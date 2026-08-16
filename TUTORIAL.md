# 从 main 入口逐行拆解（学习说明书）

> 目标：从 `python main.py` 启动那一刻起，逐行看代码走到哪里、做了什么、为什么。
> 配合终端里打印的 `[工具调用] ...` 行一起看，效果最好。

---

## 一、启动：`python main.py` 发生了什么

执行 `python main.py` 时，Python 从**第 1 行开始逐行读整个文件**，但只**执行**没有缩进的代码。

main.py 只有两处"顶层代码"（不在任何函数/类里）：

```python
SAMPLE = """甲方：..."""      # 第 9 行：定义一条示例合同（全局变量）

if __name__ == "__main__":    # 第 34 行：程序真正从这里"开始跑"
    main()                    # 第 35 行：调用 main 函数
```

所以启动路径是：**Python 读完整个文件 → 执行 `SAMPLE = ...`（准备数据）→ 走到第 34 行 → 调用 `main()` → 跳到第 15 行**。

### 插曲：`import` 会先把被导入的文件整个跑一遍

第 5~7 行有三个 `import`，其中 `from contract_agent import build_agent, log_run` 最值得注意。

**`import` 不是"拿两个函数"这么简单**，它会把 `contract_agent.py` 从头到尾执行一遍。由于 contract_agent.py 顶部也有 import：

```
main.py  import contract_agent
    │
    ▼
contract_agent.py 第 15 行  import agent
    │
    ▼
agent.py  第 9 行  import config
    │
    ▼
config.py  import os / dotenv / openai     ← 第一次真正加载第三方库
```

**为什么这条链重要**：第一次 `import config` 时，`os`、`dotenv`、`openai` 这些第三方库会被加载进内存（需要 `pip install` 过，否则这里就报错）。之后 main.py、contract_agent.py、agent.py 共享同一个 `config` 模块——这是 Python 的模块机制，现在只需要知道：**文件间是"接力跑"，import 就是交接棒**。

> 📌 记住一句话：**`import X` = 把 X 整个文件从头到尾执行一遍**。你以后想搞清楚某个项目怎么跑起来，顺着 import 链找就是了。

---

## 二、`main()`：调度者的 7 步

进入 `main()`（第 15 行）后，逐行看：

### 第 16~19 行：打印

```python
print("=" * 60)                            # 打印 60 个等号，装饰性输出
print("  租赁合同审查 agent - 演示")
print("=" * 60)
print(f"\n📄 待审查合同：\n{SAMPLE}\n")      # f-string 把 SAMPLE 拼进输出
```

纯装饰，让用户看到"在审查哪份合同"。

### 第 21 行：组装 agent（关键一步）

```python
agent = build_agent()
```

调用 contract_agent.py 的 `build_agent()`。跳过去看它：

```python
def build_agent() -> Agent:
    return Agent(                            # 创建 Agent 实例
        system_prompt=SYSTEM_PROMPT,         # ① 行业规则（contract_agent.py 第 22 行）
        tools_impl=TOOL_IMPL,                # ② 工具实现（从 tools.py 导入）
        output_schema=ReviewResult,          # ③ 输出结构（从 schemas.py 导入）
    )
```

**这一个调用同时触发了两个文件的代码**：
- `SYSTEM_PROMPT` 在 contract_agent.py 第 22 行已经定义好了（模块加载时就执行了，`build_agent` 只是引用它）
- `TOOL_IMPL` 在 tools.py 里定义，import 时已经执行了所有 `@_tool(...)` 装饰器，把函数注册进字典

然后调用 `Agent.__init__`（agent.py 第 21 行）。它做的事：

```python
self.client = make_client(provider)   # ① 创建 API 客户端（读 .env 里的 key）
self.model = model                    # ② 记住用哪个模型（deepseek-chat）
self.tools = [...]                    # ③ 把 TOOL_IMPL 的函数转成"给模型的说明书"
```

其中 ③ 是核心：`TOOL_IMPL` 是 `{函数名: 函数}`，而模型不认识 Python 函数，它只认 JSON 说明书。`Agent.__init__` 把它**翻译**成模型能读的格式：

```python
self.tools = [
    {
        "type": "function",
        "function": {
            "name": name,                 # 函数名："search_clause"
            "description": _description(fn),  # 函数 docstring 第一行
            "parameters": _parameters(fn),   # 参数结构（演示版宽松）
        },
    }
    for name, fn in tools_impl.items()   # 遍历每个工具函数
]
```

