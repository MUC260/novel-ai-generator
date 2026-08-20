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

TARGETS = ["木门", "铁门", "窗口", "墙角", "灯", "桌", "天花板", "墙", "地板缝", "门槛"]

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

VERBS = ["翻东西", "数钱", "套衣服", "拨电话", "翻抽屉", "藏箱子", "拆封条"]

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



# 开篇首句库，直接切入现场（第 2 章起使用）

OPENING_LINES = [

    "{name}醒过来的时候，{place}外面的{noise}已经停了。",

    "\u201c把手举起来。\u201d{name}还没看清说话的人，{noise}就先到了。",

    "雨从{place}漏下来，落在{name}后颈上，凉得{name}肩膀一缩。",

    "{name}是在{place}被堵住的，前后都有人。",

    "门被撞开时，{name}刚把{object}塞进怀里。",

]

# 第一章开篇立人：先立主角（姓名+身世+当前处境+目标）再切入冲突（增强版）

OPENING_INTROS = [

    "{name}{origin}。眼下被堵在{place}，{situation}。{name}攥紧{object}，知道这一关躲不过去——{drive}。",

    "{name}，{origin}。听到有人喊他名字的瞬间，{name}攥紧了{object}，{situation}。脑子里只有一个念头：{drive}。",

    "\u201c{name}。\u201d声音从{place}那头传来。{origin}的{name}知道这声称呼意味着什么——{situation}。{name}咬紧牙，{drive}。",

    "{name}这辈子最不想回忆的事，就是{origin}。可眼下{situation}，由不得{name}选。{name}把{object}握在手里，{drive}。",

    "{name}头顶着{origin}，脚踩在{place}的碎砖上，{situation}。{name}深吸一口气，{drive}。",

    "{name}知道{drive}——可眼下{situation}，{name}还是把{object}握紧了，迈步走进{place}。",

]



# 第一章立人回退：当 world 角色没有填写原生经历或当前处境时使用

ORIGIN_FALLBACKS = [

    "生来就没人管",

    "从死人堆里爬出来的",

    "身世成谜，只知道自己是孤儿",

    "在底层摸爬滚打长大的",

    "曾是某个没落家族的独子",

    "战场上捡回一条命的幸存者",

    "从小被师傅带大，师傅却死得不明不白",

    "十五岁就一个人闯江湖",

]

SITUATION_FALLBACKS = [

    "刚被人出卖，身上带着伤",

    "身上只剩下最后一口气，却还不能倒下",

    "被追了三条街，退路已经断了",

    "面前站着的人，正等着他做决定",

    "手里握着一条命，犹豫要不要交出去",

    "时间不多了，外面的人已经围过来了",

]

DRIVE_FALLBACKS = [

    "活下去，不管用什么手段",

    "把该拿的东西拿到手",

    "不能死在这里，还有账没算清",

    "找到那个人，问清楚当年的事",

    "把所有人都带出去，一个都不能少",

]





def _seed_from(title: str) -> int:

    return int(hashlib.md5(title.encode("utf-8")).hexdigest()[:8], 16)





def _power_system(genre: str) -> Dict[str, Any]:

    g = str(genre).strip()

    if "修仙" in g or "玄幻" in g:

        return {

            "能力来源": "灵气修炼",

            "修炼流程": "引气入体→筑基→结丹→元婴→化神→渡劫→飞升",

            "完整等级体系": [

                "练气（引气入体，初步感知灵气）",

                "筑基（灵气淬体，寿命延长至两百岁）",

                "结丹（丹田结丹，可御物飞行）",

                "元婴（元婴出窍，神识覆盖百里）",

                "化神（感悟天地法则，可撕裂虚空）",

                "渡劫（九重雷劫，九死一生）",

                "飞升（超脱此界，去往上界）",

            ],

            "进阶难度": "每阶差距十倍以上，结丹后每进一步都需要机缘",

            "进阶代价": "渡劫失败则魂飞魄散，筑基失败则经脉尽断",

            "能力短板": "灵力耗尽后与凡人无异",

            "能力副作用": "修炼越急越容易走火入魔",

            "实力天花板": "渡劫期九重天劫，百万中无一能过",

            "特殊禁忌能力": "血祭、夺舍、禁术，使用后遭天谴",

        }

    return {

        "能力来源": "天赋与训练",

        "修炼流程": "入门→熟练→精通→大师→宗师",

        "完整等级体系": [

            "入门（掌握基本技能）",

            "熟练（能独立应对中等难度）",

            "精通（技术全面，能解决复杂问题）",

            "大师（领域内顶尖，可带新人）",

            "宗师（开宗立派级别）",

        ],

        "进阶难度": "每阶需要大量实践与积累",

        "进阶代价": "训练过度会留下暗伤",

        "能力短板": "没有绝对完美的能力",

        "能力副作用": "长期高压使用会导致身心俱疲",

        "实力天花板": "人类体能极限",

        "特殊禁忌能力": "非正常手段获得的力量往往伴随代价",

    }





