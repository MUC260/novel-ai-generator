"""Web 图形界面入口：直接运行 python webui.py 打开浏览器使用。"""
from __future__ import annotations
import argparse
import json
import urllib.parse
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

from novel_ai.config import NovelConfig, WORD_TIERS
from novel_ai.generator import generate_chapters, _generate_one, _update_archives, generate_outline, extract_memory_from_chapter, inject_memory_to_prompt, init_foreshadowing_tracker, update_foreshadowing_status, _json_snippet
from novel_ai.llm import LLMProvider
from novel_ai.settings import load_runtime_settings, save_runtime_settings, mask_api_key
from novel_ai.project_manager import (
    create_project,
    list_projects,
    load_project,
    rename_project,
    delete_project,
)
from novel_ai.storage import ProjectStore, safe_project_name
from novel_ai.wordcount import normalize as wc_normalize

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_ROOT = BASE_DIR / "projects"
STATIC_DIR = BASE_DIR / "web"
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)


def _log(*args: Any) -> None:
    if sys.stdout is not None:
        print(*args)


def _json_loads(raw: bytes) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("请求体不是有效 JSON")


def _load_cfg_from_config(store: ProjectStore) -> NovelConfig:
    config_data = store.read("config.json") or {}
    cfg = NovelConfig(title=config_data.get("title", store.title))
    for field in NovelConfig.__dataclass_fields__:
        if field in config_data:
            setattr(cfg, field, config_data[field])
    for bool_field in ["anti_ending", "memory_inherit", "progression", "de_ai", "autosave"]:
        if bool_field in config_data:
            setattr(cfg, bool_field, bool(config_data[bool_field]))
    return cfg


DEFAULT_MODELS = [
    "gpt-4o-mini", "gpt-4o", "gpt-4.1", "gpt-4.1-mini",
    "deepseek-chat", "deepseek-reasoner",
    "qwen-max", "qwen-plus",
    "MiniMax-M3", "MiniMax-M2.5-highspeed", "MiniMax-M2.7-highspeed",
    "MiniMax-M2.5", "MiniMax-M2.7",
]


