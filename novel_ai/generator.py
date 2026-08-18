"""连写调度：上下文承接锁定、深度净化、精准字数、自动存档更新。"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config import NovelConfig, WORD_TIERS
from .filters import purify, has_ending
from .llm import LLMProvider
from .local_engine import LocalEngine
from .prompts import WRITE_BASE_PROMPT, DE_AI_RULES_PROMPT, ANTI_ENDING_PROMPT, PROGRESSION_PROMPT, chapter_user_prompt
from .storage import ProjectStore
from .wordcount import normalize, need_expansion


def _json_snippet(obj: Any, limit: int = 9000) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)[:limit]


def _make_messages(
    cfg: NovelConfig,
    chapter_no: int,
    total: int,
    tier: str,
    world: Dict[str, Any],
    chars: Dict[str, Any],
    plot: Dict[str, Any],
    tail: str,
) -> List[Dict[str, str]]:
    low, high = WORD_TIERS[tier]
    system = WRITE_BASE_PROMPT
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
    )
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


def _generate_one(
    cfg: NovelConfig,
    chapter_no: int,
    total: int,
    tier: str,
    world: Dict[str, Any],
    chars: Dict[str, Any],
    plot: Dict[str, Any],
    tail: str,
) -> str:
    llm = LLMProvider()
    local = LocalEngine(cfg.title)
    low, high = WORD_TIERS[tier]

    if llm.available:
        messages = _make_messages(cfg, chapter_no, total, tier, world, chars, plot, tail)
        last_err = ""
        for attempt in range(2):
            try:
                text = llm.chat(messages, max_tokens=min(high * 2, 20000), temperature=0.9)
                text = text.strip()
                if cfg.de_ai:
                    text = purify(text, remove_ai=True, forbid_ending=cfg.anti_ending).cleaned_text
                if cfg.anti_ending and has_ending(text):
                    text = _open_continuation(text)
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
                last_err = str(exc)
                break
        # 模型连续失败则回退离线引擎
        text = local.generate_chapter(world, chapter_no, total, tier, tail)
        if cfg.de_ai:
            text = purify(text, remove_ai=True, forbid_ending=cfg.anti_ending).cleaned_text
        return text

    text = local.generate_chapter(world, chapter_no, total, tier, tail)
    if cfg.de_ai:
        text = purify(text, remove_ai=True, forbid_ending=cfg.anti_ending).cleaned_text
    return text


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
    # 未解决危机保持未回收，模拟百万字不丢线
    plot["pending_conflicts"] = plot.get("pending_conflicts", []) or []
    if chapter_no < total:
        plot["pending_conflicts"] = plot.get("pending_conflicts", []) + [f"第{chapter_no+1}章续接第{chapter_no}章结尾冲突"]
    plot["main_progress"] = plot.get("main_progress", "") or "主线持续推进中"

    store.write("char.json", chars)
    store.write("plot.json", plot)


def generate_chapters(
    store: ProjectStore,
    cfg: NovelConfig,
    chapters: int,
    tier: str,
) -> List[Dict[str, Any]]:
    world = store.read("world.json") if cfg.memory_inherit else {}
    chars = store.read("char.json") if cfg.memory_inherit else {}
    plot = store.read("plot.json") if cfg.memory_inherit else {}
    results: List[Dict[str, Any]] = []
    for i in range(1, chapters + 1):
        tail = store.last_tail(500) if cfg.memory_inherit else ""
        text = _generate_one(cfg, i, chapters, tier, world, chars, plot, tail)
        # 精准字数兜底校验
        low, high = WORD_TIERS[tier]
        result = normalize(text, tier)
        if not result.ok:
            text = result.text
        path = store.append_chapter(i, text)
        if cfg.autosave:
            _update_archives(store, i, text, chapters)
        results.append({
            "chapter": i,
            "chars": len("".join(text.split())),
            "path": str(path),
            "text": text,
        })
    return results
