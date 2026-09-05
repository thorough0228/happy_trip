"""
Reviewer Agent — 业务校验软提示。

调用一次 LLM,基于 validate_plan 的 errors 列表 + TripPlan + PlannerContext,
生成简短中文警告(2-4 条),作为 plan.notes 追加,提示用户哪些项目可能不准确。

关键设计:
- 独立于 planner,不进入 planner 重试循环,避免浪费 token
- prompt 极简,只看 errors + plan + ctx 概要,要求输出简短中文数组
- 失败时降级为 errors 原文(不抛错,不影响 plan 返回)
"""
from app.models.schemas import TripPlan
from app.planner.context import PlannerContext
from app.services.llm import chat


REVIEWER_SYSTEM_PROMPT = """你是行程质量审核员。任务:基于下面提供的【校验错误】和【行程计划】,生成 2-4 条简短中文警告,提示用户哪些地方可能不准确。

要求:
- 每条警告一行,不超过 30 字
- 用用户能看懂的语言,不要用"违反规则""违规"等批判词
- 重点说"这个景点不在候选中,建议你确认"这类可操作建议
- 输出纯 JSON 数组: ["警告1", "警告2", ...]
- 不要重复输入,不要解释"""


def _build_reviewer_messages(plan: TripPlan, errors: list[str], ctx: PlannerContext) -> list[dict]:
    """构造 reviewer 的 messages。"""
    # 摘要信息(避免塞整个 plan,省 token)
    plan_summary = {
        "title": plan.title,
        "destination": plan.destination,
        "days_count": len(plan.days),
        "budget_total": plan.budget.total,
    }
    ctx_summary = {
        "attractions_count": len(ctx.attractions),
        "hotels_count": len(ctx.hotels),
        "food_count": len(ctx.food),
    }
    user_prompt = (
        "【校验错误】\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\n【行程概要】\n"
        + str(plan_summary)
        + "\n\n【候选池规模】\n"
        + str(ctx_summary)
        + "\n\n请输出 JSON 数组格式的警告(2-4 条):"
    )
    return [
        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


async def review_warnings(plan: TripPlan, errors: list[str], ctx: PlannerContext) -> list[str]:
    """
    调一次 LLM 生成软警告。失败时降级为 errors 原文,不抛错。

    Returns:
        中文警告列表,作为 plan.notes 追加。
    """
    messages = _build_reviewer_messages(plan, errors, ctx)
    try:
        raw = await chat(messages, temperature=0.3)
        # reviewer 输出也是 JSON,需要解析
        import json

        warnings = json.loads(raw)
        if isinstance(warnings, list):
            return [str(w) for w in warnings if w]
        # 如果 LLM 返回的不是 list,降级处理
        return [f"行程有以下项目可能不准确,请确认: {'; '.join(errors[:3])}"]
    except Exception:
        # 降级:把 errors 原文拼成一句话,保证至少有提示
        return [f"行程有以下项目可能不准确,请确认: {'; '.join(errors[:3])}"]