"""三档精准锁字体系：严格字数控制、校验、裁剪与补足。

网文排版规范（基于真实网文标准）：
- 叙述段落: 80-250字，一段表达一个完整场景/动作/情绪
- 对话段落: 单独成段，15-80字，含引号
- 动作段落: 30-120字，夹在对话之间
- 段与段之间: 1个换行符（无空行）
- 场景切换: 使用 *** 或自然过渡
- 章节开头: 零空行，直接切入
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Tuple

from .config import WORD_TIERS

# 适合断句的中文标点
CUT_PUNCT = "。！？；…"
SAFE_PUNCT = "。！？"

# 对话标记
_DIALOGUE_STARTS = ("“", "「", "『", "\"", "'", "—", "——")
_DIALOGUE_ENDS = ("”", "」", "』", "\"", "'")

# 场景分隔符
_SCENE_BREAK_RE = re.compile(r'^\s*(\*\*\*|———|——|---|···|~~~|〔场景切换〕|\[场景切换\])\s*$')

# 元信息行标记
_META_PREFIXES = ("以下为", "以上为")
_THIS_IS_META_KEYWORDS = ("本章", "上章", "本次", "生成", "故事概要", "人物档案", "世界观", "剧情", "大纲", "内容", "部分", "正文")
_TAIL_MARKERS = ("本章完", "未完待续", "（完）", "---")
_CN_NUM = "0-9一二三四五六七八九十百千万〇零"
_META_CHAPTER_RE = re.compile("^第\\s*[" + _CN_NUM + "]+\\s*[章回节卷]")


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


def _is_dialogue(line: str) -> bool:
    """判断是否对话行（引号/破折号开头或引号结尾）。"""
    s = line.strip()
    if not s:
        return False
    return s.startswith(_DIALOGUE_STARTS) or s.endswith(_DIALOGUE_ENDS)


def _is_action_after_dialogue(line: str) -> bool:
    """判断是否是对话后的短动作。"""
    s = line.strip()
    if not s:
        return False
    if _is_dialogue(s):
        return False
    return len(s) < 35


def _starts_dialogue(line: str) -> bool:
    """判断是否以引号开头。"""
    s = line.strip()
    if not s:
        return False
    return s.startswith(_DIALOGUE_STARTS)


def _is_meta_line(line: str) -> bool:
    """判断是否是元信息行。"""
    s = line.strip()
    if not s:
        return False
    if s.startswith(_META_PREFIXES):
        return True
    if s.startswith("这是") and len(s) < 40:
        # "这是" 前缀可能是普通叙述（"这是一片废墟"），仅当明显是生成元信息时才过滤
        for kw in _THIS_IS_META_KEYWORDS:
            if kw in s[2:6]:
                return True
    if _META_CHAPTER_RE.match(s) and len(s) < 30:
        # 仅纯章节标题（短行）被视为元信息，合并后的长行不视为元信息
        return True
    return False


def _is_tail_marker(line: str) -> bool:
    """判断是否是结尾标记。"""
    s = line.strip()
    return any(s.endswith(m) or s == m for m in _TAIL_MARKERS)


def _paras(text: str) -> List[str]:
    """将文本按换行分割成段落列表，保留场景分隔符。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    result = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if _SCENE_BREAK_RE.match(s):
            result.append("***")
        else:
            result.append(s)
    return result


