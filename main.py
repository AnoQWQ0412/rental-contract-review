"""演示入口：跑一条内置的示例合同，看 agent 的完整审查过程。

用法：python main.py
"""
import json

from contract_agent import build_agent, log_run
from tools import bind_contract

SAMPLE = """甲方：XX商业管理有限公司。乙方：张三。
乙方承租甲方位于本市XX路的商铺一间，月租金8000元。
乙方向甲方支付押金50000元，租赁期满后经甲方验收合格，押金无息退还。
租期自2026年3月1日起，租期一年。"""


def main() -> None:
    print("=" * 60)
    print("  租赁合同审查 agent - 演示")
    print("=" * 60)
    print(f"\n📄 待审查合同：\n{SAMPLE}\n")

    agent = build_agent()
    bind_contract(SAMPLE)
    print("🔍 开始审查（观察模型如何调用工具）...\n")
    result = agent.run(SAMPLE)

    print("\n" + "=" * 60)
    print("📋 审查结果")
    print("=" * 60)
    print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))

    log_path = log_run(SAMPLE, result)
    print(f"\n✅ 已留档到 {log_path}")


if __name__ == "__main__":
    main()
