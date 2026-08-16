"""HTTP 服务：把合同审查 agent 变成可被移动端调用的接口。

这是"打包 APK"的第一步：
  手机 APP（界面）→ HTTP → 本服务（跑 agent）→ 返回 JSON

API key 管理：浏览器界面里填一次，保存到本机 .agent_key，之后免填。
（个人使用足够；若要多用户上线，再加服务端 key + 鉴权。）

启动：python server.py
访问：浏览器打开 http://127.0.0.1:8000  （手机在同一 WiFi 时，用电脑局域网 IP 访问）
"""

import json
import time

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
from contract_agent import build_agent, log_run
from tools import bind_contract
from validator import build_verify_agent, validate_input

app = FastAPI(title="租赁合同审查 Agent")

# 全局单例（Agent 是无状态的，可复用；请求进来并发用同一实例即可）
_agent = None
_verify_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def get_verify_agent():
    global _verify_agent
    if _verify_agent is None:
        _verify_agent = build_verify_agent()
    return _verify_agent


class ReviewRequest(BaseModel):
    text: str                      # 合同全文


class ReviewResponse(BaseModel):
    ok: bool                       # 是否成功
    kind: str = ""                 # 输入类型：租赁合同 / 其他合同 / 无关内容
    error: str = ""                # ok=False 时的提示
    result: dict | None = None     # ok=True 时的审查报告
    elapsed: float = 0             # 耗时（秒）


class KeyRequest(BaseModel):
    api_key: str                   # 用户在网页填的 DeepSeek key


class KeyResponse(BaseModel):
    ok: bool
    error: str = ""


@app.post("/api/review")
def review(req: ReviewRequest) -> ReviewResponse:
    """审查一份合同。先校验输入，不是租赁就拦截。"""
    t0 = time.time()

    # 输入校验
    check = validate_input(req.text, get_verify_agent())
    if not check["ok"]:
        return ReviewResponse(ok=False, kind=check["kind"], error=check["reason"])

    try:
        bind_contract(req.text)
        result = get_agent().run(req.text)
        # result 是 pydantic 对象 → 转 dict
        data = result.model_dump(by_alias=True) if hasattr(result, "model_dump") else result
        log_run(req.text, result)   # 留档
        return ReviewResponse(ok=True, kind="租赁合同", result=data, elapsed=round(time.time() - t0, 2))
    except RuntimeError as e:
        return ReviewResponse(ok=False, kind="租赁合同", error=f"审查未完成: {e}")
    except Exception as e:
        return ReviewResponse(ok=False, kind="租赁合同",
                              error=f"审查失败，请人工检查: {e}")


@app.post("/api/set_key")
def set_key(req: KeyRequest) -> KeyResponse:
    """保存网页里填的 API key 到本机 .agent_key，供后续请求使用。"""
    key = (req.api_key or "").strip()
    if not key:
        return KeyResponse(ok=False, error="key 不能为空")
    try:
        with open(config._KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key)
    except OSError as e:
        return KeyResponse(ok=False, error=f"保存失败: {e}")
    global _agent
    _agent = None                   # 让下一个请求用新 key 重建 agent
    return KeyResponse(ok=True)


@app.get("/api/has_key")
def has_key() -> dict:
    """查询是否已配置 key（网页据此决定是否弹设置）。"""
    try:
        key = config.get_api_key()
        return {"has_key": bool(key)}
    except Exception:
        return {"has_key": False}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "rental-review-agent"}


# 前端静态页面（打包成 APK 时的"壳"）
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    print("启动服务：浏览器访问 http://127.0.0.1:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
