"""
硬规则校验。

LLM 通过 schema 校验 ≠ 输出合法。LLM 可能违反业务规则:
- 编了候选外的景点/酒店/餐厅
- 编了"附近餐厅/当地小吃"这类占位词
- 预算明细加总对不上 total
- 景点天数对不上 travel_days
"""
from app.models.schemas import TripPlan
from app.planner.context import PlannerContext


# 占位词白名单(命中即判定违规)
PLACEHOLDER_MEALS = {
    "附近餐厅", "当地小吃", "酒店晚餐", "酒店早餐", "无", "不适用", "/",
    "nearby restaurant", "local snack", "hotel restaurant",
}


def validate_plan(plan: TripPlan, ctx: PlannerContext) -> list[str]:
    """
    对 LLM 输出的 TripPlan 做硬规则校验。

    Returns:
        错误列表。空列表 = 通过校验。
    """
    errors: list[str] = []

    # 候选集(从 ctx 提取,加速查询)
    attraction_names = {p.name for p in ctx.attractions}
    hotel_names = {p.name for p in ctx.hotels}
    food_names = {p.name for p in ctx.food}

    # 1. 候选约束
    for i, day in enumerate(plan.days):
        for a in day.attractions:
            if a.name not in attraction_names:
                errors.append(
                    f"day{i+1}:景点'{a.name}'不在候选列表中"
                )

        if day.hotel and day.hotel.name not in hotel_names:
            errors.append(
                f"day{i+1}:酒店'{day.hotel.name}'不在候选列表中"
            )

        for meal_type, meal in day.meals.items():
            if meal is None:
                continue
            # 占位词检测
            if meal.name.strip() in PLACEHOLDER_MEALS:
                errors.append(
                    f"day{i+1}.{meal_type}:餐厅名'{meal.name}'是占位词"
                )
                continue
            # 候选约束
            if meal.name not in food_names:
                errors.append(
                    f"day{i+1}.{meal_type}:餐厅'{meal.name}'不在候选列表中"
                )

    # 2. 预算一致性(各项加总 vs total,允许 ±5%)
    budget = plan.budget
    items_sum = (
        budget.total_attractions
        + budget.total_hotels
        + budget.total_meals
        + budget.total_transportation
    )
    if items_sum > 0:
        diff_ratio = abs(budget.total - items_sum) / max(items_sum, 1.0)
        if diff_ratio > 0.05:
            errors.append(
                f"预算不一致:各项加总={items_sum:.0f}, total={budget.total:.0f}, 误差={diff_ratio:.1%}"
            )

    # 3. 天数匹配
    # 注意:这一项与 TripRequest 比对,plan 没有 request 引用,需要在 plan_trip 里拦截

    # 4. 多样性:同一餐厅不得在多餐重复出现
    seen_meal: dict[str, str] = {}  # name -> 第一次出现的位置
    for i, day in enumerate(plan.days):
        for meal_type, meal in day.meals.items():
            if meal is None:
                continue
            location = f"day{i+1}.{meal_type}"
            name = meal.name.strip()
            if name in seen_meal:
                errors.append(
                    f"餐厅'{name}'重复出现:{seen_meal[name]} 和 {location},应换其他候选餐厅"
                )
            else:
                seen_meal[name] = location

    return errors