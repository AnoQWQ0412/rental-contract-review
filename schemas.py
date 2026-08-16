"""输出校验：把模型输出变成类型安全的对象（护栏之一）。

模型可能输出残缺/类型不对的 JSON，pydantic 会在解析时报错，
我们就能拦住坏输出，不把它当"正常结果"交给用户。
"""

from typing import Literal

from pydantic import BaseModel, Field


class Risk(BaseModel):
    """单个风险点。"""

    item: str = Field(description="风险点名称")
    level: Literal["高", "中", "低", "待复核"] = Field(
        description="风险等级；拿不准等级或是否构成风险时标『待复核』，由人工确认"
    )
    detail: str = Field(description="风险描述")
    basis: str = Field(description="依据的条款或规程")


class ReviewResult(BaseModel):
    """合同审查的最终输出结构。"""

    document_type: Literal["住宅", "商铺", "办公", "设备", "车辆", "其他", "非租赁"] = Field(
        description="识别出的文档类型；非租赁表示输入不是租赁合同"
    )
    risks: list[Risk] = Field(default_factory=list, description="风险清单，可为空列表")
    pass_: Literal["是", "否", "待复核"] = Field(
        alias="pass", description="是否通过审查"
    )
    summary: str = Field(description="总体评价")

    model_config = {"populate_by_name": True}  # 允许用 JSON 里的 pass 字段名
