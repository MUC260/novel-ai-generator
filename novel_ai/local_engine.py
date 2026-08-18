"""离线演示引擎：用于无 API 环境下的流程验证、存档验证、字数验证。"""
from __future__ import annotations
import hashlib
import json
import random
from typing import Any, Dict, List, Tuple

from .config import GENRES, STYLES
from .wordcount import char_count, trim_to, WORD_TIERS

# 避免 AI 套话的短句模板，全部由动作、对话、感官推进。
ACTIONS = [
    "他{action}，眼睛没离开{target}。",
    "{name}把{target}推到一边，指节按得发白。",
    "门外传来{noise}，屋里的人都没动。",
    "{name}压着声音说：“{line}”",
    "对方盯着他，半晌才接了一句：“{line2}”",
    "墙上的{object}裂开一道细纹，灰尘簌簌往下落。",
    "{name}往后退了半步，后背撞在{object}上。",
    "风从破口灌进来，{name}的衣摆被吹得紧贴身体。",
    "他抬手抹掉脸上的{fluid}，脚步没停。",
    "远处{scene}，像有人从黑暗里慢慢逼过来。",
    "{name}没说话，只把{weapon}握得更紧。",
    "地上留着{mark}，一直延伸到{place}。",
    "“{line}”{name}重复了一遍，嗓子发紧。",
    "有人从{place}探出半个身子，又缩了回去。",
    "{name}转过头，看见{target}正在{verb}。",
    "他的呼吸很重，一下一下，像把胸腔里的气往外挤。",
    "门被推开一条缝，{noise}先钻了进来。",
    "{name}盯着{target}，没接话，脚底慢慢往后挪。",
    "“别动。”声音从{place}传出来，带着{texture}。",
    "{object}滚到墙边，发出{noise}。",
]
ACTION_WORDS = ["侧身", "停住", "弯腰", "抬头", "咬紧牙", "绷着肩", "压低身子", "攥住衣角"]
TARGETS = ["门缝", "楼梯口", "桌上的信", "那个人", "街角", "窗框", "巷子深处", "地上的影子"]
NOISES = ["细碎脚步声", "金属摩擦声", "一声闷响", "急促敲击", "风吹木板声", "若有若无的咳嗽"]
LINES = [
    "这事没完", "你最好没骗我", "别跟过来", "他们已经到了", "再等下去人都没了",
    "把东西放下", "我不会交出去", "你先走", "谁报的信", "门别锁",
]
LINES2 = ["轮不到你教我", "我只看结果", "那就都别走", "你心里清楚", "晚了", "先活过今晚"]
OBJECTS = ["旧柜子", "铁皮门", "木箱", "灯架", "半截楼梯", "玻璃窗", "石墙", "货架"]
FLUIDS = ["血", "泥水", "雨水", "汗", "灰"]
SCENES = ["警笛声混在风里", "有光从楼顶扫过去", "人群正在散开", "黑烟贴着屋檐升起来", "什么东西在水面翻动"]
WEAPONS = ["刀柄", "铁管", "绳头", "木板", "枪把", "钥匙"]
MARKS = ["一串湿脚印", "拖痕", "散落的纸片", "断掉的鞋带", "几滴暗红", "一道划痕"]
PLACES = ["后门", "楼梯拐角", "柜台底下", "桥洞", "天台", "地下室", "巷子口", "站台"]
VERBS = ["翻东西", "数钱", "套衣服", "拨电话", "抄近路", "藏箱子", "拆封条"]
TEXTURES = ["沙哑", "冷", "发紧", "低", "不耐烦", "嘲弄"]

OPEN_ENDINGS = [
    "他没再说话，抬脚朝{place}走。后面的{noise}追着鞋跟响起来。",
    "{name}盯着{target}，刚迈出一步，{target}那头的灯突然灭了。",
    "“事情还没完。”{name}说完把{object}拎起来，转身往{place}走。",
    "风把门拍在墙上。{name}没躲，只听见{place}传来新的{noise}。",
    "{name}停在{place}前，身后{noise}越来越近。他没有回头。",
    "远处{scene}，{name}的手指在{weapon}上收紧。",
    "门从外面被顶了一下，{noise}贴着木板传进来。{name}没动。",
    "{name}把{object}踢到一边，刚要看{target}，脚下的{mark}又多了一道。",
]

