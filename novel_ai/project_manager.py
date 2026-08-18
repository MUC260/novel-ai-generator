"""工程新建、载入、补全与三份存档初始化。"""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .config import NovelConfig
from .llm import LLMProvider
from .local_engine import world_from_title
from .storage import ProjectStore, safe_project_name


def _custom_dict(cfg: NovelConfig) -> Dict[str, str]:
    return {
        "genre": cfg.genre,
        "style": cfg.style,
        "world": cfg.world,
        "rules": cfg.rules,
        "power": cfg.power,
        "forces": cfg.forces,
        "protagonist": cfg.protagonist,
        "side_characters": cfg.side_characters,
        "antagonist": cfg.antagonist,
        "opening": cfg.opening,
        "conflict": cfg.conflict,
        "relations": cfg.relations,
        "direction": cfg.direction,
        "taboos": cfg.taboos,
        "preferences": cfg.preferences,
    }


def _build_world(cfg: NovelConfig) -> Dict[str, Any]:
    custom = _custom_dict(cfg)
    llm = LLMProvider()
    if llm.available:
        from .prompts import world_prompt
        try:
            raw = llm.chat(
                [{"role": "user", "content": world_prompt(cfg.title, custom)}],
                max_tokens=6000,
                temperature=0.8,
            )
            # 去掉可能的 ```json 围栏
            if "```" in raw:
                start = raw.find("{")
                end = raw.rfind("}")
                raw = raw[start:end + 1] if start != -1 and end != -1 else raw
            world = json.loads(raw)
            if not isinstance(world, dict) or "world_setting" not in world:
                raise ValueError("模型返回缺少 world_setting")
            world["locked"] = True
            if not world.get("genre"):
                world["genre"] = custom.get("genre") or world.get("world_setting", {}).get("世界类型", "")
            if not world.get("style"):
                world["style"] = custom.get("style") or world.get("world_setting", {}).get("整体基调", "")
            return world
        except Exception:
            # 大模型异常时回退离线世界生成
            return world_from_title(cfg.title, custom)
    return world_from_title(cfg.title, custom)


def _char_from_world(world: Dict[str, Any]) -> Dict[str, Any]:
    characters = world.get("character_list", []) or []
    return {
        "characters": characters,
        "relations": world.get("force_map", []) or [],
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _plot_from_world(world: Dict[str, Any]) -> Dict[str, Any]:
    plot = world.get("plot_framework", {}) or {}
    return {
        "events": [],
        "short_arcs": plot.get("短期伏笔", []),
        "mid_arcs": plot.get("中期伏笔", []),
        "long_arcs": plot.get("长线伏笔", []),
        "crises": plot.get("当前未解决危机", []),
        "main_progress": plot.get("全书终极主线", ""),
        "side_progress": plot.get("中期节点", []),
        "current_tension": plot.get("短期开局冲突", ""),
        "pending_conflicts": plot.get("未来潜在大冲突", []),
    }


def create_project(cfg: NovelConfig, projects_root: Path) -> Dict[str, Any]:
    store = ProjectStore(projects_root, cfg.title)
    world = _build_world(cfg)
    world.setdefault("locked", True)
    store.write("world.json", world)
    store.write("char.json", _char_from_world(world))
    store.write("plot.json", _plot_from_world(world))
    return {
        "title": cfg.title,
        "dir": str(store.dir),
        "world": world,
        "store": store,
    }


def load_project(title: str, projects_root: Path) -> Optional[ProjectStore]:
    name = safe_project_name(title)
    dir_path = Path(projects_root) / name
    if not dir_path.exists():
        return None
    return ProjectStore(projects_root, title)


def list_projects(projects_root: Path) -> list[str]:
    root = Path(projects_root)
    if not root.exists():
        return []
    return sorted([p.name for p in root.iterdir() if p.is_dir() and (p / "world.json").exists()])
