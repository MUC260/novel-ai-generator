# -*- coding: utf-8 -*-
import io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
from novel_ai.local_engine import world_from_title, LocalEngine
from novel_ai.wordcount import normalize
world = world_from_title("试炼之塔", {"protagonist": "司", "worldview": "仙魔大战千年后的人间，灵气枯竭，主角司是上古宗门的末代弟子，宗门覆灭后流落人间，靠给人修复法器为生。"})
print("主角:", world["character_list"][0]["姓名"])
print("主线:", world["plot_framework"]["全书终极主线"])
eng = LocalEngine("试炼之塔")
text = eng.generate_chapter(world, 1, 3, "short")
norm = normalize(text, "short").text
print("---开头300字---")
print(norm[:300])
paras = [p for p in norm.split("\n") if p.strip()]
print("段落数:", len(paras), "空行:", norm.count("\n\n"))
lens = [len(p) for p in paras]
print("长度范围:", min(lens), "-", max(lens))