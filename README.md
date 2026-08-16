# 专用 Agent 开发脚手架（租赁合同审查示例）

一个**可运行的专用 agent 最小项目**，同时是「把专业工作产品化」的教程骨架。
模型调用通过 OpenAI 兼容接口完成，默认走 DeepSeek，换模型商只改一行配置。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配 key（三选一）
#   a) 网页版：启动服务后在网页点「设置」填一次，保存到本机 .agent_key
#   b) 命令行：首次运行会提示你输入一次
#   c) 环境变量：setx DEEPSEEK_API_KEY "sk-..." （部署场景）
copy .env.example .env          # Windows（可选，环境变量方式才需要）

# 3. 跑演示（内置一条示例合同，观察工具调用过程）
python main.py

# 4. 跑评估（量化"干得好不好"的北极星指标）
python eval.py

# 5. 真实使用：交互模式（不绑定示例，随意输入）
python interactive.py
#   - 输入文件路径 → 直接读取
#   - 直接粘贴合同文本（可多行，最后输空行提交）
#   - 审完一份继续审下一份，输 q 退出
# 也可以一次性审查指定文件：
python interactive.py path/to/contract.txt

# 6. 启动 HTTP 服务（移动端网页，APK 的前身）
python server.py
#   浏览器访问 http://127.0.0.1:8000
#   手机同一 WiFi 时，访问 http://<电脑局域网IP>:8000 即可在手机上用
#   （局域网 IP 用 `ipconfig` 查看，如 192.168.x.x）
```

## 输入校验

`validator.py` 在审查前先拦截"无关输入"，避免浪费 token：
- 明显无关内容（你好、闲聊、一句话）→ 提示重新输入
- 其他合同（借条、买卖、劳务）→ 提示"目前只审查租赁合同"
- 歧义输入 → 用轻量模型回检一次，确认是租赁才继续

命令行和 HTTP 服务都接入了校验。
```

## 项目结构

```
agent-project/
├── config.py            # 换模型商只改这里（base_url + key 环境变量）
├── agent.py             # 通用 agentic loop（与领域无关，不要改）
├── tools.py             # 领域工具：把"专业动作"变成函数（换行业重写这里）
├── schemas.py           # 输出校验：pydantic 定义审查报告结构（护栏）
├── contract_agent.py    # 领域入口：系统提示词 + 组装 + 留档
├── eval_set.json        # 评估集：真实案例 + 人工标注（你的命根子）
├── eval.py              # 评估脚本：跑评估集，输出通过率
├── main.py              # 演示入口
├── requirements.txt
├── .env.example / .env  # 可选：环境变量方式的 key（不提交 git）
├── .agent_key           # 网页/命令行首次运行时填的 key（不提交 git）
└── logs/                # 每次审查留档，出问题能复盘
```

## 核心心智模型

> **Agent = 一个 while 循环 + 工具集 + 上下文管理。**

`agent.py` 里的循环只有 30 行左右，与领域无关。它的逻辑：
模型返回 `tool_calls` → 你执行工具 → 把结果以 `role="tool"` 塞回历史 → 循环，
直到模型不再调用工具。**换行业，只是换 `tools.py` 的工具和 `contract_agent.py` 的提示词，循环永远不变。**

## 换行业 = 换 3 个文件

| 文件 | 改成什么 |
|---|---|
| `tools.py` | 你的领域的专业动作（如 `read_file` / `grep_code` / `query_db`） |
| `contract_agent.py` | 你的领域的系统提示词（行业规则、检查清单、输出格式要求） |
| `schemas.py` | 你的领域的输出结构（报告里要有什么字段） |

`agent.py` 和 `config.py` 一般不用动。

## 评估集：为什么它是命根子

没有评估集，你永远无法回答"这次改动是变好还是变差"。
`eval_set.json` 里每条案例 = `input`（真实输入）+ `expected`（人工标注的正确答案）+ `note`（标注理由）。

