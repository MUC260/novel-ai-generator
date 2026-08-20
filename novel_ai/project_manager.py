"""工程新建、载入、补全与三份存档初始化。"""

from __future__ import annotations

import json

from datetime import datetime

from pathlib import Path

from typing import Any, Dict, Optional



from .config import NovelConfig

from .llm import LLMProvider, safe_json_loads

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

        "worldview": cfg.worldview,

    }





def _build_world(cfg: NovelConfig) -> Dict[str, Any]:

    custom = _custom_dict(cfg)

    llm = LLMProvider()

    if llm.available:

        from .prompts import world_prompt, world_prompt_compact

        # 尝试最多 2 次：首次全量 prompt，若截断/解析失败则用精简 prompt 重试一次

        for attempt in range(2):

            try:

                prompt = world_prompt(cfg.title, custom) if attempt == 0 else world_prompt_compact(cfg.title, custom)

                raw = llm.chat(

                    [{"role": "user", "content": prompt}],

                    max_tokens=8000,

                    temperature=0.8,

                )

                # 去掉可能的 ```json 围栏

                if "```" in raw:

                    start = raw.find("{")

                    end = raw.rfind("}")

                    raw = raw[start:end + 1] if start != -1 and end != -1 else raw

                world = safe_json_loads(raw)

                if not isinstance(world, dict) or "world_setting" not in world:

                    raise ValueError("模型返回缺少 world_setting")

                world["locked"] = True

                if not world.get("genre"):

                    world["genre"] = custom.get("genre") or world.get("world_setting", {}).get("世界类型", "")

                if not world.get("style"):

                    world["style"] = custom.get("style") or world.get("world_setting", {}).get("整体基调", "")

                # 用户自定义覆盖：强制应用用户指定的字段，覆盖 LLM 可能忽略或篡改的值

                if custom.get("protagonist") and world.get("character_list"):

                    # 先保存 LLM 生成的原主角名，再覆盖为用户指定名

                    old_name = world["character_list"][0].get("姓名", "")

                    # 单字视为姓（如"司"），AI 生成完整姓名；非单字视为完整姓名，一字不差

                    if len(custom["protagonist"]) == 1:

                        world["_protagonist_surname"] = custom["protagonist"]

                        if old_name and old_name.startswith(custom["protagonist"]):

                            new_name = old_name

                        else:

                            # LLM生成的名字不符合预期，调用LLM重新生成完整姓名

                            try:

                                surname = custom["protagonist"]

                                wv = custom.get("worldview", "")[:100]

                                name_prompt = "请为以下姓生成2-3字的完整姓名，只输出姓名：\n姓：" + surname + "\n世界观：" + wv + "\n小说：" + cfg.title + "\n要求：姓必须一字不差，名根据世界观合理创作"

                                raw = llm.chat([{"role": "user", "content": name_prompt}], max_tokens=20, temperature=0.7)

                                gen_name = raw.strip().strip('\"\'?.')

                                if len(gen_name) >= 2 and gen_name.startswith(surname):

                                    new_name = gen_name

                                else:

                                    new_name = surname + "\u65e0\u540d"

                            except Exception:

                                new_name = surname + "\u65e0\u540d"

                            if old_name and old_name != new_name:

                                _fix_protagonist_in_plot(world, old_name, new_name)

                        world["_old_protagonist_name"] = old_name if old_name and old_name != new_name else ""

                        world["character_list"][0]["姓名"] = new_name

                    else:

                        world["character_list"][0]["姓名"] = custom["protagonist"]

                        if custom.get("worldview"):

                            world["character_list"][0]["原生经历"] = world["character_list"][0].get("原生经历", "") + "（" + custom["protagonist"] + "所在世界：" + custom["worldview"][:50] + "）"

                        world["_old_protagonist_name"] = old_name if old_name and old_name != custom["protagonist"] else ""

                        if old_name and old_name != custom["protagonist"]:

                            _fix_protagonist_in_plot(world, old_name, custom["protagonist"])

                if custom.get("antagonist") and world.get("character_list"):

                    world["character_list"][-1]["姓名"] = custom["antagonist"]

                if custom.get("opening") and world.get("plot_framework"):

                    world["plot_framework"]["短期开局冲突"] = custom["opening"]

                if custom.get("conflict") and world.get("plot_framework"):

                    world["plot_framework"]["当前未解决危机"] = [custom["conflict"]]

                if custom.get("direction") and world.get("plot_framework"):

                    world["plot_framework"]["全书终极主线"] = custom["direction"]

                if custom.get("worldview") and world.get("world_setting"):

                    ws = world["world_setting"]

                    ws["_core_worldview"] = custom["worldview"]

                    core_block = {

                        "用户核心世界观（最高优先级，所有设定必须以此为基础，禁止偏离）": custom["worldview"]

                    }

                    merged = {}

                    merged.update(core_block)

                    for k, v in ws.items():

                        if k != "_core_worldview":

                            merged[k] = v

                    world["world_setting"] = merged

                    if "用户世界观补充" in world["world_setting"]:

                        del world["world_setting"]["用户世界观补充"]

                # 把用户自定义字段存入 world 顶层，供后续生成使用

                world["_user_custom"] = {k: v for k, v in custom.items() if v.strip()}

                return world

            except Exception:

                if attempt == 0:

                    continue  # 第一次失败，用精简 prompt 重试

                # 第二次也失败，回退到离线世界生成

                return world_from_title(cfg.title, custom)

        return world_from_title(cfg.title, custom)

    return world_from_title(cfg.title, custom)