def _remove_excessive_newlines(text: str) -> str:
    """修复排版：连续多个换行符折叠为段落间空行（\n\n），去掉开头和结尾的换行符。
    参考网文规范：每段60-250字，段间空一行，禁止连续空行。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 连续2个以上换行折叠为1个空行（网文标准：段落间最多1个空行）
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = text.lstrip("\n")
    text = text.rstrip("\n")
    return text

def _join_clean(paras: List[str]) -> str:
    """将段落列表合并回文本，清理尾部和元信息行。"""
    if not paras:
        return ""
    cleaned = []
    for p in paras:
        if p == "***":
            cleaned.append(p)
            continue
        if _is_meta_line(p) or _is_tail_marker(p):
            continue
        p = re.sub(r"\s+", " ", p).strip()
        if p:
            cleaned.append(p)
    return "\n\n".join(cleaned)


def _dedup_paragraphs(paras: List[str]) -> List[str]:
    """跨段去重：对话行保留原样，普通行去重相似句子，避免内容重复。"""
    if len(paras) < 2:
        return paras
    result = []
    seen = set()
    for p in paras:
        # 对话行不去重（不同场景重复对话属正常），普通行才做去重
        if p.strip().startswith(_DIALOGUE_STARTS):
            result.append(p)
            continue
        key = re.sub(r"\s+", "", p)[:60]
        if key not in seen:
            seen.add(key)
            result.append(p)
    return result

def _merge_text(left: str, right: str) -> str:
    """合并两个段落文本，确保不会产生过长段落。"""
    if not left:
        return right
    if not right:
        return left
    # 如果合并后超过 300 字，用句号分隔
    merged = left.rstrip() + right.lstrip()
    if len(merged) > 300:
        if left[-1] not in CUT_PUNCT:
            return left.rstrip() + "\u3002" + right.lstrip()
        return merged
    if left[-1] in CUT_PUNCT:
        return left.rstrip() + right.lstrip()
    return merged


def _split_sentences(para: str) -> List[str]:
    """将段落按句号分割成句子列表，每个句子保留其结尾标点。"""
    parts = re.split(r"([。！？；\n])", para)
    sentences = []
    buf = ""
    for p in parts:
        if re.match(r"^[。！？；\n]$", p):
            if buf:
                # 将标点附加到前一句的末尾
                buf += p
                sentences.append(buf.strip())
                buf = ""
            elif sentences:
                # 孤立标点，附加到最后一句
                sentences[-1] += p
            else:
                # 开头就是标点
                sentences.append(p)
        else:
            if buf:
                buf += p
            else:
                buf = p
    if buf.strip():
        sentences.append(buf.strip())
    return sentences or [para]


def _dedup_across_paragraphs(paras: List[str]) -> List[str]:
    """跨段落去重相似句子。"""
    if len(paras) < 2:
        return paras
    result = [paras[0]]
    all_sentences = set()
    for s in _split_sentences(paras[0]):
        all_sentences.add(re.sub(r"\s+", "", s))
    for i in range(1, len(paras)):
        current = paras[i]
        if current == "***":
            result.append(current)
            continue
        sentences = _split_sentences(current)
        kept = []
        for s in sentences:
            key = re.sub(r"\s+", "", s)[:40]
            if key not in all_sentences:
                all_sentences.add(key)
                kept.append(s)
        merged = "".join(kept)
        if merged.strip():
            result.append(merged.strip())
    return result


def _split_long_paragraph(para: str) -> List[str]:
    """将超长段落按句号/逗号拆分。"""
    if len(para) < 300:
        return [para]
    splits = []
    current = ""
    for m in re.finditer(r"[^。！？；，、！？]+[。！？；，、！？]?", para):
        seg = m.group()
        if len(current) + len(seg) > 200 and current:
            splits.append(current.strip())
            current = seg
        else:
            current += seg
    if current.strip():
        splits.append(current.strip())
    return splits if splits else [para]


def fix_layout(text: str) -> str:
    text = text.lstrip("\ufeff")
    """8轮排版修复：主流网文段落规范。

    处理流程：
    1. 统一换行符，去除空行，分割段落
    2. 短句打包（连续短行合并为一个自然段落）
    3. 合并对话+跟随的短动作
    4. 合并碎片短句（<35字非对话行）到相邻段落
    5. 合并短段（<60字非对话行）到相邻段落
    6. 合并连续短段（均<60字）
    7. 合并连续对话行
    8. 跨段去重，拆分超长段（>300字）
    """
    if not text or not text.strip():
        return ""

    # 第1轮：统一换行符，去除空行，分割段落
    paras = _paras(text)
    if not paras:
        return ""

    # 第2轮：短句打包（连续短行合并为一个自然段落）
    packed = []
    buf = []
    for p in paras:
        if _is_dialogue(p) or p == "***" or _is_meta_line(p):
            if buf:
                packed.append("".join(buf))
                buf = []
            packed.append(p)
        elif len(p) < 50:
            buf.append(p)
            if len("".join(buf)) >= 120:
                packed.append("".join(buf))
                buf = []
        else:
            if buf:
                packed.append("".join(buf))
                buf = []
            packed.append(p)
    if buf:
        packed.append("".join(buf))
    paras = packed

    # 第3轮：合并对话+跟随的短动作
    merged = []
    i = 0
    while i < len(paras):
        if i + 1 < len(paras) and _is_dialogue(paras[i]) and _is_action_after_dialogue(paras[i + 1]):
            merged.append(paras[i].rstrip() + "\n" + paras[i + 1].strip())
            i += 2
        else:
            merged.append(paras[i])
            i += 1
    paras = merged

    # 边界保护：如果只剩一个段落，不做合并
    if len(paras) <= 1:
        return _join_clean(paras)

    # 第4轮：合并碎片短句（<35字非对话行）到相邻段落，保留至少3段
    changed = True
    safety_count = 0
    while changed and safety_count < 20:
        safety_count += 1
        changed = False
        new_paras = []
        i = 0
        while i < len(paras):
            if i + 1 < len(paras) and paras[i] and paras[i + 1]:
                s = paras[i + 1].strip()
                if not _is_dialogue(s) and len(s) < 35 and s != "***" and not _is_meta_line(paras[i]):
                    remaining = len(new_paras) + (len(paras) - i - 2) // 2 + 1
                    if remaining >= 3:
                        new_paras.append(_merge_text(paras[i], s))
                        i += 2
                        changed = True
                        continue
            new_paras.append(paras[i])
            i += 1
        paras = new_paras

    if len(paras) <= 1:
        return _join_clean(paras)

    # 第5轮：合并短段（<60字非对话行）到相邻段落，保留至少3段
    changed = True
    safety_count = 0
    while changed and safety_count < 20:
        safety_count += 1
        changed = False
        new_paras = []
        i = 0
        while i < len(paras):
            if i + 1 < len(paras) and paras[i] and paras[i + 1]:
                s = paras[i + 1].strip()
                if not _is_dialogue(s) and len(s) < 60 and s != "***" and not _is_meta_line(paras[i]):
                    remaining = len(new_paras) + (len(paras) - i - 2) // 2 + 1
                    if remaining >= 3:
                        new_paras.append(_merge_text(paras[i], s))
                        i += 2
                        changed = True
                        continue
            new_paras.append(paras[i])
            i += 1
        paras = new_paras

    if len(paras) <= 1:
        return _join_clean(paras)

    # 第6轮：合并连续短段（均<60字，非对话），保留至少3段
    if len(paras) > 3:
        changed = True
        safety_count = 0
        while changed and safety_count < 20:
            safety_count += 1
            changed = False
            new_paras = []
            i = 0
            while i < len(paras):
                if i + 1 < len(paras) and paras[i] and paras[i + 1]:
                    s1 = paras[i].strip()
                    s2 = paras[i + 1].strip()
                    if (not _is_dialogue(s1) and not _is_dialogue(s2)
                            and len(s1) < 60 and len(s2) < 60
                            and s1 != "***" and s2 != "***"
                            and not _is_meta_line(s1) and not _is_meta_line(s2)):
                        remaining = len(new_paras) + (len(paras) - i - 2) // 2 + 1
                        if remaining >= 3:
                            new_paras.append(_merge_text(s1, s2))
                            i += 2
                            changed = True
                            continue
                new_paras.append(paras[i])
                i += 1
            paras = new_paras

    if len(paras) <= 1:
        return _join_clean(paras)

    # 第7轮已移除（对话应独立成段，不符合网文排版规范）

    # 第8轮：跨段去重，拆分超长段
    paras = _dedup_across_paragraphs(paras)
    split_paras = []
    for p in paras:
        if p == "***":
            split_paras.append(p)
        else:
            split_paras.extend(_split_long_paragraph(p))
    paras = split_paras

    result = _join_clean(paras)
    # 额外清理：确保没有连续过多的换行符
    result = _remove_excessive_newlines(result)
    if not result and text.strip():
        # 边界保护：过滤导致空结果时，保留原始内容（仅折叠换行）
        kept = "\n\n".join(p for p in _paras(text) if p != "***")
        return _remove_excessive_newlines(kept) if kept else text.strip()
    return result


def normalize(text: str, tier: str) -> WordResult:
    """字数校验 + 排版修复 + 裁剪。"""
    low, high = WORD_TIERS[tier]
    text = (text or "").strip()
    if not text:
        return WordResult(text, 0, low, high, False, "文本为空")

    # 先修复排版
    text = fix_layout(text)
    text = _remove_excessive_newlines(text)

    count = char_count(text)
    if count < low:
        return WordResult(text, count, low, high, False, f"字数不足：{count}/{low}-{high}")
    if count > high:
        trimmed = trim_to(text, high)
        trimmed = fix_layout(trimmed)
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
    """判断是否需要补足字数。"""
    low, _ = WORD_TIERS[tier]
    return char_count(text) < low


