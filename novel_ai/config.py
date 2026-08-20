"""全部可选择参数体系、默认开关、档位与题材文风库。"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict

from typing import Dict, List



CHAPTER_CHOICES = list(range(1, 16))



GENRES = [

    "玄幻修仙", "现代都市", "现实悲情", "末世废土", "硬核科幻",

    "悬疑惊悚", "灵异克制", "古风权谋", "校园现实", "赛博朋克",

]



STYLES = [

    "冷峻写实", "压抑悲凉", "暗黑残酷", "热血高燃", "平淡治愈",

    "阴郁克制", "悲壮现实", "轻松日常", "悬疑深沉",

]



# 三档精准锁字：名称 -> (最低字数, 最高字数)

WORD_TIERS = {

    "short": (1000, 2000),

    "standard": (3000, 4000),

    "long": (9000, 11000),

}



TIER_LABELS = {

    "short": "日常短章",

    "standard": "标准连载章",

    "long": "超长大剧情爆发章",

}



@dataclass

class NovelConfig:

    title: str = ""

    mode: str = "auto"  # auto | custom

    genre: str = ""

    style: str = ""

    world: str = ""

    rules: str = ""

    power: str = ""

    forces: str = ""

    protagonist: str = ""

    side_characters: str = ""

    antagonist: str = ""

    opening: str = ""

    conflict: str = ""

    relations: str = ""

    direction: str = ""

    taboos: str = ""

    preferences: str = ""

    worldview: str = ""  # 世界观一句话描述/额外设定，用户选填，供 AI 与离线引擎作依据



    # 五大高级功能开关

    anti_ending: bool = True

    memory_inherit: bool = True

    progression: bool = True

    de_ai: bool = True

    autosave: bool = True



    def custom_filled(self) -> List[str]:

        """返回用户已填写的自定义字段名。"""

        keys = [

            "genre", "style", "world", "rules", "power", "forces",

            "protagonist", "side_characters", "antagonist", "opening",

            "conflict", "relations", "direction", "taboos", "preferences", "worldview",

        ]

        return [k for k in keys if str(getattr(self, k, "")).strip()]



    def to_dict(self) -> Dict:

        return asdict(self)

