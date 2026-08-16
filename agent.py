"""通用 agentic loop：Agent = 一个 while 循环 + 工具集 + 上下文管理。

这个文件与领域无关——换行业只需换 tools 和 system 提示词。
不要改这里的循环逻辑，它已经是通用骨架。
"""

import json

from config import MODEL, make_client
from schemas import ReviewResult


class Agent:
    """一个通用工具调用 Agent。

    用法：
        agent = Agent(system_prompt, tools_impl, output_schema)
        result = agent.run("需要处理的内容")
    """

    def __init__(self, system_prompt: str, tools_defs: list, tools_impl: dict,
                 output_schema=None, model: str = MODEL, max_turns: int = 20,
                 max_tokens: int = 8192, provider: str = "deepseek"):
        self.client = make_client(provider)
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools_defs          # 给模型看的"说明书"（JSON schema）
        self.tools_impl = tools_impl     # 给代码执行的"实现"（函数字典）
        self.output_schema = output_schema
        self.max_turns = max_turns
        self.max_tokens = max_tokens     # 单次输出上限；长报告容易被默认值截断

    def run(self, user_content: str) -> dict:
        """执行一次任务，返回 dict（若传了 output_schema 则为校验后的对象）。"""
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content},
        ]

        for _ in range(self.max_turns):          # 上限保护，防止无限循环
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=messages,
                tools=self.tools,
                response_format={"type": "json_object"} if self.output_schema else None,
            )
            msg = response.choices[0].message

            if not msg.tool_calls:               # 模型回答完毕
                return self._finish(messages, msg.content)

            # 先把含 tool_calls 的 assistant 消息原样记入历史（硬规则）
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": msg.tool_calls,
            })

            # 逐个执行工具，结果以 role="tool" 追加
            for call in msg.tool_calls:
                fn_name = call.function.name
                args = json.loads(call.function.arguments)
                print(f"  [工具调用] {fn_name} {args}")     # 调试：看清模型在做什么

                fn = self.tools_impl.get(fn_name)
                try:
                    result = fn(**args) if fn else f"未知工具: {fn_name}"
                except TypeError as e:
                    result = f"工具参数错误: {e}"
                except Exception as e:                       # 工具出错 → 反馈给模型，让它自己调整
                    result = f"工具执行异常: {e}"

                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,                 # 必须和上面的 tool_call.id 配对
                    "content": result,
                })

        raise RuntimeError(f"达到最大轮数 {self.max_turns}，任务未完成")

    def _finish(self, messages: list, content: str) -> dict:
        """拿到最终文本，解析成输出结构；解析失败则让模型自修复一次。

        长报告的 JSON 容易被 max_tokens 截断，这里把修复请求追加进历史，
        让模型在后续对话里补全成合法 JSON（不带工具，一次修复机会）。
        """
        try:
            return self._validate(content)
        except Exception:
            messages = messages + [
                {"role": "assistant", "content": content},
                {"role": "user", "content": (
                    "你上面的输出不是合法的 JSON 或结构不完整。"
                    "请重新输出，只输出符合要求结构的完整 JSON，不要任何解释。"
                )},
            ]
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=messages,                    # 不带 tools：只要求它补全 JSON，不要再去调工具
                response_format={"type": "json_object"} if self.output_schema else None,
            )
            return self._validate(response.choices[0].message.content)

    def _validate(self, content: str) -> dict:
        """把文本解析成输出结构；失败抛出异常（由调用方决定怎么处理）。"""
        if self.output_schema is None:
            return {"content": content}
        return self.output_schema.model_validate_json(content)


def _description(fn) -> str:
    """从函数 docstring 第一行取工具描述。"""
    return (fn.__doc__ or "").strip().split("\n")[0]


def _parameters(fn) -> dict:
    """从函数签名生成 JSON Schema（需要 pydantic 支持）。

    演示版固定返回宽松 schema；真实版可以用 `pydantic` 的
    `TypeAdapter` 或 `inspect.signature` 生成精确的参数结构。
    这里为了保证开箱即用，让模型自由传参、靠工具侧校验兜底。
    """
    return {
        "type": "object",
        "properties": {},
    }
