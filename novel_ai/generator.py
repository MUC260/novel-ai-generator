# -*- coding: utf-8 -*-
"""连写调度：上下文承接锁定、深度净化、精准字数、自动存档更新。"""
from __future__ import annotations
import json
import math
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import NovelConfig, WORD_TIERS
from .filters import purify, has_ending
from .llm import LLMProvider, safe_json_loads
from .local_engine import LocalEngine
from .prompts import (
    WRITE_BASE_PROMPT,
    DE_AI_RULES_PROMPT,
    ANTI_ENDING_PROMPT,
    PROGRESSION_PROMPT,
    USER_RULES_PROMPT,
    CHAPTER1_INTRO_PROMPT,
    FORMAT_RULES_PROMPT,
    chapter_user_prompt,
)
from .storage import ProjectStore
from .wordcount import char_count, normalize, need_expansion, trim_to


def _json_snippet(obj: Any, limit: int = 9000) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)[:limit]


# ==================== 主角姓名（单字姓 -> 完整姓名） ====================

def _iter_strings(obj: Any, depth: int = 0):
    """递归遍历 dict/list/str，产出所有字符串片段。"""
    if depth > 12:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _iter_strings(v, depth + 1)
    elif isinstance(obj, str):
        yield obj


def _find_name_in_world(obj: Any, surname: str) -> str:
    """? world ????? ?+??? '?' -> '???'??

    ???
    - ? ?+1~3 ??? ????????? 2-4 ??????
    - ?????????????????????????????
    - 4 ???????????????? ??+?? ???
    - ??????? 2-3 ????????????????
    """
    candidates = []
    for s in _iter_strings(obj):
        for m in re.finditer(re.escape(surname) + r"[\u4e00-\u9fa5]{1,3}", s):
            full = m.group(0)
            start = m.start()
            for ln in range(2, min(len(full), 4) + 1):
                name = full[:ln]
                nxt = s[start + ln:start + ln + 1]
                is_boundary = (not nxt) or (not ("\u4e00" <= nxt <= "\u9fa5"))
                # 4 ????????????
                if ln >= 4 and not is_boundary:
                    continue
                candidates.append((is_boundary, min(ln, 3), ln, name))
    if not candidates:
        return ""
    best = max(candidates, key=lambda c: (1 if c[0] else 0, c[1], c[2]))
    return best[3]


def _canonical_name(cfg: NovelConfig, world: Dict[str, Any]) -> str:
    """获取主角完整姓名：单字姓转换为完整姓名（如 '司' -> '司无名'），非单字直接返回。

    查找顺序：
    1. cfg.protagonist 本身（>=2 字直接返回）
    2. world._user_custom / user_custom / custom 里的主角姓名
    3. world.character_list[0].姓名 / 名字
    4. 递归搜索 plot_framework 中的 姓+名
    5. 回退默认：姓 + '无名'
    """
    if not cfg or not cfg.protagonist:
        return ""
    protagonist = str(cfg.protagonist).strip()
    if not protagonist:
        return ""
    if len(protagonist) >= 2:
        return protagonist
    surname = protagonist
    if world and isinstance(world, dict):
        # 1) 用户自定义里的完整姓名
        for key in ("_user_custom", "user_custom", "custom"):
            custom = world.get(key)
            if isinstance(custom, dict):
                for name_key in ("主角姓名", "protagonist", "protagonist_name", "姓名", "名字", "name"):
                    val = custom.get(name_key)
                    if isinstance(val, str):
                        val = val.strip()
                        if val.startswith(surname) and 2 <= len(val) <= 4:
                            return val
        # 2) character_list 第一个角色
        char_list = world.get("character_list") or []
        if char_list and isinstance(char_list[0], dict):
            for name_key in ("姓名", "名字", "name"):
                val = str(char_list[0].get(name_key, "") or "").strip()
                if val.startswith(surname) and 2 <= len(val) <= 4:
                    return val
        # 3) plot_framework 递归搜索
        found = _find_name_in_world(world.get("plot_framework") or world, surname)
        if found:
            return found
    # 4) 回退默认完整姓名
    return surname + "无名"


