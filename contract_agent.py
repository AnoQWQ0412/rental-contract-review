"""租赁合同审查 agent 的领域入口。

职责：
1. 定义领域系统提示词（行业规则）
2. 用 tools.TOOL_IMPL + 提示词 + 输出结构，组装出一个 Agent
3. 把每次审查留档到 logs/（可观测性，出了问题能复盘）
4. 提供命令行用法：python contract_agent.py <合同文件或文本>
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent import Agent
from config import make_client
from schemas import ReviewResult
from tools import TOOLS, TOOL_IMPL, bind_contract

LOG_DIR = Path("logs")

SYSTEM_PROMPT = """你是一名资深的租赁合同审查员，能处理各类租赁合同（住宅、商铺、办公、设备、车辆等）。

审查流程：
1. 阅读输入的全文，先判断它属于什么类型（住宅/商铺/办公/设备/车辆/其他/非租赁）
2. 必须调用 load_skill 加载『通用』规程（基础风险检查清单）
3. 再调用 load_skill 加载对应类型的专属规程（如 住宅/商铺/办公/设备/车辆）；无法确定类型则加载『其他』
4. 按两份规程逐条核对合同，输出审查结果
5. 需要法规依据时调用 lookup_regulation 查证

工具使用规则：
- load_skill 和 lookup_regulation 是用来获取外部知识的，应当使用
- 不要调用工具去"读合同"——合同全文已在上方，直接阅读即可
- 已加载的规程不要重复加载（一份类型规程 + 一份通用规程即可）

审查要求：
1. 只根据合同原文判断，不臆测条款内容
2. 未约定的点如实记录为"未约定"，而不是"无风险"
3. 条款不明确或证据不足 → 标"待复核"，不强行下结论
4. 输出 JSON 格式，结构为：
   {"document_type": "住宅/商铺/办公/设备/车辆/其他/非租赁",
    "risks": [{"item": "风险点名称", "level": "高/中/低/待复核", "detail": "风险描述", "basis": "依据的条款或规程"}],
    "pass": "是/否/待复核", "summary": "总体评价"}
   说明：单个风险点拿不准等级时 level 用"待复核"；整份合同拿不准是否通过时 pass 用"待复核"。

非租赁内容处理：如果输入不是租赁合同（如借款、买卖、劳务合同），document_type 填"非租赁"，risks 可为空，summary 中说明这更可能是什么类型的合同，不强行套用租赁规则。"""


def build_agent() -> Agent:
    """组装领域 agent（评估脚本也用它，保证提示词一致）。"""
    return Agent(
        system_prompt=SYSTEM_PROMPT,
        tools_defs=TOOLS,          # 给模型看的"说明书"（手写精确 schema）
        tools_impl=TOOL_IMPL,      # 给代码执行的"实现"（函数字典）
        output_schema=ReviewResult,
    )


def log_run(contract_text: str, result) -> Path:
    """把一次审查留档，返回日志文件路径。"""
    LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = LOG_DIR / f"review_{stamp}.json"
    payload = {
        "input": contract_text,
        "output": result.model_dump(by_alias=True) if hasattr(result, "model_dump") else result,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python contract_agent.py <合同文件路径 或 直接粘贴合同文本>")
        return

    arg = sys.argv[1]
    if Path(arg).exists():
        contract_text = Path(arg).read_text(encoding="utf-8")
    else:
        contract_text = arg

    # 做个健康检查：确保 API key 配好了，比跑到一半才报错强
    make_client()

    print(f"正在审查（共 {len(contract_text)} 字）...\n")
    agent = build_agent()
    bind_contract(contract_text)   # 先把合同绑定进工具，避免调用时重复传全文
    result = agent.run(contract_text)

    # 用 by_alias=True 打印 pass 字段（而不是 pass_）
    print("\n" + "=" * 50)
    print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))

    log_path = log_run(contract_text, result)
    print(f"\n已留档: {log_path}")


if __name__ == "__main__":
    main()