def _settings_payload() -> Dict[str, Any]:
    """返回与 GET/POST /api/settings 相同的结构。"""
    provider = LLMProvider()
    rt = load_runtime_settings()
    has_runtime = any(str(rt.get(key) or "").strip() for key in ("base_url", "api_key", "model"))
    return {
        "ok": True,
        "base_url": provider.base_url,
        "model": provider.model,
        "api_key_set": provider.available,
        "api_key_masked": mask_api_key(provider.api_key),
        "source": "runtime" if has_runtime else "env",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "NovelWebUI/1.0"

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _error(self, status, message):
        self._json(status, {"ok": False, "error": message})

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        return _json_loads(self.rfile.read(length) if length else b"")

    def _cfg_from_body(self, body):
        cfg = NovelConfig()
        for field in NovelConfig.__dataclass_fields__:
            if field in body:
                setattr(cfg, field, body[field])
        cfg.title = str(cfg.title or "").strip()
        if not cfg.title:
            raise ValueError("小说名称不能为空")
        if cfg.mode not in ("auto", "custom"):
            cfg.mode = "auto"
        return cfg

    def _resolve_project_name(self, name):
        exact = PROJECTS_ROOT / name
        if exact.exists() and exact.is_dir():
            return name
        sanitized = safe_project_name(name)
        sp = PROJECTS_ROOT / sanitized
        if sp.exists() and sp.is_dir():
            return sanitized
        for d in PROJECTS_ROOT.iterdir():
            if d.is_dir() and (d / "world.json").exists():
                if d.name == name or d.name == sanitized:
                    return d.name
        raise FileNotFoundError(f"工程不存在: {name}")

    def _project_snapshots(self, name):
        dir_name = self._resolve_project_name(name)
        store = load_project(dir_name, PROJECTS_ROOT)
        if store is None:
            raise FileNotFoundError("工程不存在")
        snapshots = store.all_snapshots()
        config = store.read("config.json") or {}
        chapters = store.list_chapters()
        world = snapshots.get("world", {})
        custom_settings = {}
        user_custom = world.get("_user_custom", {})
        if user_custom:
            custom_settings.update(user_custom)
        for key in ["protagonist", "worldview", "opening", "conflict", "direction", "genre", "style"]:
            val = config.get(key, "") or user_custom.get(key, "")
            if val:
                custom_settings[key] = val
        return {
            "name": dir_name, "title": config.get("title", dir_name),
            "dir": str(store.dir),
            "config": config,
            "custom_settings": custom_settings,
            "world": world,
            "char": snapshots.get("char", {}),
            "plot": snapshots.get("plot", {}),
            "chapters": chapters,
            "tail": store.last_tail(500),
        }

    def _parse_query(self):
        qs = self.path.split("?", 1)[1] if "?" in self.path else ""
        result = {}
        if qs:
            for pair in qs.split(chr(38)):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    result[urllib.parse.unquote(k)] = urllib.parse.unquote(v)
        return result

    def _serve_static(self, path):
        rel = path[1:] if path.startswith("/") else path
        if rel == "":
            rel = "index.html"
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())):
            self._error(403, "禁止访问")
            return
        if not target.is_file():
            self._error(404, "页面不存在")
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send(200, target.read_bytes(), ctype)

    def _stream_header(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

    def _stream_chunk(self, obj):
        self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
        self.wfile.flush()

    def _stream_end(self):
        self.wfile.write(b"\n")

    def _make_progress_callback(self, chapter, total):
        """返回平滑的进度回调：按已用时间/预计时间推送，同时保留真实 token 进度。

        旧实现按 token/1500 估算且回调低频，导致进度条长时间不动；
        这里改为按生成耗时线性推进，每 1 秒推送一次，进度条平滑移动。
        """
        import time as _time_mod
        _start = [_time_mod.time()]  # 本章节开始生成的时间
        _last = [0.0]  # 上次推送时间
        _tokens = [0]  # 已收到 token 数
        _expected_secs = 30.0  # 单章预计耗时（秒），用于平滑估算

        def _on_token(text_fragment):
            _tokens[0] += 1
            now = _time_mod.time()
            # 每秒推送一次；首个 token 到达时立即推送，保证进度条马上动起来
            if now - _last[0] >= 1.0 or _tokens[0] == 1:
                _last[0] = now
                elapsed = max(0.0, now - _start[0])
                # 平滑估算：已用时间 / 预计单章时间，封顶 95（真实 100% 由章节完成事件给出）
                percent = min(95, round((elapsed / _expected_secs) * 100))
                # 保留真实 token 进度作为参考字段
                percent_real = min(99, round((_tokens[0] / 1500) * 100))
                self._stream_chunk({"type": "progress", "chapter": chapter, "total": total, "percent": percent, "percent_real": percent_real, "tokens": _tokens[0]})
        return _on_token

    def _generate_chapters_stream(self, cfg, chapters, tier, store, world, chars, plot, exist_count, project_label, memory_inherit=True):
        """统一章节生成流：/api/chapters/generate 与 /api/continue 共用同一循环。

        :param cfg: NovelConfig（含 autosave / memory_inherit 等设置）
        :param chapters: 本次要生成的章节总数
        :param tier: 字数档位
        :param store: ProjectStore
        :param world/chars/plot: 起始存档（memory_inherit=False 时 chars/plot 可为空 dict）
        :param exist_count: 已有章节数，新章节从 exist_count+1 开始
        :param project_label: 完成事件里用于工程快照的名称
        :param memory_inherit: 是否读取记忆/存档（决定是否带 char.json / plot.json / 上文 tail）
        """
        self._stream_header()
        results = []
        for i in range(1, chapters + 1):
            ch_no = exist_count + i
            self._stream_chunk({"type": "progress", "chapter": ch_no, "total": chapters, "percent": round((i - 1) / chapters * 100)})
            try:
                tail = store.last_tail(500) if memory_inherit else ""
                text = _generate_one(cfg, ch_no, chapters, tier, world, chars, plot, tail, on_progress=self._make_progress_callback(ch_no, chapters))
                self._stream_chunk({"type": "progress", "chapter": ch_no, "total": chapters, "percent": min(99, round((i - 0.3) / chapters * 100))})
                text = wc_normalize(text, tier).text
                store = load_project(cfg.title, PROJECTS_ROOT) or store
                store.append_chapter(ch_no, text)
                if cfg.autosave:
                    _update_archives(store, ch_no, text, chapters)
                world, chars, plot = store.read("world.json"), store.read("char.json"), store.read("plot.json")
                chars_count = len("".join(text.split()))
                results.append({"chapter": ch_no, "text": text, "chars": chars_count})
                self._stream_chunk({"type": "chapter", "chapter": ch_no, "total": chapters, "text": text, "chars": chars_count})
                self._stream_chunk({"type": "progress", "chapter": ch_no, "total": chapters, "percent": min(100, round(i / chapters * 100))})
            except Exception as exc:
                self._stream_chunk({"type": "error", "chapter": ch_no, "total": chapters, "error": str(exc)})
        self._stream_chunk({"type": "done", "project": self._project_snapshots(project_label), "results": results, "message": "全部生成完成！"})
        self._stream_end()
        return results


    def do_GET(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            if path == "/api/health":
                provider = LLMProvider()
                self._json(200, {
                    "ok": True,
                    "model": provider.model,
                    "base_url": provider.base_url,
                    "api_key_set": provider.available,
                    "configured": provider.available,
                    "status": "configured" if provider.available else "no_key",
                })
                return
            if path == "/api/settings":
                self._json(200, _settings_payload())
                return
            if path == "/api/models":
                provider = LLMProvider()
                models = provider.list_models() or DEFAULT_MODELS
                self._json(200, {"ok": True, "models": models})
                return
            if path == "/api/projects":
                self._json(200, {"ok": True, "projects": list_projects(PROJECTS_ROOT)})
                return
            if path == "/api/project":
                name = self._parse_query().get("name", "")
                if not name:
                    self._error(400, "需要 name 参数")
                    return
                self._json(200, {"ok": True, "project": self._project_snapshots(name)})
                return
            if path == "/api/project/stats":
                name = self._parse_query().get("name", "")
                if not name:
                    self._error(400, "需要 name 参数")
                    return
                snap = self._project_snapshots(name)
                chapters = snap.get("chapters", [])
                total_chars = sum(c.get("chars", 0) for c in chapters)
                chars = snap.get("char", {})
                chars_count = len(chars.get("characters", []))
                self._json(200, {"ok": True, "stats": {
                    "chapters": chapters,
                    "total_chars": total_chars,
                    "avg_chars": total_chars // max(1, len(chapters)),
                    "chars_count": chars_count,
                }})
                return
            if path == "/api/project/book":
                name = self._parse_query().get("name", "")
                if not name:
                    self._error(400, "需要 name 参数")
                    return
                dir_name = self._resolve_project_name(name)
                store = load_project(dir_name, PROJECTS_ROOT)
                if store is None:
                    self._error(404, "工程不存在")
                    return
                chapters = store.list_chapters()
                book_chapters = []
                for ch in chapters:
                    path_obj = Path(ch["path"])
                    if path_obj.exists():
                        text = path_obj.read_text(encoding="utf-8")
                    else:
                        text = ""
                    book_chapters.append({"title": ch["name"], "text": text})
                world_data = store.read("world.json") or {}
                total_chars_var = sum(len("".join(c["text"].split())) for c in book_chapters)
                self._json(200, {"ok": True, "book": {"name": name, "chapters": book_chapters, "genre": world_data.get("genre", ""), "style": world_data.get("style", ""), "total_chars": total_chars_var}})
                return
            if path == "/api/project/export":
                name = self._parse_query().get("name", "")
                if not name:
                    self._error(400, "需要 name 参数")
                    return
                dir_name = self._resolve_project_name(name)
                store = load_project(dir_name, PROJECTS_ROOT)
                if store is None:
                    self._error(404, "工程不存在")
                    return
                text = store.export_as_text()
                self._json(200, {"ok": True, "text": text})
                return
            if path == "/api/chapter":
                q = self._parse_query()
                project = q.get("project", "")
                if not project:
                    self._error(400, "需要 project 参数")
                    return
                dir_name = self._resolve_project_name(project)
                store = load_project(dir_name, PROJECTS_ROOT)
                if store is None:
                    self._error(404, "工程不存在")
                    return
                chapter = q.get("chapter", "")
                index_str = q.get("index", "")
                if index_str:
                    try:
                        idx = int(index_str)
                        if idx < 1 or idx > 9999:
                            raise ValueError("index 超出范围")
                    except (ValueError, TypeError):
                        self._error(400, "index 参数必须是有效的数字")
                        return
                    f = store.chapters_dir / f"chapter_{idx:03d}.txt"
                elif chapter:
                    # 安全校验：只允许 chapter_xxx.txt 格式，禁止路径穿越
                    if not chapter.startswith("chapter_") or not chapter.endswith(".txt"):
                        self._error(400, "chapter 参数格式无效")
                        return
                    # 进一步白名单：只允许 chapter_ 后跟数字
                    stem = chapter.replace(".txt", "").replace("chapter_", "")
                    if not stem.isdigit():
                        self._error(400, "chapter 参数格式无效")
                        return
                    f = store.chapters_dir / chapter
                else:
                    self._error(400, "需要 chapter 或 index 参数")
                    return
                # 确保路径在 chapters_dir 内
                try:
                    f = f.resolve()
                    if not str(f).startswith(str(store.chapters_dir.resolve())):
                        self._error(400, "路径不合法")
                        return
                except Exception:
                    self._error(400, "路径解析失败")
                    return
                if not f.exists():
                    self._error(404, "章节文件不存在")
                    return
                self._json(200, {"ok": True, "text": f.read_text(encoding="utf-8")})
                return
            if path.startswith("/api/"):
                self._error(404, "接口不存在")
                return
            self._serve_static(path)
        except Exception as exc:
            self._error(500, str(exc))

    def do_POST(self):
        path = self.path.split("?", 1)[0].rstrip("/")
        try:
            body = self._read_body()
            if path == "/api/settings":
                if body.get("clear_api_key"):
                    # 恢复默认(.env)：清空全部运行时覆盖，回退 .env
                    save_runtime_settings({})
                    self._json(200, _settings_payload())
                    return
                rt = load_runtime_settings()
                api_key = body.get("api_key")
                if isinstance(api_key, str) and api_key.strip():
                    rt["api_key"] = api_key.strip()
                for field in ("base_url", "model"):
                    value = body.get(field)
                    if isinstance(value, str) and value.strip():
                        rt[field] = value.strip()
                save_runtime_settings(rt)
                self._json(200, _settings_payload())
                return
            if path == "/api/world/generate":
                cfg = self._cfg_from_body(body)
                for field in ["anti_ending", "memory_inherit", "progression", "de_ai", "autosave"]:
                    if field in body:
                        setattr(cfg, field, bool(body[field]))
                created = create_project(cfg, PROJECTS_ROOT)
                snapshots = self._project_snapshots(cfg.title)
                self._json(200, {"ok": True, "project": snapshots})
                return
            if path == "/api/chapters/generate":
                cfg = self._cfg_from_body(body)
                chapters = int(body.get("chapters", 1))
                tier = str(body.get("tier", "standard"))
                if tier not in WORD_TIERS:
                    tier = "standard"
                chapters = max(1, min(15, chapters))
                store = load_project(cfg.title, PROJECTS_ROOT)
                if store is None:
                    raise ValueError(f"工程不存在或创建失败: {cfg.title}")
                world = store.read("world.json") if store else {}
                chars = store.read("char.json") if store else {}
                plot = store.read("plot.json") if store else {}
                exist_count = len(store.list_chapters()) if store else 0
                self._generate_chapters_stream(cfg, chapters, tier, store, world, chars, plot, exist_count, cfg.title)
                return
            if path == "/api/continue":
                name = str(body.get("project", "")).strip()
                if not name:
                    self._error(400, "需要 project 名称")
                    return
                dir_name = self._resolve_project_name(name)
                store = load_project(dir_name, PROJECTS_ROOT)
                if store is None:
                    self._error(404, "工程不存在")
                    return
                cfg = _load_cfg_from_config(store)
                for field in ["anti_ending", "memory_inherit", "progression", "de_ai", "autosave"]:
                    if field in body:
                        setattr(cfg, field, bool(body[field]))
                chapters = int(body.get("chapters", 1))
                tier = str(body.get("tier", "standard"))
                if tier not in WORD_TIERS:
                    tier = "standard"
                chapters = max(1, min(15, chapters))
                exist_count = len(store.list_chapters())
                world = store.read("world.json")
                chars = store.read("char.json") if cfg.memory_inherit else {}
                plot = store.read("plot.json") if cfg.memory_inherit else {}
                self._generate_chapters_stream(cfg, chapters, tier, store, world, chars, plot, exist_count, dir_name, memory_inherit=cfg.memory_inherit)
                return
            if path == "/api/create":
                cfg = self._cfg_from_body(body)
                for field in ["anti_ending", "memory_inherit", "progression", "de_ai", "autosave"]:
                    if field in body:
                        setattr(cfg, field, bool(body[field]))
                created = create_project(cfg, PROJECTS_ROOT)
                snapshots = self._project_snapshots(cfg.title)
                self._json(200, {"ok": True, "project": snapshots})
                return
            if path == "/api/outline/generate":
                name = str(body.get("name", "")).strip()
                chapters = int(body.get("chapters", 5))
                tier = str(body.get("tier", "standard"))
                if tier not in WORD_TIERS:
                    tier = "standard"
                chapters = max(1, min(15, chapters))
                store = load_project(name, PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                cfg = _load_cfg_from_config(store)
                world = store.read("world.json")
                chars = store.read("char.json") if cfg.memory_inherit else {}
                plot = store.read("plot.json") if cfg.memory_inherit else {}
                outline = generate_outline(cfg, chapters, tier, world, chars, plot)
                store.write("outline.json", outline)
                self._json(200, {"ok": True, "outline": outline})
                return
            if path == "/api/outline/get":
                name = str(body.get("name", "")).strip()
                store = load_project(name, PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                outline = store.read("outline.json") or {}
                self._json(200, {"ok": True, "outline": outline})
                return
            if path == "/api/outline/save":
                name = str(body.get("name", "")).strip()
                outline = body.get("outline", {})
                store = load_project(name, PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                store.write("outline.json", outline)
                self._json(200, {"ok": True})
                return
            if path == "/api/project/archives":
                name = str(body.get("name", "")).strip()
                if not name:
                    raise ValueError("工程名称不能为空")
                store = load_project(name, PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                if "world" in body and body["world"]:
                    store.write("world.json", body["world"])
                if "char" in body and body["char"]:
                    store.write("char.json", body["char"])
                if "plot" in body and body["plot"]:
                    store.write("plot.json", body["plot"])
                self._json(200, {"ok": True})
                return
            if path == "/api/chapter/revise":
                name = str(body.get("project", "")).strip()
                index = int(body.get("index", 0))
                instructions = str(body.get("instructions", "")).strip()
                if not instructions:
                    raise ValueError("修改意见不能为空")
                store = load_project(name, PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                cfg = _load_cfg_from_config(store)
                world = store.read("world.json")
                chars = store.read("char.json") if cfg.memory_inherit else {}
                plot = store.read("plot.json") if cfg.memory_inherit else {}
                chapters = store.list_chapters()
                chapter_info = None
                for ch in chapters:
                    if ch["index"] == index:
                        chapter_info = ch
                        break
                if chapter_info is None:
                    raise FileNotFoundError(f"章节 {index} 不存在")
                file_path = store.chapters_dir / f"chapter_{index:03d}.txt"
                original_text = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
                if not original_text:
                    raise ValueError(f"章节文件为空: chapter_{index:03d}.txt")
                tail = store.last_tail(500) if cfg.memory_inherit else ""
                llm = LLMProvider()
                prompt = f"""你是一位资深小说编辑。请根据以下修改意见，修订指定章节。

小说：{name}
当前章节：第 {index} 章

修改意见：{instructions}

原章节内容：
{original_text}

请直接输出修订后的完整章节内容，不要输出任何解释。"""
                revised = llm.chat([{"role": "user", "content": prompt}], max_tokens=8000, temperature=0.7)
                file_path.write_text(revised, encoding="utf-8")
                store._rebuild_manuscript()
                self._json(200, {"ok": True, "text": revised, "original": original_text})
                return
            if path == "/api/chapter/delete":
                project = str(body.get("project", "")).strip()
                index = int(body.get("index", 0))
                store = load_project(project, PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                ok = store.delete_chapter(index)
                self._json(200, {"ok": ok})
                return
            if path == "/api/project/rename":
                old = str(body.get("old", "")).strip()
                new = str(body.get("new", "")).strip()
                if not old or not new:
                    raise ValueError("旧名称和新名称不能为空")
                result = rename_project(old, new, PROJECTS_ROOT)
                self._json(200, {"ok": True, "result": result})
                return
            if path == "/api/project/delete":
                name = str(body.get("name", "")).strip()
                if not name:
                    raise ValueError("工程名称不能为空")
                delete_project(name, PROJECTS_ROOT)
                self._json(200, {"ok": True})
                return
            if path == "/api/test":
                provider = LLMProvider()
                if provider.available:
                    reply = provider.test()
                    self._json(200, {"ok": True, "reply": reply[:200]})
                else:
                    self._json(200, {"ok": True, "reply": "离线模式，无需测试"})
                return
            self._error(404, "接口不存在")
        except Exception as exc:
            self._error(500, str(exc))

    def log_message(self, format, *args):
        _log(f"[{self.log_date_time_string()}] {format % args}")


def main():
    parser = argparse.ArgumentParser(description="小说生成器 Web 界面")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    _log(f"小说生成器 Web 界面已启动：{url}")
    _log("按 Ctrl+C 停止服务")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _log("\n已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

