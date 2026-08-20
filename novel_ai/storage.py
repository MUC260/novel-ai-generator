"""三大永久本地存档系统：原子写入、读取与路径安全。"""

from __future__ import annotations

import json

import os

from pathlib import Path

from typing import Any, Dict, List





def safe_project_name(name: str) -> str:

    """把书名转成安全的目录名。"""

    bad = '<>:"/\\|?*'

    out = []

    for ch in name.strip():

        if ch in bad or ord(ch) < 32:

            out.append("_")

        else:

            out.append(ch)

    cleaned = "".join(out).strip().rstrip(".")

    return cleaned or "未命名工程"





class ProjectStore:

    def __init__(self, projects_root: Path, title: str):

        self.root = Path(projects_root)

        self.dir = self.root / safe_project_name(title)

        self.chapters_dir = self.dir / "chapters"

        self.chapters_dir.mkdir(parents=True, exist_ok=True)

        for fname in ("world.json", "char.json", "plot.json"):

            p = self.dir / fname

            if not p.exists():

                self._atomic_write(p, self._default_for(fname))

        self.title = title



    @staticmethod

    def _default_for(fname: str) -> Dict[str, Any]:

        if fname == "world.json":

            return {

                "world_setting": {},

                "power_system": {},

                "force_map": [],

                "character_list": [],

                "plot_framework": {},

                "style": "",

                "genre": "",

                "locked": True,

            }

        if fname == "char.json":

            return {"characters": [], "relations": [], "updated_at": ""}

        return {

            "events": [],

            "short_arcs": [],

            "mid_arcs": [],

            "long_arcs": [],

            "crises": [],

            "main_progress": "",

            "side_progress": [],

            "current_tension": "",

            "pending_conflicts": [],

        }



    @staticmethod

    def _atomic_write(path: Path, data: Any) -> None:

        tmp = path.with_suffix(path.suffix + ".tmp")

        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        os.replace(tmp, path)



    def read(self, fname: str) -> Dict[str, Any]:

        path = self.dir / fname

        try:

            return json.loads(path.read_text(encoding="utf-8"))

        except Exception:

            return {}



    def write(self, fname: str, data: Any) -> None:

        self._atomic_write(self.dir / fname, data)



    def all_snapshots(self) -> Dict[str, Any]:

        return {

            "world": self.read("world.json"),

            "char": self.read("char.json"),

            "plot": self.read("plot.json"),

        }



    def append_chapter(self, index: int, text: str) -> Path:

        path = self.chapters_dir / f"chapter_{index:03d}.txt"

        path.write_text(text, encoding="utf-8")

        manuscript = self.dir / "manuscript.txt"

        prev = ""

        if manuscript.exists():

            prev = manuscript.read_text(encoding="utf-8")

            if prev and not prev.endswith("\n"):

                prev += "\n"

        manuscript.write_text(prev + text + "\n\n", encoding="utf-8")

        return path



    def last_tail(self, chars: int = 500) -> str:

        """防割裂：只读取末尾 N 字承接画面，不全文塞入上下文。"""

        manuscript = self.dir / "manuscript.txt"

        if not manuscript.exists():

            return ""

        text = manuscript.read_text(encoding="utf-8")

        text = text.strip()

        if not text:

            return ""

        if len(text) <= chars:

            return text

        return "……" + text[-chars:]





    def save_memory(self, data: Dict[str, Any]) -> None:

        """持久化叙事记忆/上下文压缩数据到 memory.json。"""

        self._atomic_write(self.dir / "memory.json", data)



    def load_memory(self) -> Dict[str, Any]:

        """从 memory.json 加载叙事记忆/上下文压缩数据。"""

        path = self.dir / "memory.json"

        try:

            return json.loads(path.read_text(encoding="utf-8"))

        except Exception:

            return {}



    def delete_chapter(self, chapter_index: int) -> bool:

        """删除指定章节文件。"""

        path = self.chapters_dir / f"chapter_{chapter_index:03d}.txt"

        if not path.exists():

            return False

        path.unlink()

        # 重建 manuscript.txt

        self._rebuild_manuscript()

        return True



    def list_chapters(self) -> List[Dict[str, Any]]:

        """列出所有章节。"""

        if not self.chapters_dir.exists():

            return []

        result = []

        for p in sorted(self.chapters_dir.glob("chapter_*.txt")):

            text = p.read_text(encoding="utf-8")

            result.append({

                "file": p.name,

                "name": "第 " + str(int(p.stem.split("_")[1])) + " 章",

                "path": str(p),

                "index": int(p.stem.split("_")[1]),

                "chars": len("".join(text.split())),

                "lines": text.count(chr(10)),

            })

        return result



    def _rebuild_manuscript(self) -> None:

        """从所有章节文件重建 manuscript.txt。"""

        manuscript = self.dir / "manuscript.txt"

        parts = []

        for p in sorted(self.chapters_dir.glob("chapter_*.txt")):

            parts.append(p.read_text(encoding="utf-8"))

        manuscript.write_text("\n\n".join(parts) + ("\n" if parts else ""), encoding="utf-8")



    def export_as_text(self) -> str:

        """导出工程为纯文本（含标题和章节）。"""

        lines = []

        lines.append(f"=== {self.title} ===")

        lines.append("")

        snap = self.all_snapshots()

        w = snap.get("world", {})

        lines.append(f"题材: {w.get('genre', '未设定')}  文风: {w.get('style', '未设定')}")

        lines.append("")

        for p in sorted(self.chapters_dir.glob("chapter_*.txt")):

            text = p.read_text(encoding="utf-8")

            ch = p.stem.replace("chapter_", "第 ").replace("_", " 章")

            lines.append(f"--- {ch} ---")

            lines.append(text)

            lines.append("")

        return "\n".join(lines)