工作流：
1. 拿到一条用户纠正过的案例 → 脱敏 → 加进 `eval_set.json`
2. 改提示词或工具
3. 跑 `python eval.py`，看通过率变化
4. 通过率上升就保留改动，下降就回滚

**这是专用 agent 开发的唯一北极星指标。** 案例积累到 20~30 条，agent 会明显变稳。

## 领域知识编码在工具里

`tools.py` 的 `lookup_regulation` 用内置字典保存法规要点——这是"领域知识"的起点。
真实场景可以升级为：

- 法规库放在数据库 / 向量检索里，工具从库中查
- 合同检索按章节/条款结构解析，而不是简单按关键词切句
- 检查清单从几十条逐步扩展（租期 / 押金 / 违约金 / 维修责任 / 转租条款……）

**骨架不变，知识库变大。**

## 护栏清单（第 7~8 周完善）

- [x] `schemas.py`：pydantic 校验输出结构，坏 JSON 直接拦截（`agent.py` 里已实现）
- [x] `max_turns`：循环次数上限，防死循环
- [x] `logs/`：每次审查留档，可复盘
- [ ] 人工复核闭环：专业用户审核输出 → 纠正案例进评估集 → 你改进
- [ ] 提示词/工具 git 版本管理，出问题可回滚
- [ ] 批处理 + 限流重试（跑几十份合同时）

## 常见问题

**Q: 工具参数结构是宽松的吗？**
A: 演示版 `_parameters()` 返回空 schema，靠工具侧校验兜底。正式项目建议用
`inspect.signature` 或 pydantic 从函数签名生成精确的 JSON Schema，让模型少传错参数。

**Q: `deepseek-reasoner` 能用吗？**
A: 不推荐。推理模型工具调用不稳定、响应慢。Agent 一律用 `deepseek-chat`。

**Q: 怎么换 Claude / Kimi？**
A: `config.py` 里加一个 provider 配置即可，代码不用改。
DeepSeek 的上下文缓存是自动的，无需像 Claude 那样手动标记。

---

## 打包成 APK（移动端软件）

### API key 怎么处理（重要）

key 是**你自己在软件里填的**（网页版或命令行首次运行时填一次，存到本机 `.agent_key`）。
对于个人使用，这个方案最简单。

如果要发布给别人用，别让他们的 key 存到你服务器——改为**用户填自己的 key**（就像各家 AI 客户端的做法）。打包成 APK 后同样在设置里填 key。

### 方案一（最简单，推荐先做）：手机浏览器直接访问

后端跑在你电脑上，手机同一 WiFi 访问网页即可，无需打包：
```
python server.py
手机浏览器打开 http://<电脑局域网IP>:8000
```

### 方案二：用 Capacitor 打包成 APK（需要 Android Studio）

Capacitor 能把网页包成本地 APK，界面直接调用后端地址：

1. 安装 Node.js，创建壳工程：
   ```
   npx @capacitor/cli create rental-app
   cd rental-app
   npm install @capacitor/core @capacitor/android
   npx cap add android
   ```
2. 把 `static/` 里的内容拷到 `rental-app/www/`
3. 把网页里的 `fetch("/api/review", ...)` 改成后端完整地址：
   `fetch("http://<你的服务器地址>:8000/api/review", ...)`
4. 生成 APK：
   ```
   npx cap open android      # 用 Android Studio 打开
   ```
   Android Studio → Build → Build Bundle(s)/APK(s) → Build APK(s)
   产物在 `app/build/outputs/apk/debug/app-debug.apk`

> 注意：手机访问 `http://192.168.x.x:8000` 属于明文 HTTP。同 WiFi 调试可行；
> 如果要给外部用户用，需要一台公网服务器 + HTTPS（或用内网穿透工具）。

### 更进一步的架构（上线再说）

- 后端加简单鉴权（token 校验），避免被随意调用消耗你的 key
- 后端部署到云服务器，APK 直连云端
- 审查结果落库，方便统计和管理
