# 负责"组装 prompt + 调 LLM + 解析 JSON + 业务校验 + Time Check + reviewer 提案"。
from app.agents.reviewer import review_propose
from app.agents.time_check import time_check
from app.models.schemas import TripRequest, TripPlan
from app.services.llm import chat
from app.services import progress
from app.planner.context import PlannerContext, build_context
from app.planner.optimize import optimize_day
from app.planner.validation import validate_plan

# LLM 主循环最多跑 2 次(初始 1 次 + 业务校验失败后重试 1 次)。
# 2 次仍未通过业务校验 → 调 reviewer 提出改进方案,planner 第 3 次生成最终版。
BUSINESS_MAX_ATTEMPTS = 2


def build_prompt(req: TripRequest, ctx: PlannerContext) -> list[dict]:
    """
    构造发送给 LLM 的 messages 列表。
    包含 system 角色(角色、输出格式、约束)和 user 角色(用户需求)。
    """
    start_date_str = req.start_date.isoformat()

    hard_constraint = (
        "【硬约束 - 必须严格遵守】\n"
        "1. 景点/酒店/餐厅 必须从【可用候选列表】中选择,不得编造候选中不存在的名字。\n"
        "2. 选定后,name/address 必须原样复制候选,不得修改或编造。\n"
        "3. 候选列表外的名字,只能通过 notes 提及,不得放进 attractions/hotel/meals 数组。\n"
        "4. 如果某类候选为空,可基于真实存在的知名地点生成,但要在 notes 里说明'非候选'。\n"
        "5. 预算总额不得超过用户提供的总预算,各项明细要合理。\n"
        "6. 【价格约束 - L6 新增】价格必须使用候选 POI 的 cost 字段,不得自行估算或编造。\n"
        "   - 景点:复制候选 cost(免费则 0)\n"
        "   - 酒店:cost 已是每晚估价,hotel.cost 直接使用\n"
        "   - 餐饮:cost 已是规则估价(单人单餐)\n"
        "7. budget.total 必须等于 attractions+hotels+meals+transportation 明细之和,允许 ±5% 误差。\n"
        "8. 【多样性约束 - L8+L9 新增】同一餐厅不得在多餐重复出现(包括同一天的早午晚、不同天之间)。\n"
        "9. 【餐饮 grounding 加严 - L10.B 优化】午餐和晚餐必须 100% 命中候选列表中的餐厅。\n"
        "   早餐可以是候选中的餐厅,也可以是酒店早餐 fallback(在 notes 里说明)。\n"
        "   如果候选里没有符合用户 cuisine 偏好的餐厅,选最接近的当地特色餐厅,绝不允许编造餐厅名。\n"
        "   早午晚三餐之间、不同日期之间,餐厅应尽量多样化。\n"
        "9. 【少快餐约束】尽量减少选择肯德基、麦当劳、必胜客、星巴克等连锁快餐店。\n"
        "   优先选择本地特色餐厅、正餐品牌或非连锁餐饮。如果必须用快餐,每份行程最多 1 次。\n"
        "10. 【预算利用率 - 防 LLM 偷懒】budget.total 应至少达到用户预算的 80%,\n"
        "    不应远低于用户预期(LLM 倾向保守出低价)。\n"
        "    在景点门票、酒店档次、餐饮规格上合理分配,让总成本贴近用户预算,\n"
        "    但不必花满 — 用户预算允许有一定的节约空间。\n"
    )

    system_prompt = (
        "你是一位专业的旅行规划助手。你的任务是基于 PlannerContext 中的真实事实,为用户编排一份详细、合理的行程计划。\n\n"
        + hard_constraint + "\n"
        "【PlannerContext - 所有事实来源】\n"
        + ctx.summary() + "\n\n"
        "你必须严格按以下 JSON 格式输出结果,不要包含任何额外解释、不要用 markdown 代码块包裹,只输出纯 JSON。\n"
        "输出的 JSON 必须完全符合下面的结构:\n\n"
        "{\n"
        "  \"title\": \"行程标题(字符串)\",\n"
        "  \"destination\": \"目的地(字符串)\",\n"
        "  \"date_range\": \"YYYY-MM-DD ~ YYYY-MM-DD(字符串)\",\n"
        "  \"party\": {\n"
        "    \"adults\": 整数,\n"
        "    \"children\": 整数,\n"
        "    \"elders\": 整数,\n"
        "    \"total\": 整数(自动等于三者之和),\n"
        "    \"companion_type\": \"couple\" | \"family\" | \"friends\" | \"solo\"\n"
        "  },\n"
        "  \"days\": [\n"
        "    {\n"
        "      \"date\": \"YYYY-MM-DD\",\n"
        "      \"theme\": \"主题(字符串,可为 null)\",\n"
        "      \"attractions\": [\n"
        "        {\n"
        "          \"name\": \"景点名\",\n"
        "          \"address\": \"地址\",\n"
        "          \"cost\": 花费(数字,>=0),\n"
        "          \"notes\": \"备注(字符串,可为 null)\"\n"
        "        }\n"
        "        // 可多个\n"
        "      ],\n"
        "      \"meals\": {\n"
        "        \"breakfast\": {\"name\": \"餐厅名\", \"address\": \"地址\", \"cost\": 数字},\n"
        "        \"lunch\": {\"name\": \"...\", \"address\": \"...\", \"cost\": 数字},\n"
        "        \"dinner\": {\"name\": \"...\", \"address\": \"...\", \"cost\": 数字}\n"
        "      },\n"
        "      \"hotel\": {\n"
        "        \"name\": \"酒店名\",\n"
        "        \"address\": \"地址\",\n"
        "        \"cost\": 每晚费用(数字),\n"
        "        \"nights\": 入住晚数(整数)\n"
        "      }  // 若当天无住宿,可为 null\n"
        "    }\n"
        "    // 天数需等于用户要求的 travel_days\n"
        "  ],\n"
        "  \"budget\": {\n"
        "    \"total_attractions\": 数字,\n"
        "    \"total_hotels\": 数字,\n"
        "    \"total_meals\": 数字,\n"
        "    \"total_transportation\": 数字,\n"
        "    \"total\": 数字(等于上述四项之和)\n"
        "  },\n"
        "  \"notes\": [\"贴士1\", \"贴士2\", ...]\n"
        "}\n\n"
        "字段约束:\n"
        "- 所有数字必须 >= 0。\n"
        "- 日期格式必须为 YYYY-MM-DD。\n"
        "- 天数必须等于用户要求的 travel_days。\n"
        "- 预算明细应合理分配,且总和不应超过用户总预算(但不必完全相等,需在合理范围内)。\n"
        "- 住宿类型需匹配用户选择的 accommodation(酒店/民宿/青旅),交通方式需匹配 transportation。\n"
        "- 请根据用户偏好(preferences)和负面约束(negative_constraints)调整景点、餐饮推荐。\n"
        "- 输出必须合法 JSON,键名和嵌套结构与上述示例完全一致。"
    )

    user_prompt = (
        f"请为我规划一次旅行:\n"
        f"- 目的地:{req.destination}\n"
        f"- 出发日期:{start_date_str}\n"
        f"- 旅行天数:{req.travel_days} 天\n"
        f"- 人数:成人 {req.party.adults} 人,儿童 {req.party.children} 人,老人 {req.party.elders} 人(总 {req.party.total} 人),出行类型:{req.party.companion_type}\n"
        f"- 总预算:{req.budget_constraint.amount} 元\n"
        f"- 交通方式:{req.transportation}\n"
        f"- 住宿类型:{req.accommodation}\n"
        f"- 偏好:{', '.join(req.preferences) if req.preferences else '无特别偏好'}\n"
        f"- 负面约束:{', '.join(req.negative_constraints) if req.negative_constraints else '无'}\n"
        "\n请严格按照上述 JSON 格式输出完整行程计划。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_retry_messages(
    req: TripRequest,
    ctx: PlannerContext,
    feedback: list[str],
    heading: str = "上一次输出未通过校验,以下问题必须修复:",
) -> list[dict]:
    """
    把反馈(错误列表 / reviewer 建议)追加到 messages,让 LLM 重生成。

    heading 控制措辞 — 业务校验时用"必须修复",reviewer 提案后用"基于此重新生成"。
    """
    base = build_prompt(req, ctx)
    base.append({
        "role": "user",
        "content": (
            heading + "\n"
            + "\n".join(f"- {item}" for item in feedback)
            + "\n\n请重新输出完整 JSON,严格遵守硬约束。"
        ),
    })
    return base