> 📌 **关键概念**：函数在 `tools.py` 是给 Python 执行的；转成这个 JSON 后是给**模型看**的说明书。模型"决定调用 search_clause"时，实际返回的只是这个 JSON 里的 `name` + 参数，真正执行还是靠 `tools_impl` 里的函数。**说明书的作者是你（tools.py 的 docstring），翻译官是 Agent.__init__。**

回到 `main()`。

### 第 23 行：**真正让 agent 干活的行**

```python
result = agent.run(SAMPLE)
```

这一行会一直执行到审查结束——期间模型可能调用工具好几轮。这是整个项目的核心，下一节单独拆。运行完，`result` 是一个校验过的 `ReviewResult` 对象。

### 第 25~28 行：打印结果

```python
print("=" * 60)
print("📋 审查结果")
print("=" * 60)
print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))
```

`result` 是 pydantic 对象，不是字典，不能直接 `print`。所以：
- `result.model_dump(by_alias=True)`：转成字典，`by_alias=True` 让字段名用 JSON 里的 `pass`（而不是 Python 里的 `pass_`）
- `json.dumps(..., ensure_ascii=False, indent=2)`：转成**带缩进的、不乱码的** JSON 字符串打印

### 第 30~31 行：留档

```python
log_path = log_run(SAMPLE, result)
print(f"\n✅ 已留档到 {log_path}")
```

跳去看 `log_run`（contract_agent.py 第 45 行）：

```python
LOG_DIR.mkdir(exist_ok=True)                               # 建 logs/ 目录（已存在则跳过）
stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")  # 时间戳，如 20260816_143010
path = LOG_DIR / f"review_{stamp}.json"                    # 文件名：review_时间戳.json
payload = {"input": contract_text, "output": ...}           # 输入 + 输出 一起存
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
return path
```

**为什么留档**：出问题时能复盘"当时给模型的输入是什么、它输出了什么"。这是专业 agent 的可观测性基础。

---

## 三、`agent.run(SAMPLE)`：核心循环逐行拆

这是全项目最该反复读的 47 行。`SAMPLE` 是那份示例合同文本。

### 第 43~46 行：组装初始消息

```python
messages = [
    {"role": "system", "content": self.system_prompt},   # 行业规则，固定放最前
    {"role": "user",   "content": user_content},          # 本次任务：审查这份合同
]
```

`messages` 是**对话历史**，会随着循环不断变长。模型"记得"的一切都在这个列表里。

### 第 48 行：循环上限

```python
for _ in range(self.max_turns):   # max_turns=10
```

不是 `while True`，而是最多 10 轮。防止模型反复调用工具陷入死循环。

### 第 49~54 行：向模型提问

```python
response = self.client.chat.completions.create(
    model=self.model,                          # deepseek-chat
    messages=messages,                          # 完整历史（会越来越大）
    tools=self.tools,                           # 工具的"说明书"
    response_format={"type": "json_object"},   # 要求输出 JSON
)
msg = response.choices[0].message
```

一次网络请求。模型读完整历史 + 工具说明书，然后返回。结果存进 `msg`。

### 第 57~58 行：检查模型是否"回答完毕"

```python
if not msg.tool_calls:
    return self._validate(msg.content)
```

**模型每次回复可能有两种内容**：
1. **普通回答**（没有 `tool_calls`）→ 它觉得信息够了，直接给最终报告 → 返回
2. **想调用工具**（有 `tool_calls`）→ 进入下面的分支

> 📌 这就是 agentic loop 的"开关"：**没有 tool_calls = 结束，有 = 继续**。

### 第 60~65 行：把"想调工具"的回复记入历史

```python
messages.append({
    "role": "assistant",
    "content": msg.content,
    "tool_calls": msg.tool_calls,   # ← 必须原样存，不能自己重新构造
})
```

**硬规则**：模型说"我要调工具"的那条回复，必须整条原样存进历史，后面才能接工具结果。

### 第 68~85 行：执行工具，把结果喂回去