def _fix_protagonist_name(text: str, cfg: NovelConfig, world: Dict[str, Any]) -> str:
    """修正正文中的主角名：单字姓必须替换为世界中的完整姓名。"""
    if not text:
        return text
    canon = _canonical_name(cfg, world)
    if not canon:
        return text
    surname = str(cfg.protagonist or "").strip()
    # 旧名修正（用户覆盖主角名后，world 里残留的旧名）
    if isinstance(world, dict):
        old_name = str(world.get("_old_protagonist_name", "") or "").strip()
        if old_name and len(old_name) >= 2 and old_name != canon:
            text = text.replace(old_name, canon)
    if len(surname) == 1 and surname != canon:
        # 替换"孤立的单字姓"（前面和后面都不跟汉字，避免误伤 司马/司徒 等）
        pattern = re.compile(
            r"(?<![\u4e00-\u9fa5])" + re.escape(surname) + r"(?![\u4e00-\u9fa5])"
        )
        text = pattern.sub(canon, text)
    return text


# ==================== 用户世界观 / 自定义设定最高优先级 ====================

def _extract_custom_context(cfg: NovelConfig, world: Dict[str, Any]) -> str:
    """从 cfg 和 world 中提取用户设定，构造【最高优先级】提示段落。

    确保 AI 严格遵循用户提供的世界观、主角姓名、开篇等，绝不敷衍。
    """
    lines = []
    if not cfg:
        cfg = NovelConfig()
    canon = _canonical_name(cfg, world)
    if canon:
        lines.append(f"主角完整姓名（全书必须一字不差使用，禁止只用单字姓）：{canon}")
    field_map = [
        ("worldview", "用户世界观补充（最高优先级）"),
        ("world", "用户世界观"),
        ("opening", "用户开篇设定"),
        ("conflict", "用户冲突设定"),
        ("direction", "用户剧情方向"),
        ("rules", "用户附加规则"),
        ("power", "用户力量体系设定"),
        ("forces", "用户势力设定"),
        ("side_characters", "用户配角设定"),
        ("antagonist", "用户反派设定"),
        ("relations", "用户人物关系"),
        ("taboos", "用户禁忌设定"),
        ("preferences", "用户文风偏好"),
        ("genre", "用户题材"),
        ("style", "用户文风"),
    ]
    for attr, label in field_map:
        val = str(getattr(cfg, attr, "") or "").strip()
        if val:
            lines.append(f"{label}：{val}")
    if world and isinstance(world, dict):
        ws = world.get("world_setting")
        if isinstance(ws, dict):
            core = ws.get("用户核心世界观（最高优先级，所有设定必须以此为基础，禁止偏离）", "")
            if isinstance(core, str) and core.strip():
                lines.append(f"用户核心世界观（最高优先级，所有设定必须以此为基础，禁止偏离）：{core.strip()}")
        custom = world.get("_user_custom")
        if isinstance(custom, dict):
            seen = set()
            for k, v in custom.items():
                if k in ("protagonist", "主角姓名", "name", "protagonist_name"):
                    continue
                if k in seen or not isinstance(v, str) or not v.strip():
                    continue
                seen.add(k)
                lines.append(f"用户设定-{k}：{v.strip()}")
    if not lines:
        return ""
    return (
        "【用户设定（最高优先级铁律：任何生成内容必须严格遵循，禁止篡改、禁止忽略、禁止偏离）】\n"
        + "\n".join(lines)
        + "\n【以上为用户设定，优先级高于一切自动生成档案。】"
    )


# ==================== 第 1 章开场身世 ====================

def _find_first_sentence_end(text: str) -> int:
    """找第一个句子结束位置。"""
    m = re.search(r"[。！？…\n]", text)
    return m.end() if m else min(len(text), 200)


def _ensure_protagonist_name(text: str, cfg: NovelConfig, world: Dict[str, Any], chapter_no: int) -> str:
    """第 1 章前 300 字必须有主角完整姓名；缺失则插入含身世的开场句。"""
    if chapter_no != 1:
        return text
    canon = _canonical_name(cfg, world)
    if not canon:
        return text
    head = text[:300]
    if canon in head:
        return text
    # 若只写了单字姓，先整体替换
    surname = str(cfg.protagonist or "").strip()
    if len(surname) == 1 and surname != canon and surname in head:
        fixed = _fix_protagonist_name(text, cfg, world)
        if canon in fixed[:300]:
            return fixed
    # 仍缺失 -> 插入开场句（交代姓名 + 身世 + 当前处境）
    genre = ""
    if isinstance(world, dict):
        ws = world.get("world_setting") or {}
        genre = str((world.get("genre") or (ws.get("世界类型", "") if isinstance(ws, dict) else "")) or "")
    opening = (
        f"{canon}打记事起就在{genre or '这片土地上'}讨生活，身上背着的旧事压得他喘不过气，"
        "可再难的日子也得朝前挪，他清楚自己没得选。"
    )
    return opening + "\n\n" + text