def _fix_protagonist_in_plot(world: Dict[str, Any], old_name: str, new_name: str) -> None:

    """将 plot_framework 中所有出现旧主角名的地方替换为新主角名。



    在用户自定义主角姓名覆盖 LLM 生成的随机名之后调用，确保剧情档案中的名字一致。

    """

    if not old_name or not new_name or old_name == new_name:

        return

    plot = world.get("plot_framework", {})

    if not plot:

        return



    def _replace_in_value(value: Any) -> Any:

        if isinstance(value, str):

            return value.replace(old_name, new_name)

        if isinstance(value, list):

            return [v.replace(old_name, new_name) if isinstance(v, str) else v for v in value]

        return value



    # 剧情档案中所有可能引用主角姓名的字段

    name_keys = [

        "全书终极主线", "中期节点", "短期开局冲突",

        "当前未解决危机", "未来潜在大冲突",

    ]

    for key in name_keys:

        if key in plot:

            plot[key] = _replace_in_value(plot[key])



    # 多层伏笔库：可能是 dict（含短期/中期/长线伏笔列表）或扁平结构

    fb = plot.get("多层伏笔库", {})

    if isinstance(fb, dict):

        for sub_key in ("短期伏笔", "中期伏笔", "长线伏笔"):

            if sub_key in fb:

                fb[sub_key] = _replace_in_value(fb[sub_key])





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





def _save_user_config(cfg: NovelConfig, store: ProjectStore) -> None:

    """把用户自定义设定保存到 config.json，供后续续写时使用。"""

    config_path = store.dir / "config.json"

    existing = {}

    if config_path.exists():

        try:

            existing = json.loads(config_path.read_text(encoding="utf-8"))

        except Exception:

            pass

    # 保存用户自定义字段到 config

    custom_fields = {

        "protagonist": cfg.protagonist,

        "worldview": cfg.worldview,

        "opening": cfg.opening,

        "conflict": cfg.conflict,

        "direction": cfg.direction,

        "genre": cfg.genre,

        "style": cfg.style,

        "world": cfg.world,

        "rules": cfg.rules,

        "power": cfg.power,

        "forces": cfg.forces,

        "antagonist": cfg.antagonist,

        "side_characters": cfg.side_characters,

        "relations": cfg.relations,

        "taboos": cfg.taboos,

        "preferences": cfg.preferences,

    }

    existing.update({k: v for k, v in custom_fields.items() if v.strip()})

    existing["title"] = cfg.title

    existing["mode"] = cfg.mode

    existing["anti_ending"] = cfg.anti_ending

    existing["memory_inherit"] = cfg.memory_inherit

    existing["progression"] = cfg.progression

    existing["de_ai"] = cfg.de_ai

    existing["autosave"] = cfg.autosave

    config_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")





def create_project(cfg: NovelConfig, projects_root: Path) -> Dict[str, Any]:

    store = ProjectStore(projects_root, cfg.title)

    world = _build_world(cfg)

    world.setdefault("locked", True)

    store.write("world.json", world)

    store.write("char.json", _char_from_world(world))

    store.write("plot.json", _plot_from_world(world))

    # 保存用户自定义设定到 config.json

    _save_user_config(cfg, store)

    return {

        "title": cfg.title,

        "dir": str(store.dir),

        "world": world,

        "store": store,

    }





def load_project(title: str, projects_root: Path) -> Optional[ProjectStore]:
    """载入工程，先尝试精确名称，再尝试 safe_project_name。"""
    from pathlib import Path as _Path
    root = _Path(projects_root)
    # 先尝试精确匹配（Windows 非法字符会抛 OSError）
    try:
        exact = root / title
        if exact.exists() and exact.is_dir():
            return ProjectStore(projects_root, title)
    except OSError:
        pass
    # 再尝试 safe_project_name
    name = safe_project_name(title)
    dir_path = root / name
    if dir_path.exists() and dir_path.is_dir():
        return ProjectStore(projects_root, title)
    return None
def list_projects(projects_root: Path) -> list[str]:

    root = Path(projects_root)

    if not root.exists():

        return []

    return sorted([p.name for p in root.iterdir() if p.is_dir() and (p / "world.json").exists()])





def rename_project(old_title: str, new_title: str, projects_root: Path) -> Dict[str, Any]:

    """重命名工程。"""

    old_name = safe_project_name(old_title)

    new_name = safe_project_name(new_title)

    old_dir = Path(projects_root) / old_name

    new_dir = Path(projects_root) / new_name

    if not old_dir.exists():

        raise FileNotFoundError(f"工程不存在: {old_title}")

    if new_dir.exists():

        raise FileExistsError(f"目标名称已存在: {new_title}")

    old_dir.rename(new_dir)
    # ?? config.json ? title ??
    config_path = new_dir / "config.json"
    if config_path.exists():
        try:
            import json
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["title"] = new_title
            config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
    return {"old": old_title, "new": new_title, "dir": str(new_dir)}





def delete_project(title: str, projects_root: Path) -> None:

    """删除工程（含所有文件）。"""

    import shutil

    name = safe_project_name(title)

    dir_path = Path(projects_root) / name

    if not dir_path.exists():

        raise FileNotFoundError(f"工程不存在: {title}")

    shutil.rmtree(str(dir_path))









