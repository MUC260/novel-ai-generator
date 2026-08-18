"""命令行入口：新建、续写、查看、测试全部流程。"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .config import CHAPTER_CHOICES, WORD_TIERS, NovelConfig
from .generator import generate_chapters
from .project_manager import create_project, list_projects, load_project
from .storage import ProjectStore

PROJECTS_ROOT = Path.cwd() / "projects"


def _ask(prompt: str, default: str = "") -> str:
    try:
        val = input(prompt)
    except EOFError:
        val = ""
    return val.strip() or default


def _config_from_args(args: argparse.Namespace) -> NovelConfig:
    cfg = NovelConfig()
    cfg.title = args.title or _ask("小说名称：")
    if not cfg.title:
        raise SystemExit("小说名称不能为空")
    cfg.mode = args.mode or _ask("模式 auto=全自动 / custom=自定义 [auto]: ", "auto")
    cfg.genre = args.genre or ""
    cfg.style = args.style or ""
    cfg.world = args.world or ""
    cfg.rules = args.rules or ""
    cfg.power = args.power or ""
    cfg.forces = args.forces or ""
    cfg.protagonist = args.protagonist or ""
    cfg.side_characters = args.side_characters or ""
    cfg.antagonist = args.antagonist or ""
    cfg.opening = args.opening or ""
    cfg.conflict = args.conflict or ""
    cfg.relations = args.relations or ""
    cfg.direction = args.direction or ""
    cfg.taboos = args.taboos or ""
    cfg.preferences = args.preferences or ""
    # 开关可通过 --off 参数关闭，默认全部开启
    cfg.anti_ending = not args.no_anti_ending
    cfg.memory_inherit = not args.no_memory_inherit
    cfg.progression = not args.no_progression
    cfg.de_ai = not args.no_de_ai
    cfg.autosave = not args.no_autosave
    return cfg


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI 全自动无 AI 味超长连贯小说生成器")
    sub = parser.add_subparsers(dest="command")

    p_new = sub.add_parser("new", help="新建工程并连写")
    p_new.add_argument("--title")
    p_new.add_argument("--mode", choices=["auto", "custom"])
    p_new.add_argument("--chapters", type=int, choices=CHAPTER_CHOICES, default=1)
    p_new.add_argument("--tier", choices=list(WORD_TIERS), default="standard")
    p_new.add_argument("--genre")
    p_new.add_argument("--style")
    p_new.add_argument("--world")
    p_new.add_argument("--rules")
    p_new.add_argument("--power")
    p_new.add_argument("--forces")
    p_new.add_argument("--protagonist")
    p_new.add_argument("--side_characters")
    p_new.add_argument("--antagonist")
    p_new.add_argument("--opening")
    p_new.add_argument("--conflict")
    p_new.add_argument("--relations")
    p_new.add_argument("--direction")
    p_new.add_argument("--taboos")
    p_new.add_argument("--preferences")
    p_new.add_argument("--no-anti-ending", action="store_true")
    p_new.add_argument("--no-memory-inherit", action="store_true")
    p_new.add_argument("--no-progression", action="store_true")
    p_new.add_argument("--no-de-ai", action="store_true")
    p_new.add_argument("--no-autosave", action="store_true")

    p_con = sub.add_parser("continue", help="续写已有工程")
    p_con.add_argument("--project", required=True)
    p_con.add_argument("--chapters", type=int, choices=CHAPTER_CHOICES, default=1)
    p_con.add_argument("--tier", choices=list(WORD_TIERS), default="standard")
    p_con.add_argument("--no-anti-ending", action="store_true")
    p_con.add_argument("--no-memory-inherit", action="store_true")
    p_con.add_argument("--no-progression", action="store_true")
    p_con.add_argument("--no-de-ai", action="store_true")
    p_con.add_argument("--no-autosave", action="store_true")

    sub.add_parser("list", help="列出全部工程")
    p_inspect = sub.add_parser("inspect", help="查看工程存档")
    p_inspect.add_argument("--project", required=True)
    return parser


def _print_results(results, tier: str):
    low, high = WORD_TIERS[tier]
    print(f"\n生成完成：{len(results)} 章（目标 {low}-{high} 字/章）")
    for r in results:
        status = "OK" if low <= r["chars"] <= high else "!"
        print(f"  第 {r['chapter']:02d} 章 {r['chars']:>6} 字 {status}  {r['path']}")


def _run_new(args: argparse.Namespace):
    cfg = _config_from_args(args)
    if cfg.mode == "custom":
        print("自定义模式：以下内容可留空，留空由 AI 补全")
        cfg.genre = cfg.genre or _ask("  题材：")
        cfg.style = cfg.style or _ask("  文风：")
        cfg.world = cfg.world or _ask("  世界观/时代背景：")
        cfg.rules = cfg.rules or _ask("  世界规则：")
        cfg.power = cfg.power or _ask("  力量体系：")
        cfg.forces = cfg.forces or _ask("  势力分布：")
        cfg.protagonist = cfg.protagonist or _ask("  主角：")
        cfg.side_characters = cfg.side_characters or _ask("  配角：")
        cfg.antagonist = cfg.antagonist or _ask("  反派：")
        cfg.opening = cfg.opening or _ask("  开局剧情：")
        cfg.conflict = cfg.conflict or _ask("  当前矛盾：")
        cfg.relations = cfg.relations or _ask("  人物关系：")
        cfg.direction = cfg.direction or _ask("  剧情走向：")
        cfg.taboos = cfg.taboos or _ask("  禁忌内容：")
        cfg.preferences = cfg.preferences or _ask("  爽点/虐点偏好：")
    created = create_project(cfg, PROJECTS_ROOT)
    store: ProjectStore = created["store"]
    store.write("config.json", cfg.to_dict())
    results = generate_chapters(store, cfg, args.chapters, args.tier)
    print(f"工程已创建：{created['dir']}")
    _print_results(results, args.tier)


def _run_continue(args: argparse.Namespace):
    store = load_project(args.project, PROJECTS_ROOT)
    if store is None:
        raise SystemExit(f"未找到工程：{args.project}")
    saved = store.read("config.json") or {}
    cfg = NovelConfig(**{k: v for k, v in saved.items() if k in NovelConfig.__dataclass_fields__})
    cfg.title = args.project
    cfg.anti_ending = not args.no_anti_ending
    cfg.memory_inherit = not args.no_memory_inherit
    cfg.progression = not args.no_progression
    cfg.de_ai = not args.no_de_ai
    cfg.autosave = not args.no_autosave
    results = generate_chapters(store, cfg, args.chapters, args.tier)
    print(f"续写工程：{args.project}")
    _print_results(results, args.tier)


def _run_list(_: argparse.Namespace):
    names = list_projects(PROJECTS_ROOT)
    if not names:
        print("暂无工程")
        return
    print("全部工程：")
    for name in names:
        print(f"  - {name}")


def _run_inspect(args: argparse.Namespace):
    store = load_project(args.project, PROJECTS_ROOT)
    if store is None:
        raise SystemExit(f"未找到工程：{args.project}")
    snapshots = store.all_snapshots()
    for key, value in snapshots.items():
        print(f"\n===== {key}.json =====")
        print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: Optional[list] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        title = _ask("小说名称：")
        if not title:
            print("已退出")
            return 0
        mode = _ask("模式 auto=全自动 / custom=自定义 [auto]: ", "auto")
        try:
            chapters = int(_ask("生成章节数 1-15 [1]: ", "1") or "1")
        except ValueError:
            chapters = 1
        tier = _ask("字数档位 short/standard/long [standard]: ", "standard")
        args = argparse.Namespace(
            command="new", title=title, mode=mode, chapters=chapters, tier=tier,
            genre="", style="", world="", rules="", power="", forces="",
            protagonist="", side_characters="", antagonist="", opening="",
            conflict="", relations="", direction="", taboos="", preferences="",
            no_anti_ending=False, no_memory_inherit=False, no_progression=False,
            no_de_ai=False, no_autosave=False,
        )
        _run_new(args)
        return 0

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "new":
        _run_new(args)
    elif args.command == "continue":
        _run_continue(args)
    elif args.command == "list":
        _run_list(args)
    elif args.command == "inspect":
        _run_inspect(args)
    else:
        parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
