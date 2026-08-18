"""深度去 AI 文风净化：套话词库、模板结构、结尾检测与替换。"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List

# 全网最细 AI 套话禁用词库
AI_PHRASES = [
    "不由得", "一时间", "就这样", "此刻", "此时", "亦是", "便是",
    "殊不知", "缓缓", "渐渐", "随即", "心中暗道", "脑海一闪",
    "心头一凛", "万般思绪涌上心头", "不由感慨", "在此刻", "于此时",
    "随之而来", "渐渐明白", "缓缓开口", "就在这时", "与此同时",
    "不曾想", "谁也没想到", "偏偏在此时", "然后", "于是", "接着",
    "不禁", "忍不住", "仿佛", "似乎", "像是", "宛如",
]

# 结尾收束语：绝对禁止
ENDING_PHRASES = [
    "告一段落", "至此", "尘埃落定", "暂时平静", "风波平息",
    "暂时安稳", "事情终于结束", "一切恢复平静", "终成定局",
    "画上句号", "告终", "落幕", "收场",
]

# 机械过渡句
TRANSITION_PHRASES = [
    "就在这时", "与此同时", "不曾想", "谁也没想到", "偏偏在此时",
    "突然之间", "刹那间", "瞬间", "电光火石之间",
]

REPLACEMENTS = {
    "不由得": "没压住",
    "一时间": "当场",
    "就这样": "到了这一步",
    "此刻": "这会儿",
    "此时": "这会儿",
    "亦是": "也是",
    "便是": "就是",
    "殊不知": "没料到",
    "缓缓": "慢吞吞",
    "渐渐": "一点点",
    "随即": "紧跟着",
    "就在这时": "没等反应",
    "与此同时": "另一头",
    "不曾想": "没料到",
    "谁也没想到": "没人料到",
    "仿佛": "跟",
    "似乎": "像",
    "像是": "跟",
    "然后": "",
    "于是": "",
    "接着": "随后",
}


@dataclass
class FilterReport:
    cleaned_text: str
    removed: int
    found: List[str]
    ending_hit: bool
    ending_found: List[str]
    transition_hit: bool


def purify(text: str, remove_ai: bool = True, forbid_ending: bool = True) -> FilterReport:
    """扫描、统计、剔除高频 AI 套话，并检测结尾收束。"""
    found: List[str] = []
    cleaned = text or ""
    if remove_ai:
        for phrase in sorted(AI_PHRASES, key=len, reverse=True):
            if phrase in cleaned:
                found.append(phrase)
                cleaned = cleaned.replace(phrase, REPLACEMENTS.get(phrase, ""))
    ending_found = [p for p in ENDING_PHRASES if p in cleaned] if forbid_ending else []
    transition_hit = any(p in cleaned for p in TRANSITION_PHRASES)
    removed = len(found)
    return FilterReport(
        cleaned_text=cleaned,
        removed=removed,
        found=found,
        ending_hit=bool(ending_found),
        ending_found=ending_found,
        transition_hit=transition_hit,
    )


def has_ending(text: str) -> bool:
    return any(p in text for p in ENDING_PHRASES)