def _post_process_chapter(
    text: str,
    cfg: NovelConfig,
    world: Dict[str, Any],
    chapter_no: int,
    tier: str = "standard",
) -> str:
    """统一后处理：修主角名 + 第1章开场身世 + 排版/字数净化。"""
    if not text:
        return text
    text = _fix_protagonist_name(text, cfg, world)
    text = _ensure_protagonist_name(text, cfg, world, chapter_no)
    result = normalize(text, tier)
    return result.text


# ==================== 记忆追踪 ====================

def extract_memory_from_chapter(chapter_no: int, text: str, existing_memory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """从章节正文提取关键记忆（人物、地点、事件、状态），供后续章节注入。"""
    memory = dict(existing_memory or {})
    series = memory.setdefault("series", [])
    while len(series) >= 30:
        series.pop(0)
    head = text[:600].replace("\n", " ")
    series.append({
        "chapter": chapter_no,
        "summary": head,
        "chars": char_count(text),
    })
    memory["last_chapter"] = chapter_no
    memory["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return memory


def inject_memory_to_prompt(memory: Optional[Dict[str, Any]], chapter_no: int) -> str:
    """把记忆摘要注入提示词：交代前文关键事件与人物状态。"""
    memory = memory or {}
    series = memory.get("series") or []
    if not series:
        return ""
    parts = []
    for item in series[-8:]:
        ch = item.get("chapter")
        summary = str(item.get("summary", "") or "").strip()
        if summary:
            parts.append(f"第{ch}章摘要：{summary}")
    if not parts:
        return ""
    return "【前文记忆摘要（必须继承，禁止遗忘）】\n" + "\n".join(parts)


# ==================== 伏笔系统 ====================

def init_foreshadowing_tracker() -> Dict[str, Any]:
    """初始化伏笔追踪器。"""
    return {"foreshadows": [], "resolved": [], "injected": []}


def update_foreshadowing_status(tracker: Dict[str, Any], chapter_text: str) -> Dict[str, Any]:
    """根据章节正文更新伏笔状态（记录提及过的伏笔，回收已揭示的伏笔）。"""
    tracker = dict(tracker or init_foreshadowing_tracker())
    foreshadows = tracker.setdefault("foreshadows", [])
    seen = set()
    for item in foreshadows:
        name = str(item if isinstance(item, str) else (item.get("name", "") if isinstance(item, dict) else ""))
        if name and name in chapter_text:
            seen.add(name)
    seen_prev = set(tracker.get("injected", []))
    for name in seen - seen_prev:
        tracker["injected"] = tracker.get("injected", []) + [name]
    return tracker


# ==================== 提示词构造 ====================

def _make_messages(
    cfg: NovelConfig,
    chapter_no: int,
    total: int,
    tier: str,
    world: Dict[str, Any],
    chars: Dict[str, Any],
    plot: Dict[str, Any],
    tail: str,
    memory: Optional[Dict[str, Any]] = None,
    custom_context: Optional[str] = None,
) -> List[Dict[str, str]]:
    low, high = WORD_TIERS[tier]
    system = WRITE_BASE_PROMPT
    # 用户定制设定绝对优先
    system += "\n\n" + USER_RULES_PROMPT
    if cfg.de_ai:
        system += "\n\n" + DE_AI_RULES_PROMPT
    if cfg.anti_ending:
        system += "\n\n" + ANTI_ENDING_PROMPT
    if cfg.progression and total > 1:
        system += "\n\n" + PROGRESSION_PROMPT
    user = chapter_user_prompt(
        cfg.title,
        chapter_no,
        total,
        tier,
        low,
        high,
        _json_snippet(world),
        _json_snippet(chars),
        _json_snippet(plot),
        tail,
        custom_context=(custom_context if custom_context is not None else _extract_custom_context(cfg, world)),
    )
    if memory:
        injected = inject_memory_to_prompt(memory, chapter_no)
        if injected:
            user += "\n\n" + injected
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _open_continuation(text: str) -> str:
    """防割裂：如果模型给出收尾句，替换为强续接画面。"""
    replacements = [
        ("至此", "还没等他缓过气，"),
        ("尘埃落定", "地上的灰还没散"),
        ("告一段落", "事情只开了一个口"),
        ("风波平息", "外头的动静压了下去"),
        ("暂时安稳", "这份安稳薄得像纸"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text


# ==================== 单章生成 ====================

def _generate_one(
    cfg: NovelConfig,
    chapter_no: int,
    total: int,
    tier: str,
    world: Dict[str, Any],
    chars: Dict[str, Any],
    plot: Dict[str, Any],
    tail: str,
    on_progress=None,
    memory: Optional[Dict[str, Any]] = None,
) -> str:
    llm = LLMProvider()
    local = LocalEngine(cfg.title)
    low, high = WORD_TIERS[tier]
    custom_context = _extract_custom_context(cfg, world)
    _done = [False]
    _stop = [False]

    def _ticker():
        import time as _t
        while not _stop[0]:
            if not _done[0] and on_progress:
                try:
                    on_progress("")
                except Exception:
                    pass
            _t.sleep(0.8)

    ticker_thread = None
    if on_progress:
        ticker_thread = threading.Thread(target=_ticker, daemon=True)
        ticker_thread.start()

    try:
        if llm.available:
            messages = _make_messages(
                cfg, chapter_no, total, tier, world, chars, plot, tail,
                memory=memory, custom_context=custom_context,
            )
            last_err = ""
            for attempt in range(2):
                try:
                    _done[0] = False
                    if on_progress:
                        on_progress("")
                    text = llm.chat(messages, max_tokens=min(high * 2, 20000), temperature=0.9)
                    _done[0] = True
                    text = text.strip()
                    if cfg.de_ai:
                        text = purify(text, remove_ai=True, forbid_ending=cfg.anti_ending).cleaned_text
                    if cfg.anti_ending and has_ending(text):
                        text = _open_continuation(text)
                    text = _post_process_chapter(text, cfg, world, chapter_no, tier)
                    result = normalize(text, tier)
                    if result.ok:
                        return result.text
                    if need_expansion(text, tier):
                        messages.append({"role": "assistant", "content": text})
                        messages.append({"role": "user", "content": f"字数不足，请扩展到 {low}-{high} 字，不要重复已写内容，继续推进剧情。"})
                    else:
                        messages.append({"role": "assistant", "content": text})
                        messages.append({"role": "user", "content": f"字数超出，请压缩到 {low}-{high} 字，保留最后画面，不要收尾。"})
                    last_err = result.message
                except Exception as exc:
                    _done[0] = True
                    last_err = str(exc)
                    continue
            # 模型连续失败则回退离线引擎
            text = local.generate_chapter(world, chapter_no, total, tier, tail)
            if cfg.de_ai:
                text = purify(text, remove_ai=True, forbid_ending=cfg.anti_ending).cleaned_text
            return _post_process_chapter(text, cfg, world, chapter_no, tier)

        text = local.generate_chapter(world, chapter_no, total, tier, tail)
        if cfg.de_ai:
            text = purify(text, remove_ai=True, forbid_ending=cfg.anti_ending).cleaned_text
        return _post_process_chapter(text, cfg, world, chapter_no, tier)
    finally:
        _stop[0] = True
        if ticker_thread:
            ticker_thread.join(timeout=2)


# ==================== 存档更新 ====================

def _update_archives(store: ProjectStore, chapter_no: int, text: str, total: int) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    chars = store.read("char.json")
    plot = store.read("plot.json")

    # 动态人物状态：只做可解释的推进，不重置、不跳变
    for person in chars.get("characters", []):
        if person.get("角色定位") == "主角":
            person["当前处境"] = f"第{chapter_no}章事件刚发生，仍被局势推着走"
            person["当前情绪"] = "紧绷"
            person["近期行为"] = (person.get("近期行为", "") + f"第{chapter_no}章：继续行动。").strip()
            person["位置变化"] = "前文位置向新冲突点移动"
    chars["updated_at"] = now

    # 剧情档案：事件追加、伏笔标记、危机递延
    event = {
        "chapter": chapter_no,
        "total": total,
        "summary": text[:120].replace("\n", " "),
        "created_at": now,
    }
    plot.setdefault("events", []).append(event)
    plot["current_tension"] = f"第{chapter_no}章结尾仍处于未解决状态"
    plot["pending_conflicts"] = plot.get("pending_conflicts", []) or []
    if chapter_no < total:
        plot["pending_conflicts"] = plot.get("pending_conflicts", []) + [f"第{chapter_no+1}章续接第{chapter_no}章结尾冲突"]
    plot["main_progress"] = plot.get("main_progress", "") or "主线持续推进中"

    store.write("char.json", chars)
    store.write("plot.json", plot)


# ==================== 批量章节生成 ====================

def generate_chapters(
    store: ProjectStore,
    cfg: NovelConfig,
    chapters: int,
    tier: str,
) -> List[Dict[str, Any]]:
    world = store.read("world.json") if cfg.memory_inherit else {}
    chars = store.read("char.json") if cfg.memory_inherit else {}
    plot = store.read("plot.json") if cfg.memory_inherit else {}
    memory = store.load_memory()
    tracker = init_foreshadowing_tracker()
    results: List[Dict[str, Any]] = []
    for i in range(1, chapters + 1):
        tail = store.last_tail(500) if cfg.memory_inherit else ""
        text = _generate_one(cfg, i, chapters, tier, world, chars, plot, tail, memory=memory)
        # 精准字数兜底校验
        low, high = WORD_TIERS[tier]
        result = normalize(text, tier)
        if not result.ok:
            text = result.text
        path = store.append_chapter(i, text)
        if cfg.autosave:
            _update_archives(store, i, text, chapters)
            memory = extract_memory_from_chapter(i, text, memory)
            tracker = update_foreshadowing_status(tracker, text)
            store.save_memory(memory)
        results.append({
            "chapter": i,
            "chars": len("".join(text.split())),
            "path": str(path),
            "text": text,
        })
    return results


# ==================== 大纲生成 ====================

def _default_outline(title: str, chapters: int, tier: str, world: Dict[str, Any]) -> Dict[str, Any]:
    """本地回退大纲：保证前端大纲面板始终有内容可展示。"""
    genre = str((world or {}).get("genre") or "") or "未知题材"
    canon = ""
    if world and isinstance(world, dict):
        cl = world.get("character_list") or []
        if cl and isinstance(cl[0], dict):
            canon = str(cl[0].get("姓名") or cl[0].get("名字") or "")
    outline = []
    starter = [
        "主角初登场，交代身世与当前处境，平静的日常被意外打破，冲突拉开序幕。",
        "矛盾发酵，各方势力暗流涌动，主角被迫卷入更大的漩涡。",
        "转折点出现，新线索浮出水面，隐藏的敌人第一次显露踪迹。",
        "危机升级，主角陷入两难抉择，身边的信任关系开始松动。",
        "暗线收束并埋下长线伏笔，局势进一步恶化，迫使主角主动出击。",
    ]
    for i in range(chapters):
        outline.append({
            "title": f"{canon or '主角'}的征途 · 第{i + 1}章",
            "summary": starter[i % len(starter)],
        })
    return {
        "title": title,
        "chapters": chapters,
        "tier": tier,
        "volumes": [{"name": "第一卷", "chapters": list(range(1, chapters + 1))}],
        "chapter_titles": [o["title"] for o in outline],
        "key_events": [o["summary"] for o in outline],
        "foreshadow_plan": {"short": [], "mid": [], "long": []},
        "outline": outline,
    }


def generate_outline(cfg: NovelConfig, chapters: int, tier: str, world: Dict[str, Any], chars: Dict[str, Any], plot: Dict[str, Any]) -> Dict[str, Any]:
    """LLM 生成章节大纲（JSON）；失败时回退本地默认大纲。"""
    title = cfg.title
    canon = _canonical_name(cfg, world)
    custom_context = _extract_custom_context(cfg, world)
    low, high = WORD_TIERS[tier]

    llm = LLMProvider()
    if llm.available:
        prompt = f"""你是顶尖网文大纲设计师。请为小说《{title}》设计 {chapters} 章连贯大纲。

主角完整姓名：{canon or '（待定）'}
字数档位：{low}-{high} 字/章

【用户设定（最高优先级，必须严格遵循）】
{custom_context or '无'}

世界观档案：
{_json_snippet(world, 5000)}

人物档案：
{_json_snippet(chars, 3000)}

剧情伏笔档案：
{_json_snippet(plot, 3000)}

要求：
1. 章节循序渐进、冲突升级、惊喜不断线
2. 第1章必须交代主角身世与当前处境
3. 每章给出 title 与 summary
4. 输出严格为JSON，结构如下：
{{
  "volumes": [{{"name": "第一卷", "chapters": [1,2,3,...]}}],
  "chapter_titles": ["第1章标题", ...],
  "key_events": ["关键事件", ...],
  "foreshadow_plan": {{"short": [...], "mid": [...], "long": [...]}},
  "outline": [{{"title": "第1章标题", "summary": "本章剧情概要"}}, ...]
}}
只输出JSON，不要解释。"""
        try:
            raw = llm.chat([{"role": "user", "content": prompt}], max_tokens=8000, temperature=0.8)
            data = safe_json_loads(raw)
            if isinstance(data, dict):
                outline = data.get("outline") or []
                if isinstance(outline, list) and outline:
                    data["title"] = title
                    data["chapters"] = chapters
                    data["tier"] = tier
                    return data
        except Exception:
            pass

    return _default_outline(title, chapters, tier, world)