def _force_map(title: str, genre: str) -> List[Dict[str, Any]]:

    return [

        {"势力名": f"{title[:2]}官方", "属性": "官方势力", "利益冲突": "维持统治", "历史恩怨": "镇压过反抗者", "敌对关系": ["地下组织"], "内部矛盾": "派系斗争"},

        {"势力名": f"{title[:2]}地下组织", "属性": "地下势力", "利益冲突": "抢地盘", "历史恩怨": "被官方通缉", "敌对关系": [f"{title[:2]}官方"], "内部矛盾": "内部分赃不均"},

    ]





def _person(index: int, role: str, title: str) -> Dict[str, Any]:

    name = f"{title[:1]}{['龙','虎','七','三','五','九'][index % 6]}{['爷','姐','哥','叔','娘','少'][index % 6]}"

    if index == 0:

        name = f"{title[:1]}{['明','夜','风','尘','默','影'][index % 6]}"

    return {

        "姓名": name,

        "角色定位": [role] if role else [""],

        "外貌细节": "中等身材，眼窝深陷，嘴角有旧疤" if index == 0 else "精瘦结实，目光锐利",

        "习惯性动作": "下意识摸后颈" if index == 0 else "说话时喜欢敲桌面",

        "原生经历": f"从小在{title[:2]}街头长大，见过太多生死",

        "心理创伤": "最信任的人背叛过自己",

        "性格优点": "果决、冷静、重情义",

        "致命缺陷": "太容易相信熟人",

        "内心执念": "想找到当年那个答案",

        "隐藏秘密": "身上有一份不该存在的证据",

        "软肋": "过去的同伴",

        "当前处境": "被各方势力盯上，无处可退",

        "当前情绪": "紧绷，但表面镇定",

        "当前伤势": "左肩有旧伤，阴雨天会疼",

        "人际关系": "和地下组织有旧账，和官方有纠葛",

        "个人目标": "活下去，查出真相",

    }





def _protagonist_data(title: str, name: str) -> Dict[str, Any]:

    return {

        "姓名": name,

        "角色定位": ["主角"],

        "外貌细节": "中等身材，眼窝深陷，嘴角有旧疤",

        "习惯性动作": "下意识摸后颈",

        "原生经历": f"从小在{title[:2]}街头长大，见过太多生死",

        "心理创伤": "最信任的人背叛过自己",

        "性格优点": "果决、冷静、重情义",

        "致命缺陷": "太容易相信熟人",

        "内心执念": "想找到当年那个答案",

        "隐藏秘密": "身上有一份不该存在的证据",

        "软肋": "过去的同伴",

        "当前处境": "被各方势力盯上，无处可退",

        "当前情绪": "紧绷，但表面镇定",

        "当前伤势": "左肩有旧伤，阴雨天会疼",

        "人际关系": "和地下组织有旧账，和官方有纠葛",

        "个人目标": "活下去，查出真相",

    }





def _plot_framework(title: str, protagonist_name: str, genre: str) -> Dict[str, Any]:

    return {

        "全书终极主线": f"{protagonist_name}为弄清{title[:2]}背后被抹掉的事实，一路追查，发现真相远超想象",

        "中期节点": [f"{protagonist_name}找到第一个关键证人", f"{protagonist_name}潜入{title[:2]}核心组织"],

        "短期开局冲突": f"{protagonist_name}无意中卷入一场秘密交易，成为双方追杀目标",

        "短期伏笔": ["那封没署名的信", "抽屉里少了一张照片", "街角总有人在盯梢"],

        "中期伏笔": ["三年前那场火灾的真相", "某个人物的双重身份"],

        "长线伏笔": ["整个城市地下的秘密网络", "一幅古画背后的密码"],

        "当前未解决危机": [f"{protagonist_name}被{title[:2]}地下组织盯上"],

        "未来潜在大冲突": [f"{title[:2]}两大势力全面开战"],

    }





