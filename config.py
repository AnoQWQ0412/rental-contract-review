"""全局配置：API key 的获取与保存。

key 的优先级（第一条命中的生效）：
  1. 环境变量（DEEPSEEK_API_KEY）
  2. 本地保存的文件（首次运行时让你填一次，存到项目根目录 .agent_key）
  3. 都没有 → 弹出输入框让你填（交互式），然后保存供下次使用

换模型商：往 _PROVIDERS 里加一行即可，代码不用改。
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

# 各 provider 的 base_url 和 key 环境变量名。
# ⚠️ base_url 以各家官方文档为准，这里给的是常用地址。
_PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    # 以后拿到其他家的 key，在这里加一行即可，代码不用改：
    # "moonshot":  {"base_url": "https://api.moonshot.cn/v1",                    "api_key_env": "MOONSHOT_API_KEY"},
    # "dashscope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key_env": "DASHSCOPE_API_KEY"},
}

MODEL = "deepseek-chat"  # Agent 一律用 chat；deepseek-reasoner 工具调用不稳定

# 本地保存 key 的文件（明文，仅本机使用）
_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".agent_key")


def get_api_key(provider: str = "deepseek") -> str:
    """获取 API key。优先级：环境变量 → 本地文件 → 交互式输入并保存。"""
    if provider not in _PROVIDERS:
        raise ValueError(f"未知 provider: {provider}，可选: {list(_PROVIDERS)}")

    env_name = _PROVIDERS[provider]["api_key_env"]

    # 1. 环境变量（优先级最高，部署场景用）
    key = os.environ.get(env_name, "").strip()
    if key:
        return key

    # 2. 本地文件（用户填过一次后保存）
    if os.path.exists(_KEY_FILE):
        key = open(_KEY_FILE, encoding="utf-8").read().strip()
        if key:
            return key

    # 3. 交互式输入一次，保存供下次使用
    try:
        key = input(f"请输入你的 {provider} API key（只保存到本机 {_KEY_FILE}，不会上传）：").strip()
    except EOFError:                      # 非交互环境（如脚本调用）
        key = ""

    if not key:
        raise RuntimeError(
            f"没有可用的 API key。\n"
            f"请设置环境变量 {env_name}，或首次运行时会提示你输入。"
        )

    try:
        open(_KEY_FILE, "w", encoding="utf-8").write(key)
        print(f"已保存到 {_KEY_FILE}，下次不用再填。")
    except OSError:
        pass                              # 写失败不影响本次使用
    return key


def make_client(provider: str = "deepseek") -> OpenAI:
    """创建 OpenAI 兼容客户端。"""
    load_dotenv()
    cfg = _PROVIDERS[provider]
    return OpenAI(api_key=get_api_key(provider), base_url=cfg["base_url"])
