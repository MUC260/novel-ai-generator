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


def load_env_file(path=None):
    """从项目根目录 .env 读取配置，已存在的环境变量优先。"""
    env_path = Path(path) if path else Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _backoff_seconds(attempt: int) -> float:
    return min(2.0 * (2 ** attempt), 8.0)


class LLMProvider:
    def __init__(self) -> None:
        load_env_file()
        self.api_key = os.getenv("NOVEL_API_KEY", "").strip()
        self.base_url = os.getenv("NOVEL_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("NOVEL_MODEL", "gpt-4o-mini").strip()
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

    def test(self, prompt: str = "只回复两个字：在线") -> str:
        return self.chat([{"role": "user", "content": prompt}], max_tokens=50, temperature=0)