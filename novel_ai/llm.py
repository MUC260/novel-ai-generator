"""OpenAI 兼容大模型接口；未配置密钥时自动回退离线演示引擎。"""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List


class LLMProvider:
    def __init__(self) -> None:
        self.api_key = os.getenv("NOVEL_API_KEY", "").strip()
        self.base_url = os.getenv("NOVEL_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.model = os.getenv("NOVEL_MODEL", "gpt-4o-mini").strip()
        try:
            self.timeout = int(os.getenv("NOVEL_TIMEOUT", "120"))
        except ValueError:
            self.timeout = 120

    @property
    def available(self) -> bool:
        return bool(self.api_key)

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
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"模型接口返回 {e.code}: {detail[:500]}")
        obj = json.loads(body)
        try:
            return obj["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"模型响应结构异常: {body[:500]}") from exc
