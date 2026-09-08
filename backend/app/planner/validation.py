"""
硬规则校验(简化版)。

LLM 通过 schema 校验 ≠ 输出合法。LLM 可能违反业务规则:
- 编了候选外的景点
- 预算明细加总对不上 total
- 预算远低于用户预期(花得太少)
- 景点天数对不上 travel_days
- 同一景点在同一天重复出现

本版本不再校验酒店 / 餐厅(系统不再规划这些),只校验景点相关 + 预算一致性。
"""
from app.models.schemas import TripPlan
from app.planner.context import PlannerContext


# 预算利用率下限(统一 80%,不分档)
_BUDGET_UTILIZATION_MIN = 0.80


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

    # 2. 预算一致性(attractions 总价 vs total,允许 ±5%)
    budget = plan.budget
    items_sum = budget.total_attractions
    if items_sum > 0:
        diff_ratio = abs(budget.total - items_sum) / max(items_sum, 1.0)
        if diff_ratio > 0.05:
            errors.append(
                f"预算不一致:total_attractions={items_sum:.0f}, total={budget.total:.0f}, 误差={diff_ratio:.1%}"
            )

    # 3. 预算利用率(防止 LLM 偷懒出低价行程,统一 80% 下限)
    user_budget = ctx.request.budget_constraint.amount
    if user_budget > 0 and budget.total > 0:
        actual_ratio = budget.total / user_budget
        if actual_ratio < _BUDGET_UTILIZATION_MIN:
            errors.append(
                f"预算利用过低:total={budget.total:.0f},"
                f" 用户预算={user_budget:.0f},"
                f" 利用率={actual_ratio:.0%} < 下限 {_BUDGET_UTILIZATION_MIN:.0%}"
            )

    # 4. 天数匹配 — 这一项与 TripRequest 比对,plan 没有 request 引用,需要在 plan_trip 里拦截

    # 5. 多样性:同一景点不得在同一天重复出现
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