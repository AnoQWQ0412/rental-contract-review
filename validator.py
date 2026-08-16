"""输入校验：拦截"无关紧要的输入"，避免浪费 token，也避免 agent 误用。

分两层：
1. 规则预检（零成本）：看有没有"租赁"相关关键词，没有就直接判定"非租赁/无关"，不调模型
2. 模型回检（可选，只对歧义输入）：拿不准时让模型确认一次，不是租赁就拦下

对外只暴露 validate_input()。其它入口都应先调用它再走 agent。
"""

import json
import re

# 惰性导入：只有真正需要模型回检时才加载 agent（让规则层自测不依赖 openai）
_AGENT_MODULE = None


def _get_agent_module():
    global _AGENT_MODULE
    if _AGENT_MODULE is None:
        from agent import Agent  # noqa: F401
        _AGENT_MODULE = __import__("agent")
    return _AGENT_MODULE

# 租赁合同的典型关键词（出现任一即大概率是租赁相关）
_RENTAL_KEYWORDS = [
    "租赁", "出租", "承租", "押金", "租金", "租期", "出租人", "承租人",
    "出租方", "承租方", "甲方", "乙方", "lease", "rent", "tenant", "landlord",
]

# 显然不是合同/租赁的文本形态（长度/结构太随意）
_UNRELATED_HINTS = [
    "你好", "hello", "hi", "你是谁", "今天天气", "随便", "测试", "test",
    "哈哈", "哈哈", "你好呀", "吃了没", "在吗", "干什么",
]

# 强非租赁信号：含这些且不含租赁词，直接判为"其他合同"（借条/买卖/劳务等）
_NON_RENTAL_STRONG = [
    "借条", "借款", "贷款", "买卖合同", "劳动合同", "劳务合同", "工资", "欠条",
]

_VERIFY_PROMPT = """你是文档类型识别器。用户输入了一段文本，请判断它是不是一份【租赁合同】。

判断标准：
- 是租赁合同：出现了 出租方/承租方/甲方/乙方 + 租赁物（房/车/设备等）+ 押金/租金/租期 等要素
- 是其他合同（买卖、借款、劳务等）：不是租赁，但仍是合同
- 既不是合同也不像文本：闲聊、命令、乱码、无关话题

只输出 JSON，不要任何其他内容：
{"kind": "租赁合同" | "其他合同" | "无关内容", "reason": "一句话理由"}"""


def _rule_check(text: str) -> str | None:
    """零成本预检：命中显然无关/显然像租赁的特征，直接给结论。返回 kind 或 None（需模型判断）。"""
    stripped = text.strip()

    # 明显不是合同的形态
    if len(stripped) < 10:
        return "无关内容"

    lowered = stripped.lower()
    for hint in _UNRELATED_HINTS:
        if hint in lowered:
            return "无关内容"

    # 强非租赁信号（借条/借款/买卖/劳务等）→ 其他合同，除非同时含明确租赁词
    for sign in _NON_RENTAL_STRONG:
        if sign in stripped:
            if any(k in stripped for k in ["租赁", "出租", "承租", "押金"]):
                break  # 仍可能是租赁，交模型判断
            return "其他合同"

    # 明显是租赁：出现强关键词（甲方/乙方 + 押金/租金）
    if any(k in stripped for k in ["出租方", "承租方", "甲方", "乙方"]):
        if any(k in stripped for k in ["押金", "租金", "租期", "租赁"]):
            return "租赁合同"

    return None


def _model_check(text: str, verify_agent) -> str:
    """模型回检：确认文本类型。verify_agent 是 agent.Agent 实例。"""
    response = verify_agent.run(text)
    # 无 output_schema 时 run() 返回 {"content": ...}
    content = response["content"] if isinstance(response, dict) and "content" in response else None
    if content is None:
        content = json.dumps(response, ensure_ascii=False) if not isinstance(response, str) else response
    try:
        data = json.loads(content)
        return data.get("kind", "无关内容")
    except Exception:
        return "无关内容"


def build_verify_agent():
    """构造轻量类型识别 agent（不加载任何工具，只做文本分类）。"""
    mod = _get_agent_module()
    return mod.Agent(
        system_prompt=_VERIFY_PROMPT,
        tools_defs=[],
        tools_impl={},
    )


def validate_input(text: str, verify_agent=None) -> dict:
    """校验输入，返回 {'ok': bool, 'kind': str, 'reason': str, 'text': str}。

    - kind: 租赁合同 / 其他合同 / 无关内容
    - ok=True 才应继续走审查 agent；否则提示用户重新输入
    """
    if not text or not text.strip():
        return {"ok": False, "kind": "无关内容", "reason": "输入为空", "text": text}

    # 第一层：规则预检（零成本）
    quick = _rule_check(text)
    if quick == "无关内容":
        return {"ok": False, "kind": "无关内容",
                "reason": "输入看起来不是一份租赁合同，请粘贴合同文本再试。", "text": text}
    if quick == "租赁合同":
        return {"ok": True, "kind": "租赁合同", "reason": "", "text": text}

    # 第二层：模型回检（只对歧义输入，省 token）
    if verify_agent is not None:
        kind = _model_check(text, verify_agent)
        if kind == "租赁合同":
            return {"ok": True, "kind": "租赁合同", "reason": "", "text": text}
        if kind == "其他合同":
            return {"ok": False, "kind": "其他合同",
                    "reason": "这是一份其他类型的合同（非租赁），本工具目前只审查租赁合同。", "text": text}
        return {"ok": False, "kind": "无关内容",
                "reason": "输入看起来不是一份租赁合同，请粘贴合同文本再试。", "text": text}

    # 没有 verify_agent 时，规则层已判定的其他合同直接拦；歧义则放行（不误拦）
    if quick == "其他合同":
        return {"ok": False, "kind": "其他合同",
                "reason": "这是一份其他类型的合同（非租赁），本工具目前只审查租赁合同。", "text": text}
    return {"ok": True, "kind": "租赁合同", "reason": "", "text": text}


if __name__ == "__main__":
    # 快速自测（不调 API，只测规则层）
    for sample in ["你好", "今天天气怎么样", "甲方押金9万租期一年", "借条一张：李某向王某借款5万元",
                   "甲乙双方就设备租赁达成如下协议"]:
        print(f"{sample!r:30} → {validate_input(sample)}")
