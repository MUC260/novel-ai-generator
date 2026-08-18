import tempfile
import unittest
from pathlib import Path

from novel_ai.config import NovelConfig, WORD_TIERS
from novel_ai.filters import purify, has_ending
from novel_ai.generator import generate_chapters
from novel_ai.local_engine import world_from_title
from novel_ai.project_manager import create_project
from novel_ai.storage import ProjectStore
from novel_ai.wordcount import char_count, normalize


class WorldGenerationTests(unittest.TestCase):
    def test_world_schema(self):
        world = world_from_title("废土拾荒者")
        self.assertIn("world_setting", world)
        self.assertIn("power_system", world)
        self.assertIn("force_map", world)
        self.assertIn("character_list", world)
        self.assertIn("plot_framework", world)
        self.assertGreaterEqual(len(world["character_list"]), 3)
        self.assertTrue(world["locked"])

    def test_custom_priority(self):
        world = world_from_title("长夜将明", {"protagonist": "林默", "opening": "雪夜敲门"})
        self.assertEqual(world["character_list"][0]["姓名"], "林默")
        self.assertEqual(world["plot_framework"]["短期开局冲突"], "雪夜敲门")


class FilterTests(unittest.TestCase):
    def test_purify_removes_ai_phrases(self):
        text = "他不由得一时间想到，此事就此尘埃落定。"
        report = purify(text, remove_ai=True, forbid_ending=True)
        self.assertNotIn("不由得", report.cleaned_text)
        self.assertNotIn("一时间", report.cleaned_text)
        self.assertTrue(report.ending_hit)
        self.assertTrue(has_ending(text))

    def test_word_count(self):
        self.assertEqual(char_count("你好 世界\n"), 4)
        result = normalize("。" * 500, "short")
        self.assertFalse(result.ok)
        good = normalize("。" * 1500, "short")
        self.assertTrue(good.ok)


class ProjectAndGeneratorTests(unittest.TestCase):
    def test_create_and_generate_short(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cfg = NovelConfig(title="测试工程", mode="auto", autosave=True)
            created = create_project(cfg, root)
            store: ProjectStore = created["store"]
            results = generate_chapters(store, cfg, chapters=2, tier="short")
            self.assertEqual(len(results), 2)
            low, high = WORD_TIERS["short"]
            for r in results:
                self.assertGreaterEqual(r["chars"], low)
                self.assertLessEqual(r["chars"], high)
                self.assertTrue((store.chapters_dir / f"chapter_{r['chapter']:03d}.txt").exists())
            world = store.read("world.json")
            char = store.read("char.json")
            plot = store.read("plot.json")
            self.assertTrue(world["locked"])
            self.assertIn("characters", char)
            self.assertGreaterEqual(len(plot["events"]), 2)
            self.assertTrue((store.dir / "manuscript.txt").exists())
            tail = store.last_tail(500)
            self.assertTrue(tail)


if __name__ == "__main__":
    unittest.main()