```python
for call in msg.tool_calls:              # 一次回复可能想调多个工具
    fn_name = call.function.name          # 取出工具名："search_clause"
    args = json.loads(call.function.arguments)  # 参数是 JSON 字符串，解析成字典
    print(f"  [工具调用] {fn_name} {args}")     # 调试输出：这就是你看到的"[工具调用]"行

    fn = self.tools_impl.get(fn_name)     # 在"真正干活"的字典里查函数
    try:
        result = fn(**args) if fn else f"未知工具: {fn_name}"   # 调用你的 Python 函数！
    except TypeError as e:
        result = f"工具参数错误: {e}"
    except Exception as e:
        result = f"工具执行异常: {e}"

    messages.append({
        "role": "tool",
        "tool_call_id": call.id,          # 和上面的 tool_call.id 配对
        "content": result,                # 工具返回的结果
    })
```

拆成三件事：

1. **解析**：`fn_name` = 模型想调哪个函数；`args` = 参数（模型传的是 JSON 字符串，必须 `json.loads` 成字典）
2. **执行**：`self.tools_impl.get(fn_name)` 在"真正干活的字典"里找到函数，`fn(**args)` 调它。**模型只管"说"，代码负责"做"**
3. **喂回**：把结果包成 `role="tool"` 消息追加进历史，`tool_call_id` 和上面的配对

然后**循环继续**（回到第 48 行的下一轮 `for`）——模型会读到工具结果，继续推理，决定是再调工具还是输出报告。

### 第 87 行：兜底

```python
raise RuntimeError(f"达到最大轮数 {self.max_turns}，任务未完成")
```

10 轮还没结束？抛异常，告诉你"这 agent 卡住了"。

### `_validate`：输出护栏（第 89~101 行）

```python
if self.output_schema is None:     # 没传输出结构 → 原样返回
    return {"content": content}
try:
    return self.output_schema.model_validate_json(content)  # 校验 JSON
except Exception:
    return self.output_schema(      # 校验失败 → 兜底"待复核"，不让坏输出通过
        risks=[],
        pass_="待复核",
        summary=f"模型输出无法解析为有效结构，已拦截。原始内容: {content[:200]}",
    )
```

模型输出的是字符串，`model_validate_json` 把它校验成 `ReviewResult` 对象（字段缺失/类型错会抛异常）。抛异常就兜底返回"待复核"——**宁可说不知道，不假装有结果**。

---

## 四、完整链路一张图

```
python main.py
  │
  ├─ import 链：main → contract_agent → agent → config（加载 openai 库）
  │
  ├─ SAMPLE 定义（示例合同）
  │
  ├─ main()：
  │   ├─ build_agent()           ──► Agent.__init__
  │   │                              ├─ make_client()     读 .env 的 key
  │   │                              ├─ 翻译 TOOL_IMPL 为"模型说明书"
  │   │                              └─ 保存提示词/输出结构
  │   │
  │   ├─ agent.run(SAMPLE)       ──► for 循环（≤10 轮）
  │   │                              ├─ 发请求给模型
  │   │                              ├─ 有 tool_calls？
  │   │                              │   是 → 执行 tools.py 的函数 → 结果喂回 → 继续
  │   │                              │   否 → 校验输出 → 返回 ReviewResult
  │   │                              └─ 10 轮没完 → 抛异常
  │   │
  │   ├─ 打印结果（model_dump → json.dumps）
  │   └─ log_run()               保存到 logs/review_时间戳.json
```

---

## 五、三个"最容易糊涂"的点

1. **`import` 会执行整个文件**：所以 SAMPLE、SYSTEM_PROMPT、TOOL_IMPL 这些"顶层代码"在 import 时就已经算好了。`build_agent()` 只是把它们**组装**，不是重新定义。

2. **同一个名字，两个世界**：`search_clause` 既是 Python 函数（`tools.py`，给代码执行），又出现在 JSON 说明书里（`Agent.tools`，给模型看）。模型说 `fn_name = "search_clause"`，你的代码靠这个名字在 `TOOL_IMPL` 里找回那个函数。

3. **`messages` 是唯一记忆**：整个循环里，模型每轮只看到 `messages` 里越来越长的历史。工具结果、模型自己说过的话，全靠这个列表传递。这就是"无状态 API + 有状态客户端"的运作方式。

---

## 六、照这个顺序再看一遍

1. `python main.py`，看终端打印，尤其 `[工具调用]` 行
2. 对着上面第三节的拆解，把 `agent.py` 的 `run()` 自己读一遍，纸上走一遍循环
3. 改一行：把 main.py 第 9 行的 `SAMPLE` 合同文本换掉，重跑，看输出变化
4. 改一行：在 `contract_agent.py` 的 `SYSTEM_PROMPT` 加一条规则，重跑，看行为变化

**能改、能跑、能解释每一步，就算真正看懂了。**