# 开篇首句库，直接切入现场
OPENING_LINES = [
    "{name}醒过来的时候，{place}外面的{noise}已经停了。",
    "“把手举起来。”{name}还没看清说话的人，{noise}就先到了。",
    "雨从{place}漏下来，落在{name}后颈上，凉得他肩膀一缩。",
    "{name}是在{place}被堵住的，前后都有人。",
    "门被撞开时，{name}刚把{object}塞进怀里。",
]


def _seed_from(title: str) -> int:
    h = hashlib.sha256(title.encode("utf-8")).hexdigest()
    return int(h[:12], 16)


def _pick_genre(title: str, custom: Dict[str, str]) -> str:
    if custom.get("genre", "").strip():
        return custom["genre"].strip()
    keyword_map = {
        "废土": "末世废土", "末世": "末世废土", "仙": "玄幻修仙", "修": "玄幻修仙",
        "都": "现代都市", "城": "现代都市", "赛博": "赛博朋克", "科幻": "硬核科幻",
        "惊悚": "悬疑惊悚", "悬疑": "悬疑惊悚", "灵异": "灵异克制", "鬼": "灵异克制",
        "校园": "校园现实", "悲": "现实悲情", "权谋": "古风权谋", "宫": "古风权谋",
    }
    for key, genre in keyword_map.items():
        if key in title:
            return genre
    rng = random.Random(_seed_from(title))
    return rng.choice(GENRES)


def _pick_style(title: str, custom: Dict[str, str]) -> str:
    if custom.get("style", "").strip():
        return custom["style"].strip()
    rng = random.Random(_seed_from(title) + 7)
    return rng.choice(STYLES)


def _person(index: int, role: str, title: str) -> Dict[str, Any]:
    surnames = ["林", "陈", "沈", "陆", "周", "许", "顾", "江", "裴", "程"]
    given = ["默", "砚", "迟", "野", "青", "决", "眠", "昭", "棠", "冽"]
    rng = random.Random(_seed_from(title) + index * 131 + len(role))
    name = rng.choice(surnames) + rng.choice(given)
    return {
        "姓名": name,
        "角色定位": role,
        "外貌细节": rng.choice(["偏瘦，指节有旧伤", "眉骨一道浅疤", "右手小指少一截", "走路轻，鞋底磨损严重"]),
        "习惯性动作": rng.choice(["咬下唇", "转手里的打火机", "摸后颈", "用指尖敲膝盖"]),
        "原生经历": rng.choice(["幼年失怙，跟着长辈讨生活", "从旧城区搬来，户口都丢了", "被亲戚养大，常挨饿", "在码头扛活，睡过桥洞"]),
        "心理创伤": rng.choice(["怕密闭空间", "听不得锁门声", "被遗弃过，不敢先开口", "见血会手抖"]),
        "性格优点": rng.choice(["能忍", "记路极准", "对危险敏感", "说话算数"]),
        "致命缺陷": rng.choice(["多疑", "容易把人往坏处想", "遇事先动手", "不敢信任任何人"]),
        "内心执念": rng.choice(["找到失踪的人", "还清一笔旧账", "证明自己不是弃子", "守住最后一块地方"]),
        "隐藏秘密": rng.choice(["手里有张别人不知道的地图", "和旧案有牵连", "曾替人顶过罪", "知道某个人的死因"]),
        "软肋": rng.choice(["一个孩子", "旧伤复发时动不了", "怕水", "不能见特定的人"]),
        "当前处境": rng.choice(["被人追到巷子深处", "躲在一栋旧楼里", "刚丢掉唯一住处", "在夜里赶路，身无分文"]),
        "当前情绪": rng.choice(["紧绷", "压着火", "发冷", "疲惫但不敢睡"]),
        "当前伤势": rng.choice(["左臂划伤未处理", "肋骨闷痛", "额头有干涸的血", "脚踝扭伤"]),
        "人际关系": [],
        "个人目标": "",
        "阴暗面": rng.choice(["必要时会把人推出去", "撒谎从不眨眼", "对仇人下得了死手", "为了自保可以装死"]),
    }


