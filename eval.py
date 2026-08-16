"""评估脚本：跑一遍评估集，输出通过率。

这是专用 agent 开发的"唯一北极星指标"：
每次改提示词或工具，跑一次 `python eval.py`，看通过率变好还是变坏。

扩展方法：
- eval_set.json 里加案例（input + expected + note）
- 需要更严格比对时，把 eval_case 里的判断写细
"""

import json
from pathlib import Path

from contract_agent import build_agent
from tools import bind_contract


def eval_case(result, expected) -> bool:
    """判断一个案例是否算通过。可按需加细（比对风险点列表、等级等）。"""
    # result 是 pydantic 对象（ReviewResult），字段是 pass_
    expected_pass = expected.get("pass")
    if expected_pass is not None and str(getattr(result, "pass_", "")) != str(expected_pass):
        return False
    expected_type = expected.get("document_type")
    if expected_type is not None and getattr(result, "document_type", "") != expected_type:
        return False
    return True


def run_eval(verbose: bool = False) -> None:
    cases = json.loads(Path("eval_set.json").read_text(encoding="utf-8"))
    if not cases:
        print("评估集为空，先往 eval_set.json 里加真实案例")
        return

    agent = build_agent()          # 复用 contract_agent 里的构造（含完整 system 提示词）
    passed, failed = 0, []

    for case in cases:
        bind_contract(case["input"])
        result = agent.run(case["input"])
        if eval_case(result, case["expected"]):
            passed += 1
        else:
            failed.append(case)
            if verbose:
                print(f"\n❌ 未通过: {case.get('note', '')}")
                print(f"   期望 pass={case['expected'].get('pass')}，实际 pass={getattr(result, 'pass_', None)}")

    total = len(cases)
    print(f"\n通过率: {passed}/{total} ({passed / total * 100:.0f}%)")
    if failed:
        print("未通过的案例：")
        for case in failed:
            print(f"  - {case.get('note', '')}")


if __name__ == "__main__":
    run_eval(verbose=True)
