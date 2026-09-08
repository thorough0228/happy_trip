"""
硬规则校验(简化版)。

LLM 通过 schema 校验 ≠ 输出合法。LLM 可能违反业务规则:
- 编了候选外的景点
- 同一景点在同一天重复出现

系统不校验酒店 / 餐厅 / 预算(产品层已去掉),只校验景点相关。
"""
from app.models.schemas import TripPlan
from app.planner.context import PlannerContext


def validate_plan(plan: TripPlan, ctx: PlannerContext) -> list[str]:
    """
    对 LLM 输出的 TripPlan 做硬规则校验。

    Returns:
        错误列表。空列表 = 通过校验。
    """
    errors: list[str] = []

    # 候选集(从 ctx 提取,加速查询)
    attraction_names = {p.name for p in ctx.attractions}

    # 1. 景点候选约束
    for i, day in enumerate(plan.days):
        for a in day.attractions:
            if a.name not in attraction_names:
                errors.append(
                    f"day{i+1}:景点'{a.name}'不在候选列表中"
                )

    # 2. 天数匹配 — 这一项与 TripRequest 比对,plan 没有 request 引用,需要在 plan_trip 里拦截

    # 3. 多样性:同一景点不得在同一天重复出现
    for i, day in enumerate(plan.days):
        seen: set[str] = set()
        for a in day.attractions:
            name = a.name.strip()
            if name in seen:
                errors.append(
                    f"day{i+1}:景点'{name}'重复出现"
                )
            else:
                seen.add(name)

    return errors
