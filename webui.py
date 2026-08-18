"""Web 图形界面入口：直接运行 python webui.py 打开浏览器使用。"""
from __future__ import annotations
import argparse
import json
import mimetypes
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from novel_ai.config import NovelConfig, WORD_TIERS
from novel_ai.generator import generate_chapters
from novel_ai.llm import LLMProvider
from novel_ai.project_manager import create_project, list_projects, load_project
from novel_ai.storage import ProjectStore

BASE_DIR = Path(__file__).resolve().parent
PROJECTS_ROOT = BASE_DIR / "projects"
STATIC_DIR = BASE_DIR / "web"
PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)


def _json_loads(raw: bytes) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        raise ValueError("请求体不是有效 JSON")


class Handler(BaseHTTPRequestHandler):
    server_version = "NovelWebUI/1.0"

    def _send(self, status: int, body: bytes, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def _read_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return _json_loads(self.rfile.read(length) if length else b"")

    def _cfg_from_body(self, body: Dict[str, Any]) -> NovelConfig:
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

    def _project_snapshots(self, name: str) -> Dict[str, Any]:
        store = load_project(name, PROJECTS_ROOT)
        if store is None:
            raise FileNotFoundError("工程不存在")
        snapshots = store.all_snapshots()
        config = store.read("config.json") or {}
        chapters = []
        if store.chapters_dir.exists():
            for p in sorted(store.chapters_dir.glob("chapter_*.txt")):
                chapters.append({
                    "file": p.name,
                    "name": p.name,
                    "chars": len("".join(p.read_text(encoding="utf-8").split())),
                })
        return {
            "name": name,
            "dir": str(store.dir),
            "config": config,
            "world": snapshots.get("world", {}),
            "char": snapshots.get("char", {}),
            "plot": snapshots.get("plot", {}),
            "chapters": chapters,
            "tail": store.last_tail(500),
        }

    def _serve_static(self, path: str) -> None:
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

    def do_GET(self) -> None:
        try:
            path = self.path.split("?", 1)[0]
            if not path.startswith("/api/"):
                self._serve_static(path if path != "/" else "/index.html")
                return
            if path == "/api/projects":
                self._json(200, {"ok": True, "projects": list_projects(PROJECTS_ROOT)})
                return
            if path == "/api/project":
                qs = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(x.split("=", 1) for x in qs.split("&") if "=" in x)
                name = params.get("name", "")
                self._json(200, {"ok": True, "project": self._project_snapshots(name)})
                return
            if path == "/api/chapter":
                qs = self.path.split("?", 1)[1] if "?" in self.path else ""
                params = dict(x.split("=", 1) for x in qs.split("&") if "=" in x)
                store = load_project(params.get("project", ""), PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                chapter = params.get("chapter", "")
                f = store.chapters_dir / chapter
                if not f.exists():
                    raise FileNotFoundError("章节不存在")
                self._json(200, {"ok": True, "chapter": f.read_text(encoding="utf-8")})
                return
            if path == "/api/health":
                llm = LLMProvider()
                self._json(200, {"ok": True, "llm": llm.available, "model": llm.model, "base_url": llm.base_url})
                return
            self._error(404, "接口不存在")
        except Exception as exc:
            self._error(500, str(exc))

    def do_POST(self) -> None:
        try:
            path = self.path.split("?", 1)[0]
            body = self._read_body()
            if path == "/api/test":
                llm = LLMProvider()
                if not llm.available:
                    raise RuntimeError("未配置 API Key")
                reply = llm.test()
                self._json(200, {"ok": True, "reply": reply})
                return
            if path == "/api/create":
                cfg = self._cfg_from_body(body)
                chapters = int(body.get("chapters", 1))
                tier = str(body.get("tier", "standard"))
                if tier not in WORD_TIERS:
                    tier = "standard"
                chapters = max(1, min(15, chapters))
                created = create_project(cfg, PROJECTS_ROOT)
                store: ProjectStore = created["store"]
                store.write("config.json", cfg.to_dict())
                results = generate_chapters(store, cfg, chapters, tier)
                self._json(200, {
                    "ok": True,
                    "project": self._project_snapshots(cfg.title),
                    "results": results,
                })
                return
            if path == "/api/continue":
                name = str(body.get("project", "")).strip()
                store = load_project(name, PROJECTS_ROOT)
                if store is None:
                    raise FileNotFoundError("工程不存在")
                saved = store.read("config.json") or {}
                cfg = NovelConfig(**{k: v for k, v in saved.items() if k in NovelConfig.__dataclass_fields__})
                cfg.title = name
                for field in ["anti_ending", "memory_inherit", "progression", "de_ai", "autosave"]:
                    if field in body:
                        setattr(cfg, field, bool(body[field]))
                chapters = int(body.get("chapters", 1))
                tier = str(body.get("tier", "standard"))
                if tier not in WORD_TIERS:
                    tier = "standard"
                chapters = max(1, min(15, chapters))
                results = generate_chapters(store, cfg, chapters, tier)
                self._json(200, {
                    "ok": True,
                    "project": self._project_snapshots(name),
                    "results": results,
                })
                return
            self._error(404, "接口不存在")
        except Exception as exc:
            self._error(500, str(exc))

    def log_message(self, format: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description="小说生成器 Web 界面")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"小说生成器 Web 界面已启动：{url}")
    print("按 Ctrl+C 停止服务")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
