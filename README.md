# AI 全自动无 AI 味超长连贯小说生成器

全网唯一真正根治 AI 写小说通病的专属工具：根治章节结尾自带结束感、剧情重置、人设崩坏、AI 套话、模板行文、机械叙事、上下文割裂、伏笔丢失、节奏僵硬、千章崩设定、千章变画风、强行收尾、流水账叙事。

## 核心能力
- 双启动可选模式：全自动脑洞生成 / 用户自定义精细创作
- 全自定义自由开关：防章节完结、全局记忆继承、五章剧情递进、深度去 AI 文风、自动存档更新
- 三档精准锁字：1200-2000 / 3000-4000 / 9000-11000
- 1-15 章自由批量连写
- 全自动世界观推演、人物生成、伏笔铺设、剧情递进
- 全局永久记忆存档：world.json / char.json / plot.json
- 深度去 AI 文风体系、真人网文节奏模板、全场景剧情素材库
- 强制连载不结尾机制、多层级防割裂续写机制

## 安装
```bash
cd novel-ai-generator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

本项目默认不依赖任何第三方库。接入真实大模型时，可选择任一 OpenAI 兼容接口。

## 使用
### 交互式
```bash
python main.py
```

### 全自动模式
```bash
python main.py new --title "废土拾荒者" --mode auto --chapters 5 --tier standard
```

### 自定义模式
```bash
python main.py new --title "长夜将明" --mode custom --genre "悬疑惊悚" --style "冷峻写实" --protagonist "林默" --world "南方小城连续失踪案" --chapters 3 --tier short
```

### 续写
```bash
python main.py continue --project "废土拾荒者" --chapters 5 --tier long
```

### 查看工程
```bash
python main.py list
python main.py inspect --project "废土拾荒者"
```

### 运行测试
```bash
python -m unittest discover -s tests -v
```

## 大模型接入
| 环境变量 | 说明 | 默认值 |
| --- | --- | --- |
| `NOVEL_API_KEY` | OpenAI 兼容接口密钥 | 空 |
| `NOVEL_BASE_URL` | 接口地址，需以 `/v1` 结尾 | `https://api.openai.com/v1` |
| `NOVEL_MODEL` | 模型名 | `gpt-4o-mini` |
| `NOVEL_TIMEOUT` | 请求超时秒数 | `120` |

未配置密钥时自动使用内置离线演示引擎，用于流程验证、存档验证与字数验证。正式百万字创作请接入真实大模型。

## 项目结构
```
main.py                   CLI 入口
novel_ai/
  config.py               全部可选参数与默认开关
  storage.py              三份永久本地存档
  prompts.py              完整 Prompt 体系
  llm.py                  OpenAI 兼容接口
  local_engine.py         离线演示引擎
  project_manager.py      新建/载入/补全工程
  filters.py              去 AI 套话与结尾检测
  wordcount.py            三档精准字数控制
  generator.py            连写、防割裂、自动存档
tests/
  test_smoke.py           冒烟测试
docs/
  WHITEPAPER.md           全量开发白皮书
```

## 存档
- `projects/<小说名>/world.json`：世界永久锁死档案
- `projects/<小说名>/char.json`：动态人物实时档案
- `projects/<小说名>/plot.json`：全局剧情伏笔档案
- `projects/<小说名>/chapters/`：分章文件
- `projects/<小说名>/manuscript.txt`：连续正文

## 开发白皮书
完整功能、开关、Prompt、去 AI 规则、写作模板、剧情体系、底层逻辑、存档机制、防割裂机制、章节节奏体系见 [docs/WHITEPAPER.md](docs/WHITEPAPER.md)。
