"""OpenAI 兼容大模型接口；未配置密钥时自动回退离线演示引擎。

特性：
- 自动读取项目根目录 .env
- 优先使用 requests，缺失时退回 urllib
- 对 429/5xx/连接错误自动重试并指数退避
- 兼容 reasoning 模型（deepseek-v4-flash 等），稳定解析 content
"""
from __future__ import annotations
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    import requests
    HAS_REQUESTS = True
except Exception:  # pragma: no cover
    requests = None
    HAS_REQUESTS = False

import urllib.error
import urllib.request

from .settings import load_runtime_settings


def load_env_file(path=None):
    """从项目根目录 .env 读取配置，已存在的环境变量优先。"""
    env_path = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    text = env_path.read_text(encoding="utf-8-sig")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _backoff_seconds(attempt: int) -> float:
    return min(2.0 * (2 ** attempt), 8.0)


class LLMProvider:
    def __init__(self) -> None:
        load_env_file()
        rt = load_runtime_settings()
        rt_api_key = str(rt.get("api_key") or "").strip()
        rt_base_url = str(rt.get("base_url") or "").strip()
        rt_model = str(rt.get("model") or "").strip()
        self.api_key = rt_api_key or os.getenv("NOVEL_API_KEY", "").strip()
        self.base_url = (rt_base_url or os.getenv("NOVEL_BASE_URL", "https://api.openai.com/v1").strip()).rstrip("/")
        self.model = rt_model or os.getenv("NOVEL_MODEL", "gpt-4o-mini").strip()
        try:
            self.timeout = int(os.getenv("NOVEL_TIMEOUT", "600"))
        except ValueError:
            self.timeout = 600
        try:
            self.max_retries = int(os.getenv("NOVEL_MAX_RETRIES", "3"))
        except ValueError:
            self.max_retries = 3

    @property
    def available(self) -> bool:
        key = self.api_key.lower()
        return key not in {"", "off", "false", "none", "disabled"}

    def list_models(self) -> List[str]:
        """查询 {base_url}/models 返回可用模型 id；异常或未配置时返回 []（不抛异常）。"""
        if not self.available:
            return []
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            if HAS_REQUESTS:
                resp = requests.get(url, headers=headers, timeout=15)
                if not resp.ok:
                    return []
                obj = resp.json()
            else:
                req = urllib.request.Request(url, headers=headers, method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    obj = json.loads(resp.read().decode("utf-8"))
            ids = [str(item.get("id")) for item in obj.get("data", []) if isinstance(item, dict) and item.get("id")]
            return sorted(set(ids))
        except Exception:
            return []

    def _http_post(self, url: str, payload: Dict[str, Any]) -> str:
        """发送请求并返回原始响应文本，优先 requests。"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        if HAS_REQUESTS:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            body = resp.text
            if resp.status_code >= 400:
                raise RuntimeError(f"模型接口返回 {resp.status_code}: {body[:500]}")
            return body

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"模型接口返回 {e.code}: {detail[:500]}")

    @staticmethod
    def _parse_content(obj: Any) -> str:
        """从 OpenAI 兼容响应中稳妥提取 assistant 文本。"""
        try:
            choice = obj["choices"][0]
            message = choice.get("message", {}) or {}
            content = message.get("content")
            if content is not None and str(content).strip():
                return str(content).strip()
            # 部分 reasoning 模型可能放在 reasoning_content
            rc = message.get("reasoning_content")
            if rc is not None and str(rc).strip():
                return str(rc).strip()
        except (KeyError, IndexError, TypeError):
            pass
        raise RuntimeError(f"模型响应结构异常: {json.dumps(obj, ensure_ascii=False)[:500]}")

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 4096, temperature: float = 0.9) -> str:
        if not self.available:
            raise RuntimeError("未配置 NOVEL_API_KEY，无法调用真实大模型")
        url = f"{self.base_url}/chat/completions"
        # 根据模型能力裁剪 max_tokens 上限，避免超出模型限制导致 400 错误
        model_lower = str(self.model).lower()
        token_cap = 20000
        if model_lower.startswith("minimax"):
            token_cap = 16384
        elif "deepseek" in model_lower or "qwen" in model_lower:
            token_cap = 16384
        max_tokens = max(1, min(int(max_tokens), token_cap))

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        last_err = ""
        for attempt in range(self.max_retries):
            try:
                body = self._http_post(url, payload)
                obj = json.loads(body)
                return self._parse_content(obj)
            except Exception as exc:
                last_err = str(exc)
                if attempt < self.max_retries - 1:
                    time.sleep(_backoff_seconds(attempt))
        raise RuntimeError(last_err or "模型接口未知错误")


    def chat_stream(self, messages, max_tokens=4096, temperature=0.9, on_token=None):
        """流式调用 LLM，每收到一个 token 调用 on_token(text)。返回完整文本。"""
        if not self.available:
            raise RuntimeError("未配置 NOVEL_API_KEY")
        url = f"{self.base_url}/chat/completions"
        model_lower = str(self.model).lower()
        token_cap = 20000
        if model_lower.startswith("minimax"):
            token_cap = 16384
        elif "deepseek" in model_lower or "qwen" in model_lower:
            token_cap = 16384
        max_tokens = max(1, min(int(max_tokens), token_cap))
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        last_err = ""
        for attempt in range(self.max_retries):
            try:
                if HAS_REQUESTS:
                    import requests as req
                    resp = req.post(url, headers=headers, json=payload, stream=True, timeout=self.timeout)
                    if resp.status_code >= 400:
                        raise RuntimeError(f"模型接口返回 {resp.status_code}: {resp.text[:500]}")
                    full = []
                    for line in resp.iter_lines():
                        if not line:
                            continue
                        decoded = line.decode('utf-8', errors='replace')
                        if decoded.startswith('data: '):
                            decoded = decoded[6:]
                        if decoded.strip() == '[DONE]':
                            break
                        try:
                            chunk = json.loads(decoded)
                            delta = chunk.get('choices', [{}])[0].get('delta', {})
                            content = delta.get('content', '') or ''
                            if content:
                                full.append(content)
                                if on_token:
                                    on_token(content)
                        except json.JSONDecodeError:
                            continue
                    return ''.join(full)
                else:
                    # fallback: use urllib but no streaming (urllib can't stream easily)
                    import urllib.request
                    data = json.dumps(payload).encode('utf-8')
                    req2 = urllib.request.Request(url, data=data, headers=headers, method='POST')
                    with urllib.request.urlopen(req2, timeout=self.timeout) as resp2:
                        body = resp2.read().decode('utf-8')
                    obj = json.loads(body)
                    return self._parse_content(obj)
            except Exception as exc:
                last_err = str(exc)
                if attempt < self.max_retries - 1:
                    import time as _time
                    _time.sleep(_backoff_seconds(attempt))
        raise RuntimeError(last_err or "流式接口未知错误")

    def test(self, prompt: str = "只回复两个字：在线") -> str:
        return self.chat([{"role": "user", "content": prompt}], max_tokens=50, temperature=0)

import re
def safe_json_loads(raw: str) -> Any:
    """从模型返回文本中安全提取 JSON 对象，修复常见格式错误。"""
    if not raw or not raw.strip():
        raise ValueError("空响应")
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"未找到 JSON 对象: {raw[:200]}")
    raw = raw[start:end + 1]
    raw = _fix_mixed_quotes(raw)
    raw = _fix_inner_quotes(raw)
    last_err = None
    for cand in _json_candidates(raw):
        try:
            return json.loads(cand)
        except json.JSONDecodeError as e:
            last_err = e
            continue
    raise ValueError(f"JSON 解析失败（{last_err}）: {raw[:500]}")

def _fix_inner_quotes(s: str) -> str:
    out = []
    in_str = False
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            out.append(s[i:i + 2])
            i += 2
            continue
        if ch == '"':
            if not in_str:
                in_str = True
                out.append(ch)
            else:
                j = i + 1
                while j < n and s[j] in " \t\n\r":
                    j += 1
                if j >= n or s[j] in ",:}]\n":
                    in_str = False
                    out.append(ch)
                else:
                    out.append("\u300c")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)

def _fix_mixed_quotes(s: str) -> str:
    out = []
    in_str = False
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch == "\\" and i + 1 < n:
            out.append(s[i:i + 2])
            i += 2
            continue
        if ch == '"':
            if not in_str:
                in_str = True
                out.append(ch)
            else:
                j = i + 1
                while j < n and s[j] in " \t\n\r":
                    j += 1
                if j >= n or s[j] in ",:}]\n":
                    in_str = False
                    out.append(ch)
                else:
                    out.append("\u300c")
            i += 1
            continue
        if ch == "'":
            if in_str:
                j = i + 1
                saw_newline = False
                while j < n and s[j] in " \t\n\r":
                    if s[j] in "\n\r":
                        saw_newline = True
                    j += 1
                if j >= n or s[j] in ",:}]" or (saw_newline and s[j] == '"'):
                    out.append('"')
                    in_str = False
                else:
                    out.append(ch)
            else:
                out.append(ch)
            i += 1
            continue
        out.append(ch)
        i += 1
    if in_str:
        out.append('"')
    return "".join(out)

def _json_candidates(s: str) -> list:
    def _clean(t):
        import re
        t = re.sub(r",\s*}", "}", t)
        t = re.sub(r",\s*\]", "]", t)
        t = re.sub(r",\s*$", "", t)
        return t
    candidates = []
    cleaned = _clean(s)
    for n in range(0, 9):
        candidates.append(cleaned + "}" * n)
    idx = len(cleaned)
    for _ in range(40):
        idx = cleaned.rfind("}", 0, idx)
        if idx <= 0:
            break
        cand = _clean(cleaned[:idx + 1])
        candidates.append(cand)
    seen = set()
    result = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            result.append(c)
    return result
