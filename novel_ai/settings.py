# -*- coding: utf-8 -*-
"""运行时密钥/模型设置：优先于 .env 的持久化配置。

- SETTINGS_FILE 位于项目根目录 runtime_settings.json（已 gitignore 的本地文件）。
- load_runtime_settings(): 文件缺失或内容非法时返回空 dict。
- save_runtime_settings(): 以 UTF-8、ensure_ascii=False、indent=2 写入。
- mask_api_key(): 密钥脱敏，非空返回 "sk-****<后4位>" 形式。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

SETTINGS_FILE = Path(__file__).resolve().parent.parent / "runtime_settings.json"


def load_runtime_settings() -> Dict[str, Any]:
    """读取运行时设置；文件不存在或不是合法 JSON dict 时返回 {}。"""
    if not SETTINGS_FILE.exists():
        return {}
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def save_runtime_settings(data: dict) -> None:
    """以 UTF-8、ensure_ascii=False、indent=2 写入运行时设置。"""
    SETTINGS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def mask_api_key(key: str) -> str:
    """密钥脱敏：非空时返回形如 "sk-****<后4位>"，空字符串返回空串。"""
    key = str(key or "").strip()
    if not key:
        return ""
    if len(key) <= 4:
        return "****"
    if key.startswith("sk-"):
        prefix = "sk-"
    else:
        prefix = key[:3]
    return f"{prefix}****{key[-4:]}"