def _power_system(genre: str) -> Dict[str, Any]:
    base = {
        "能力来源": "越阶使用会透支寿命与感知",
        "修炼流程": "从身体适应到意志承受，再逐步打开限制",
        "完整等级体系": ["灰烬", "浮尘", "引线", "断脊", "无面"],
        "每阶具体表现": "越往上越强，但失控风险同步增加",
        "进阶难度": "需要特定媒介与濒死体验",
        "进阶代价": "失去一段真实记忆或某类感官",
        "能力短板": "高强度使用后会暂时失去方向感",
        "能力副作用": "情绪会被力量放大，伤人先伤己",
        "实力天花板": "无法单凭力量改写世界底层规则",
        "特殊禁忌能力": "触碰死者残念会引来不可逆追踪",
    }
    if genre == "玄幻修仙":
        base["能力来源"] = "灵气入体，经灵根转化"
        base["完整等级体系"] = ["炼气", "筑基", "金丹", "元婴", "化神"]
        base["进阶代价"] = "每破一境都有心魔劫，执念越深越凶"
    elif genre in ("悬疑惊悚", "灵异克制"):
        base["能力来源"] = "与某些不可见之物建立感应"
        base["完整等级体系"] = ["闭眼", "听声", "触痕", "观相", "共念"]
        base["进阶代价"] = "视力、睡眠、正常情绪会逐渐被剥夺"
    elif genre in ("末世废土", "硬核科幻", "赛博朋克"):
        base["能力来源"] = "改造义体或服用不稳定强化剂"
        base["完整等级体系"] = ["素体", "一次改造", "神经接驳", "超频", "熔毁"]
        base["进阶代价"] = "排异、记忆碎片、器官衰竭"
    return base


def _force_map(title: str, genre: str) -> List[Dict[str, Any]]:
    rng = random.Random(_seed_from(title) + 19)
    names = ["灰巢", "老港帮", "白塔会", "九号站", "归墟门", "巡夜人", "红契司", "废线"]
    return [
        {
            "势力名": rng.choice(names) + "一系",
            "属性": "明面势力",
            "利益冲突": "控制水源与通行证发放",
            "历史恩怨": "十年前一次清剿里欠下血账",
            "敌对关系": ["灰巢", "九号站"],
            "内部矛盾": "老人要稳，新血要抢",
        },
        {
            "势力名": "地下旧门",
            "属性": "隐藏势力",
            "利益冲突": "回收遗失技术，不愿任何人掌握全图",
            "历史恩怨": "与官方有未公开协议",
            "敌对关系": ["巡夜人"],
            "内部矛盾": "门内两派为是否开战争执",
        },
        {
            "势力名": "巡夜人",
            "属性": "官方/半官方",
            "利益冲突": "维持表面秩序，掩盖底层规则失效",
            "历史恩怨": "欠过主角一方一条命",
            "敌对关系": ["地下旧门"],
            "内部矛盾": "有人开始私下放水",
        },
    ]


def _plot_framework(title: str, protagonist: str, genre: str) -> Dict[str, Any]:
    rng = random.Random(_seed_from(title) + 33)
    return {
        "全书终极主线": f"{protagonist}为弄清{title}背后被抹掉的事实，被迫从边缘向权力核心靠近",
        "中期节点": ["拿到关键证物", "第一次站到明面", "发现旧案里有自己人的手笔"],
        "短期开局冲突": f"{protagonist}在夜里被人追到旧城区，手里只剩一件来历不明的东西",
        "短期伏笔": ["追杀者叫出了他的真名", "那件东西里夹着半张照片"],
        "中期伏笔": ["某股势力很早就在等他出现", "旧地图上的路线与他童年记忆重合"],
        "长线伏笔": ["世界的规则本身在慢慢失效", "主角的身世与最顶层秘密同源"],
        "当前未解决危机": ["追兵未退", "伤口正在恶化", "唯一藏身处已经暴露"],
        "未来潜在大冲突": ["多方势力争抢旧城控制权", "主角的选择将改变规则归属"],
    }