async def plan_trip(req: TripRequest, task_id: str | None = None) -> TripPlan:
    """
    规划行程的主入口:

    1. 编译 PlannerContext
    2. 主循环:LLM 生成 → 解析 + 业务校验,失败则把错误反馈给 LLM 重试
       最多 BUSINESS_MAX_ATTEMPTS 次(默认 2 次)
    3. 主循环结束仍未通过业务校验 → 调 reviewer 提出改进方案
    4. Planner 基于 reviewer 方案再生成一次(第 3 次,作为最终版)
    5. Pydantic schema 致命错统一抛 ValueError

    task_id: 可选,传入时上报进度给前端
    """
    async def report(stage: str, progress_pct: int):
        if task_id:
            await progress.update_progress(task_id, stage, progress_pct)

    await report("⏳ 准备中...", 0)
    ctx = await build_context(req, reporter=report)
    messages = build_prompt(req, ctx)

    # ---- 主循环:LLM 生成 + 业务校验 + 反思重试 ----
    plan: TripPlan | None = None
    last_errors: list[str] = []
    last_pydantic: str = ""
    final_errors: list[str] = []

    for attempt in range(BUSINESS_MAX_ATTEMPTS):
        await report(f"🤖 AI 生成行程(第 {attempt + 1}/{BUSINESS_MAX_ATTEMPTS} 次)...", 60 + attempt * 12)
        raw_text = await chat(messages, temperature=0.7)

        await report("✅ 解析行程数据...", 65 + attempt * 12)
        try:
            plan = TripPlan.model_validate_json(raw_text)
        except Exception as e:
            last_pydantic = str(e)
            last_errors = [f"JSON 解析失败: {e}"]
            print(f"[planner] 第{attempt+1}次 Pydantic 解析失败: {e}")
            messages = _build_retry_messages(req, ctx, last_errors)
            plan = None
            continue

        errors = validate_plan(plan, ctx)
        if not errors:
            # 业务校验通过,再跑 Time Check 验证开放时间(共用重试 budget)
            await report("🕒 检查景点开放时间...", 75)
            tc_result = await time_check(plan, ctx)
            if not tc_result.approved:
                # 把 Time Check 冲突折进 errors,共用主循环重试 budget
                errors = [f"开放时间冲突:{c}" for c in tc_result.conflicts]
                last_errors = errors
                print(f"[planner] 第{attempt+1}次 Time Check 失败: {len(tc_result.conflicts)} 个冲突")
        if not errors:
            # 成功
            break
        if not last_errors or last_errors == errors:
            last_errors = errors
        print(f"[planner] 第{attempt+1}次校验失败: {len(errors)} 个错误")
        messages = _build_retry_messages(req, ctx, errors)

    if plan is None:
        # Pydantic 全部失败,严重异常
        raise ValueError(
            f"Pydantic schema 解析失败(已重试 {BUSINESS_MAX_ATTEMPTS} 次): {last_pydantic}"
        )

    final_errors = validate_plan(plan, ctx)
    if final_errors:
        # ---- Reviewer 提出改进方案,Planner 基于方案再生成 ----
        await report("📋 Reviewer 提出改进方案...", 88)
        suggestions = await review_propose(req, ctx, last_plan=plan, errors=final_errors)
        print(f"[planner] Reviewer 提出 {len(suggestions)} 条建议")

        await report("🤖 AI 基于 Reviewer 方案生成最终版...", 92)
        messages = _build_retry_messages(
            req,
            ctx,
            suggestions,
            heading="Reviewer 已分析上一次的问题,提出以下改进方案,请基于此重新生成:",
        )
        raw_text = await chat(messages, temperature=0.7)
        try:
            plan = TripPlan.model_validate_json(raw_text)
            print("[planner] 基于 Reviewer 方案成功生成最终版")
        except Exception as e:
            # Reviewer 后 Pydantic 失败 — 降级返回原 plan + notes 警告
            print(f"[planner] Reviewer 后 Pydantic 解析失败: {e},返回原 plan + 警告")
            plan.notes = list(plan.notes) + [
                f"业务校验有 {len(final_errors)} 项未通过,Reviewer 方案生成失败,以下项目可能不准确:",
                *[f"- {e}" for e in final_errors[:5]],
            ]

    await report("🎉 完成", 100)
    _enrich_locations(plan, ctx)

    # 路径优化:对每个 day 暴力枚举景点全排列,重算 dist_from_prev_km
    # 在 _enrich_locations 之后调,保证 location 已填,优化算法才能算距离
    total_original_km = 0.0
    for day in plan.days:
        optimized_day, original_km = optimize_day(day)
        # 原地写回(optimize_day 内部已经修改了 dist_from_prev_km)
        day.attractions = optimized_day.attractions
        total_original_km += original_km

    return plan


def _enrich_locations(plan, ctx) -> None:
    """
    把 ctx 里的 POI 坐标填到 plan 里,给前端地图用。

    LLM 输出 TripPlan 时不输出坐标(怕它编),后端基于 name 映射回填真实坐标。
    """
    name_to_loc = {}
    for p in ctx.attractions:
        name_to_loc[p.name] = p.location
    for p in ctx.hotels:
        name_to_loc[p.name] = p.location
    for p in ctx.food:
        name_to_loc[p.name] = p.location

    for day in plan.days:
        for a in day.attractions:
            if a.location is None and a.name in name_to_loc:
                a.location = name_to_loc[a.name]
        if day.hotel and day.hotel.location is None:
            day.hotel.location = name_to_loc.get(day.hotel.name)
        for meal in day.meals.values():
            if meal and meal.location is None:
                meal.location = name_to_loc.get(meal.name)