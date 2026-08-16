"""交互式入口：不绑定示例合同，可随意输入。

用法：
    python interactive.py                 # 交互循环：反复输入文件路径 或 直接粘贴文本
    python interactive.py 合同.txt        # 一次性审查一个文件

支持多行粘贴：连续输入，最后输入一个空行表示提交；输入 q 回车退出。
"""

import json
import sys
from pathlib import Path

from contract_agent import build_agent, log_run
from tools import bind_contract
from validator import build_verify_agent, validate_input


def read_text(path: Path) -> str:
    """读文件，兼容 utf-8 和 gbk（Windows 常见编码）。"""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="gbk")


def read_one_input() -> str | None:
    """读一段输入，返回合同文本；返回 None 表示退出。

    规则：
    - 第一行如果是 q / quit / exit → 退出
    - 第一行如果是个存在的文件路径 → 读文件
    - 否则当作粘贴文本的第一行，继续收多行，空行 = 提交
    """
    print("\n" + "-" * 60)
    print("输入合同（二选一）：")
    print("  1. 文件路径 → 直接读取")
    print("  2. 直接粘贴文本（可多行，最后输入一个空行表示结束）")
    print("输入 q 回车退出")
    print("-" * 60)

    first = input("> ").strip()
    if first.lower() in ("q", "quit", "exit"):
        return None

    # 是文件路径？
    p = Path(first)
    if p.exists():
        return read_text(p)

    # 否则作为粘贴文本的第一行，继续收多行
    lines = [first]
    while True:
        line = input("… ").strip()
        if line == "":            # 空行 = 提交
            break
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    # 命令行参数模式：python interactive.py <文件路径>
    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"文件不存在: {path}")
            return
        contract_text = read_text(path)
        check = validate_input(contract_text)
        if not check["ok"]:
            print(f"❌ {check['reason']}")
            return
        agent = build_agent()
        bind_contract(contract_text)   # 绑定到工具，避免调用时重复传全文
        print(f"📄 收到 {len(contract_text)} 字，开始审查...\n")
        result = agent.run(contract_text)
        print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))
        log_path = log_run(contract_text, result)
        print(f"\n✅ 已留档到 {log_path}")
        return

    # 交互循环模式
    agent = build_agent()
    verify_agent = build_verify_agent()   # 类型识别 agent（只在歧义输入时调用，省 token）
    print("租赁合同审查 agent —— 交互模式（输入 q 退出）")

    while True:
        contract_text = read_one_input()
        if contract_text is None:
            print("再见！")
            break
        if not contract_text.strip():
            print("输入为空，跳过。")
            continue

        # 输入校验：不是租赁合同就提示重新输入，不浪费审查 token
        check = validate_input(contract_text, verify_agent)
        if not check["ok"]:
            print(f"\n⚠️ {check['reason']}")
            print("  请粘贴一份租赁合同文本，或输入 q 退出。\n")
            continue

        print(f"📄 收到 {len(contract_text)} 字，开始审查...\n")
        try:
            bind_contract(contract_text)   # 绑定到工具，避免调用时重复传全文
            result = agent.run(contract_text)
            print("\n" + "=" * 60)
            print("📋 审查结果")
            print("=" * 60)
            print(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False, indent=2))
            log_path = log_run(contract_text, result)
            print(f"\n✅ 已留档到 {log_path}")
        except RuntimeError as e:
            print(f"❌ {e}")          # 比如达到最大轮数
        except Exception as e:
            # 输出多次修复仍无法解析 → 兜底"待复核"，不让坏输出流出
            print(f"❌ 输出解析失败: {e}")
            print("   已按『待复核』处理，请人工检查原始留档。")


if __name__ == "__main__":
    main()
