"""
Reviewer Agent — 业务校验连续失败后提出改进方案,让 Planner 基于方案再生成。

调用时机:plan_trip 主循环连续 2 次 LLM 生成仍未通过业务校验时。

输入:
- req: 用户原始 TripRequest(保留偏好、主题等)
- ctx: PlannerContext(事实源,候选 POI 池)
- last_plan: 上一次 LLM 生成的草稿(可能有违规字段)
- errors: validate_plan 给出的错误列表

输出:
- list[str] 改进建议,每条针对一个错误,说明"应替换为 ctx 中的哪个具体 POI"

reviewer 不生成 plan,只提建议。Plan 由 Planner 拿到建议后再次生成。
"""
import json
from app.models.schemas import TripRequest
from app.models.schemas import TripPlan
from app.planner.context import PlannerContext
from app.services.llm import chat


REVIEWER_SYSTEM_PROMPT = """你是行程质量审查员。Planner 之前的两次尝试都未通过业务校验。
任务:**不要生成完整行程**,只针对每个错误提出具体的改进方案(基于候选池)。

要求:
1. 对每条错误,给出 1-2 句具体修复方向,引用 ctx 候选池中真实存在的 POI 名
2. 输出分点(每条一行),便于 Planner 解析执行
3. 不要解释错误本身,只说"应该改成什么"
4. 不要写 JSON,纯文本分点输出

示例格式:
- 景点'X'不在候选中,替换为 ctx 中的'Y'(同类景点)
- 餐厅'Z'在第 2 天和第 3 天重复,改成 ctx 中的'W'
- 预算加总不对,景点合计 X 元 / 酒店 X 元 / 餐饮 X 元 / 交通 X 元,调整后 total 应为 X 元"""


def _build_reviewer_messages(
    req: TripRequest,
    ctx: PlannerContext,
    last_plan: TripPlan,
    errors: list[str],
) -> list[dict]:
    """构造 reviewer 的 messages。"""
    user_prompt = (
        "【校验错误列表】(逐一针对)\n"
        + "\n".join(f"- {e}" for e in errors)
        + "\n\n【用户核心约束(不要破坏)】\n"
        f"- 目的地:{req.destination}\n"
        f"- 旅行天数:{req.travel_days}\n"
        f"- 主题/偏好:{', '.join(req.preferences) if req.preferences else '无'}\n"
        f"- 负面约束:{', '.join(req.negative_constraints) if req.negative_constraints else '无'}\n"
        "\n【PlannerContext — 候选池,改进方案必须引用这里的事实】\n"
        + ctx.summary()
        + "\n\n请只输出改进方案(分点,每条 1-2 行,基于 ctx):"
    )
    return [
        {"role": "system", "content": REVIEWER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


async def review_propose(
    req: TripRequest,
    ctx: PlannerContext,
    last_plan: TripPlan,
    errors: list[str],
) -> list[str]:
    """
    输出针对每个错误的具体改进方案。

    Returns:
        改进方案列表,每个 string 一条建议。
        reviewer 失败时降级为 errors 原文(确保 Planner 至少收到反馈)。
    """
    messages = _build_reviewer_messages(req, ctx, last_plan, errors)
    try:
        raw = await chat(messages, temperature=0.3)
    except Exception as e:
        print(f"[reviewer] 调用失败: {e},降级为 errors 原文")
        return [f"- {e}" for e in errors]

    # 解析:按行切分,过滤 markdown 列表前缀
    suggestions: list[str] = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # 去掉常见列表前缀(- * • 数字.)
        for prefix in ["- ", "* ", "• ", "· "]:
            if line.startswith(prefix):
                line = line[len(prefix):]
                break
        else:
            # 处理 "1. xxx" 形式
            if len(line) > 3 and line[0].isdigit() and line[1] in ".)、":
                line = line[2:].lstrip()

        if line:
            suggestions.append(line)

    # 兜底:解析不到任何行就用 errors
    return suggestions if suggestions else [f"- {e}" for e in errors]