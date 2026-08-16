"""领域工具：把"专业动作"变成函数。换行业 = 重写这个文件。

设计原则：
- 每个函数自带 JSON Schema 定义（TOOLS 列表），供模型调用
- 领域知识放在函数实现里（这里是法规要点 + skill 规程，可换成数据库/向量检索）
- 函数要"尽力而为"：宁可返回"查无"，也不要编造
"""

import re
from pathlib import Path

SKILLS_DIR = Path(__file__).parent / "skills"

# 可加载的规程列表（供 schema enum 用，让模型知道有哪些可选）
SKILL_NAMES = [p.stem for p in SKILLS_DIR.glob("*.md")]

# ────────────────────────────────────────────────────────────
# 工具定义：给模型的"使用说明书"
# ────────────────────────────────────────────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_clause",
            "description": (
                "在已提供的合同中检索包含指定关键词的条款原文。"
                "需要准确定位某条款原文时使用（合同全文已在上方，通常无需调用）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "检索关键词，如 押金、违约金、租期"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_regulation",
            "description": (
                "查询法律/法规中关于某个条款的规定要点。"
                "审查合同需要引用法规依据时使用。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "法规主题，如 押金、租赁期限、违约金上限"},
                },
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": (
                "按需加载一份租赁审查规程（规则清单）。"
                "审查前先识别租赁类型，加载对应规程；通用风险用『通用』规程。"
                "必须且只能加载一份：通用 + 该类型（通用是基础，自动包含）。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "enum": SKILL_NAMES,
                        "description": "要加载的规程名称",
                    },
                },
                "required": ["skill"],
            },
        },
    },
]

# 工具名 → 函数 的映射（供 agent.py 分发表调用）
TOOL_IMPL = {}


def _tool(name):
    """注册工具函数到分发表。"""
    def decorator(fn):
        TOOL_IMPL[name] = fn
        return fn
    return decorator


# ────────────────────────────────────────────────────────────
# 领域知识库
# ────────────────────────────────────────────────────────────
REGULATIONS = {
    "押金": (
        "押金金额一般不超过月租金的1-2倍（各地规定不同，以地方标准为准）；"
        "收取押金应开具收据；租赁期满且无违约应无息退还。"
        "押金明显高于月租金1-2倍的条款存在风险。"
    ),
    "租赁期限": (
        "租赁期限应明确起止日期；未约定或约定不明视为不定期租赁，"
        "双方可随时解除合同，对承租方不利。"
    ),
    "违约金": (
        "违约金过高可请求法院酌减，以实际损失为基准；"
        "每日万分之几的滞纳金标准为常见，约定过高的违约金条款存在被酌减的风险。"
    ),
    "租赁合同必备条款": (
        "租赁合同一般应写明：租赁物名称及状况、租金及支付方式、押金、"
        "租赁期限、使用用途、维修责任、违约责任、合同解除条件等。"
    ),
}


# ────────────────────────────────────────────────────────────
# 工具实现
# ────────────────────────────────────────────────────────────

@_tool("search_clause")
def search_clause(contract_text: str, keyword: str) -> str:
    """在合同中检索包含指定关键词的条款原文。

    演示版用简单分句；真实版可换成按章节/条款结构解析。
    """
    sentences = re.split(r"[。；\n]", contract_text)
    hits = [s.strip() for s in sentences if keyword in s]
    if not hits:
        return f"合同中未找到包含『{keyword}』的条款"
    return "\n".join(f"- {h}" for h in hits)


def bind_contract(contract_text: str) -> None:
    """把当前审查的合同绑定到 search_clause，调用时只需传 keyword。

    目的：合同全文已经在对话历史里，不要在工具调用时重复传递，避免消息膨胀。
    """
    global _current_contract
    _current_contract = contract_text


def search_clause_by_keyword(keyword: str) -> str:
    """供分发表调用的接口：自动带上已绑定的合同。"""
    if not _current_contract:
        return "错误：合同尚未绑定，请先绑定合同再调用"
    return search_clause(_current_contract, keyword)


_current_contract = ""

# 分发表指向绑定版，这样工具调用时只需传 keyword
TOOL_IMPL["search_clause"] = search_clause_by_keyword


@_tool("lookup_regulation")
def lookup_regulation(topic: str) -> str:
    """法规要点查询。演示版用内置字典；真实版可换成数据库或向量检索。"""
    # 支持别名
    topic = topic.replace("押金", "押金").strip()
    key = next((k for k in REGULATIONS if k in topic), None)
    if key is None:
        return f"暂无『{topic}』相关法规要点，请人工确认"
    return REGULATIONS[key]


@_tool("load_skill")
def load_skill(skill: str) -> str:
    """加载一份租赁审查规程。按需加载，避免全部规则挤在 system prompt 里。"""
    path = SKILLS_DIR / f"{skill}.md"
    if not path.exists():
        return f"没有『{skill}』这份规程，可选：{', '.join(SKILL_NAMES)}"
    return path.read_text(encoding="utf-8")
