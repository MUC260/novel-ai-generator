# -*- coding: utf-8 -*-
"""测试：用户自定义主角姓名和世界观被正确遵循（v3.3 回归测试）。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from novel_ai.local_engine import world_from_title
from novel_ai.project_manager import _fix_protagonist_in_plot


class TestProtagonistOverride(unittest.TestCase):
    def test_world_from_title_uses_custom_protagonist(self):
        world = world_from_title("废土拾荒者", {"protagonist": "司", "worldview": "赛博朋克"})
        self.assertTrue(world["character_list"][0]["姓名"].startswith("司") and 2 <= len(world["character_list"][0]["姓名"]) <= 4, "单字姓应生成完整姓名")
        self.assertIn("司", world["plot_framework"].get("全书终极主线", ""))
        self.assertIn("司", world["plot_framework"].get("短期开局冲突", ""))
        self.assertEqual(world["world_setting"].get("用户世界观补充"), "赛博朋克")

    def test_world_from_title_backward_compatible(self):
        world = world_from_title("废土拾荒者", {})
        self.assertTrue(world["character_list"][0]["姓名"])

    def test_fix_protagonist_in_plot(self):
        w = {
            "character_list": [{"姓名": "林夜"}],
            "plot_framework": {
                "全书终极主线": "林夜调查废土真相",
                "短期开局冲突": "林夜被追杀",
                "当前未解决危机": ["林夜的妹妹失踪"],
                "中期节点": ["林夜找到线索"],
                "未来潜在大冲突": ["林夜vs组织"],
                "多层伏笔库": {"短期伏笔": ["林夜捡到的钥匙"], "中期伏笔": ["林夜的身世"]},
            },
        }
        _fix_protagonist_in_plot(w, "林夜", "司")
        plot = w["plot_framework"]
        self.assertEqual(plot["全书终极主线"], "司调查废土真相")
        self.assertEqual(plot["短期开局冲突"], "司被追杀")
        self.assertEqual(plot["当前未解决危机"], ["司的妹妹失踪"])
        self.assertEqual(plot["中期节点"], ["司找到线索"])
        self.assertEqual(plot["未来潜在大冲突"], ["司vs组织"])
        self.assertEqual(plot["多层伏笔库"]["短期伏笔"], ["司捡到的钥匙"])
        self.assertEqual(plot["多层伏笔库"]["中期伏笔"], ["司的身世"])



    def test_single_char_surname_generates_full_name(self):
        """单字姓应自动生成完整姓名"""
        world = world_from_title("废土拾荒者", {"protagonist": "司", "worldview": "赛博朋克"})
        name = world["character_list"][0]["姓名"]
        self.assertTrue(name.startswith("司"), f"姓名{name}应以司开头")
        self.assertGreaterEqual(len(name), 2, f"姓名{name}长度应>=2")
        # 确保 plot_framework 中也使用完整姓名
        framework = world.get("plot_framework", {})
        for key in ["全书终极主线", "短期开局冲突"]:
            val = framework.get(key, "")
            self.assertIn(name, val, f"plot_framework.{key}中应包含完整姓名{name}")


if __name__ == "__main__":
    unittest.main()