def world_from_title(title: str, custom: Dict[str, str] = None) -> Dict[str, Any]:

    """离线演示：从书名生成完整世界观，支持自定义覆写。"""

    custom = custom or {}

    style = custom.get("style") or random.choice(STYLES)

    genre = custom.get("genre") or random.choice(GENRES)

    protagonist_name = custom.get("protagonist") or f"{title[:1]}{['明','夜','风','尘','默','影'][0]}"
    # 单字姓转换为完整姓名（如“司”->“司无名”）
    if len(protagonist_name) == 1 and protagonist_name.strip():
        import random as _random_mod
        _suffixes = ['无名', '凌风', '天行', '少卿', '默言', '南山', '宇', '秋', '青鸟']
        protagonist_name = protagonist_name.strip() + _random_mod.choice(_suffixes)
        del _random_mod, _suffixes

    protagonist = _protagonist_data(title, protagonist_name)

    world = {

        "world_setting": {

            "世界类型": genre,

            "时代背景": custom.get("world") or f"{title[:2]}是一个混乱与秩序并存的地方，表面平静，暗流涌动",

            "社会结构": "阶层分明，底层人挣扎求生，顶层人掌控资源",

            "世界底层规则": custom.get("rules") or "弱肉强食，但仍有底线",

            "世界禁忌": custom.get("taboos") or "背叛者死",

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

        old_name = world["character_list"][0]["姓名"]

        world["character_list"][0]["姓名"] = protagonist_name

        # 同步更新 plot_framework 中的主角名引用（支持字符串和列表字段）

        def _repl_name(v):
            if isinstance(v, str) and old_name in v:
                return v.replace(old_name, protagonist_name, 1)
            if isinstance(v, list):
                return [e.replace(old_name, protagonist_name, 1) if isinstance(e, str) and old_name in e else e for e in v]
            return v

        for _pf_key in ["全书终极主线", "中期节点", "短期开局冲突", "短期伏笔", "中期伏笔", "长线伏笔", "当前未解决危机", "未来潜在大冲突"]:

            if _pf_key in world["plot_framework"]:

                world["plot_framework"][_pf_key] = _repl_name(world["plot_framework"][_pf_key])

    if custom.get("antagonist"):

        world["character_list"][-1]["姓名"] = custom["antagonist"]

    if custom.get("opening"):

        world["plot_framework"]["短期开局冲突"] = custom["opening"]

    if custom.get("conflict"):

        world["plot_framework"]["当前未解决危机"] = [custom["conflict"]]

    if custom.get("direction"):

        world["plot_framework"]["全书终极主线"] = custom["direction"]

    if custom.get("worldview"):

        world["world_setting"]["用户世界观补充"] = custom["worldview"]

    # 存储用户自定义字段

    world["_user_custom"] = {k: v for k, v in custom.items() if v.strip()}

    return world





class LocalEngine:

    def __init__(self, title: str) -> None:

        self.title = title

        self.rng = random.Random(_seed_from(title))

        self._recent_templates = []  # 最近使用的模板索引，用于去重

        self._max_recent = 3



    def _fill(self, template: str, ctx: Dict[str, str]) -> str:

        return template.format(**ctx)



    def _pick_action(self, pool, ctx):

        """从模板池中选一个，避免与最近3条重复。"""

        candidates = [(i, t) for i, t in enumerate(pool) if i not in self._recent_templates]

        if not candidates:

            candidates = list(enumerate(pool))

            self._recent_templates.clear()

        idx, tpl = self.rng.choice(candidates)

        self._recent_templates.append(idx)

        if len(self._recent_templates) > self._max_recent:

            self._recent_templates.pop(0)

        return tpl.format(**ctx)



    def _context(self, world: Dict[str, Any]) -> Dict[str, str]:

        chars = world.get("character_list", [])

        name = chars[0]["姓名"] if chars else "他"

        places = PLACES

        # 从世界观中提取地点和场景信息

        world_setting = world.get("world_setting", {})

        user_worldview = world_setting.get("用户世界观补充", "")

        return {

            "name": name,

            "origin": chars[0].get("原生经历", self.rng.choice(ORIGIN_FALLBACKS)) if chars else self.rng.choice(ORIGIN_FALLBACKS),

            "situation": chars[0].get("当前处境", self.rng.choice(SITUATION_FALLBACKS)) if chars else self.rng.choice(SITUATION_FALLBACKS),

            "drive": chars[0].get("内心执念", chars[0].get("个人目标", "活下去")) if chars else "活下去",

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

            "worldview": user_worldview or "",

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

        # 第一章开篇：先立主角（姓名+身世+当前处境+驱动力）再切入冲突；后续章节直接切入

        opening = (self.rng.choice(OPENING_INTROS) if chapter_no == 1 else self.rng.choice(OPENING_LINES)).format(**ctx)

        body = opening + "\n"

        while char_count(body) < max(1, low + 100):

            para = self._pick_action(ACTIONS, ctx) + "\n"

            body += para

            ctx = self._context(world)

        body = trim_to(body, high - 90)

        # 保证结尾卡在行动/危机/悬念，绝不收尾

        ending = self.rng.choice(OPEN_ENDINGS).format(**ctx)

        text = body + "\n" + ending + "\n"

        if char_count(text) > high:

            text = trim_to(text, high)

        elif char_count(text) < low:

            while char_count(text) < low + 80:

                text += self._pick_action(ACTIONS, ctx) + "\n"

            text = trim_to(text, high)

        return text