def world_from_title(title: str, custom: Dict[str, str] | None = None) -> Dict[str, Any]:
    custom = custom or {}
    genre = _pick_genre(title, custom)
    style = _pick_style(title, custom)
    protagonist = _person(1, "主角", title)
    protagonist_name = protagonist["姓名"]
    world = {
        "world_setting": {
            "世界类型": genre,
            "时代背景": custom.get("world") or f"{title}背景下的旧秩序正在崩解，普通人靠有限资源续命",
            "社会结构": "上层掌握稀缺资源，底层靠灰色交易与体力活存活，中坚力量夹在两头",
            "世界底层规则": custom.get("rules") or "任何越界能力都必须支付同等代价，秘密知道越多越容易被规则追踪",
            "世界禁忌": custom.get("taboos") or "不追问来处，不公开能力，不跨过旧城边界",
            "生存现状": "资源紧缺，信任昂贵，每个人都在藏一手",
            "整体基调": style,
        },
        "power_system": _power_system(genre),
        "force_map": _force_map(title, genre),
        "character_list": [
            protagonist,
            _person(2, "核心配角", title),
            _person(3, "核心反派", title),
        ],
        "plot_framework": _plot_framework(title, protagonist_name, genre),
        "style": style,
        "genre": genre,
        "locked": True,
    }
    # 用户填写内容绝对优先
    for key in ["world", "rules", "power", "forces", "taboos"]:
        if custom.get(key):
            if key == "world":
                world["world_setting"]["时代背景"] = custom[key]
            elif key == "rules":
                world["world_setting"]["世界底层规则"] = custom[key]
            elif key == "power":
                world["power_system"]["能力来源"] = custom[key]
            elif key == "forces":
                world["force_map"].append({"势力名": custom[key], "属性": "用户设定", "利益冲突": "", "历史恩怨": "", "敌对关系": [], "内部矛盾": ""})
            elif key == "taboos":
                world["world_setting"]["世界禁忌"] = custom[key]
    if custom.get("protagonist"):
        world["character_list"][0]["姓名"] = custom["protagonist"]
    if custom.get("antagonist"):
        world["character_list"][-1]["姓名"] = custom["antagonist"]
    if custom.get("opening"):
        world["plot_framework"]["短期开局冲突"] = custom["opening"]
    if custom.get("conflict"):
        world["plot_framework"]["当前未解决危机"] = [custom["conflict"]]
    if custom.get("direction"):
        world["plot_framework"]["全书终极主线"] = custom["direction"]
    return world


class LocalEngine:
    def __init__(self, title: str) -> None:
        self.title = title
        self.rng = random.Random(_seed_from(title))

    def _fill(self, template: str, ctx: Dict[str, str]) -> str:
        return template.format(**ctx)

    def _context(self, world: Dict[str, Any]) -> Dict[str, str]:
        chars = world.get("character_list", [])
        name = chars[0]["姓名"] if chars else "他"
        places = PLACES
        return {
            "name": name,
            "place": self.rng.choice(places),
            "object": self.rng.choice(OBJECTS),
            "target": self.rng.choice(TARGETS),
            "noise": self.rng.choice(NOISES),
            "line": self.rng.choice(LINES),
            "line2": self.rng.choice(LINES2),
            "action": self.rng.choice(ACTION_WORDS),
            "fluid": self.rng.choice(FLUIDS),
            "scene": self.rng.choice(SCENES),
            "weapon": self.rng.choice(WEAPONS),
            "mark": self.rng.choice(MARKS),
            "verb": self.rng.choice(VERBS),
            "texture": self.rng.choice(TEXTURES),
        }

    def generate_chapter(
        self,
        world: Dict[str, Any],
        chapter_no: int,
        total: int,
        tier: str,
        tail: str = "",
    ) -> str:
        low, high = WORD_TIERS[tier]
        ctx = self._context(world)
        name = ctx["name"]
        # 第一章开篇：直接切入，不堆背景
        opening = self.rng.choice(OPENING_LINES).format(**ctx)
        body = opening + "\n\n"
        while char_count(body) < max(1, low - 120):
            tpl = self.rng.choice(ACTIONS)
            para = self._fill(tpl, ctx) + "\n\n"
            body += para
            ctx = self._context(world)
        body = trim_to(body, high - 90)
        # 保证结尾卡在行动/危机/悬念，绝不收尾
        ending = self.rng.choice(OPEN_ENDINGS).format(**ctx)
        text = body + "\n" + ending + "\n"
        if char_count(text) > high:
            text = trim_to(text, high)
        elif char_count(text) < low:
            while char_count(text) < low:
                text += self._fill(self.rng.choice(ACTIONS), ctx) + "\n"
            text = trim_to(text, high)
        return text
