"""三档精准锁字体系：严格字数控制、校验、裁剪与补足。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple

from .config import WORD_TIERS

# 适合断句的中文标点
CUT_PUNCT = "。！？；…"
SAFE_PUNCT = "。！？"


def char_count(text: str) -> int:
    """按中文网文习惯统计正文字数：排除所有空白字符。"""
    return len("".join(text.split()))


@dataclass
class WordResult:
    text: str
    count: int
    low: int
    high: int
    ok: bool
    message: str


def normalize(text: str, tier: str) -> WordResult:
    low, high = WORD_TIERS[tier]
    text = (text or "").strip()
    count = char_count(text)
    if count < low:
        return WordResult(text, count, low, high, False, f"字数不足：{count}/{low}-{high}")
    if count > high:
        trimmed = trim_to(text, high)
        count = char_count(trimmed)
        if count < low:
            return WordResult(text, char_count(text), low, high, False, "字数溢出且无法安全裁剪")
        return WordResult(trimmed, count, low, high, True, f"已裁剪至 {count} 字")
    return WordResult(text, count, low, high, True, f"字数合格：{count}")


def trim_to(text: str, max_count: int) -> str:
    """从后往前在句子边界裁剪，尽量保留完整句。"""
    if char_count(text) <= max_count:
        return text
    tail = text[: max_count + 80]
    cut = max_count
    for i in range(max_count, max(0, max_count - 80), -1):
        if i < len(tail) and tail[i - 1] in CUT_PUNCT:
            cut = i
            break
    return tail[:cut].rstrip()


def need_expansion(text: str, tier: str) -> bool:
    low, _ = WORD_TIERS[tier]
    return char_count(text) < low
