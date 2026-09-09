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
        "1. 景点 必须从【可用候选列表】中选择,不得编造候选中不存在的名字。\n"
        "2. 选定后,name/address 必须原样复制候选,不得修改或编造。\n"
        "3. 候选列表外的名字,只能通过 notes 提及,不得放进 attractions 数组。\n"
        "4. 如果候选为空,可基于真实存在的知名地点生成,但要在 notes 里说明'非候选'。\n"
        "5. 【价格约束】价格必须使用候选 POI 的 cost 字段,不得自行估算或编造(免费则 0)。\n"
        "6. 【多样性约束】同一景点不得在同一天重复出现(改道/换角度不算)。\n"
        "7. 【Cluster 地理约束 — 非常重要】系统已经按地理聚类 + Day 分配把候选分成若干 Cluster 并指定每"
        "个 Cluster 所属日期(见 PlannerContext)。你必须严格遵守 Cluster → Day 分配:\n"
        "   - 同一 Cluster 内的景点**原则上全部安排在系统指定的那一天**\n"
        "   - 不要把同一 Cluster 的景点拆分到不同日期(会导致不必要的路线拆开)\n"
        "   - 不要无理由重新分配 Cluster 到其他 Day\n"
        "   - 不要跨 Cluster 混合:同一天优先选一个 Cluster 的景点,不要把两个相距很远的 Cluster 拼到一天\n"
        "   - 如果某天 Cluster 景点过多/时间不够,应**减少当天景点数**,而不是跨 Cluster 拉景点\n"
        "   - 如果某 Cluster 在你看来质量低(用户不感兴趣),可以**整 Cluster 跳过**,不要单独挑出 Cluster"
        "内的某些景点塞到其他天\n"
        "8. 【时间约束 — 非常重要】每个候选 POI 都有 visit_duration(预计游玩分钟数)。\n"
        "   你必须保证每天的总游玩时间 + 景点间交通时间 不超过每日可用时间(见 PlannerContext 的 '每日可用时间')。\n"
        "   - 计算公式:当天总时间 = Σ attractions[i].visit_duration + (cluster 数 - 1) × 15 分钟交通缓冲\n"
        "   - 如果某天总时间已超每日可用时间,**减少当天景点数**(剔除低优先级 POI),而不是强行加塞\n"
        "   - 不要为了塞更多景点而忽略时间约束\n"
        "   - 不要自行估算 visit_duration,必须使用系统提供的值(系统已用名称/类型启发式填好)\n"
        "   - 如果某 POI 没出现在候选列表(候选为空),可以自创,但必须在 notes 里说明"
    )

    system_prompt = (
        "你是一位专业的旅行规划助手。你的任务是基于 PlannerContext 中的真实事实,为用户编排景点游览计划。\n"
        "**本系统不规划餐饮,也不指定具体酒店** — 只规划去哪里玩,并在每天结尾给一个酒店区域建议。\n"
        "**重要:系统已为你完成地理聚类 + Day 分配** —— 同一 Cluster 的景点地理相邻,已被预先指定到某一天。"
        "你直接采纳该分配即可,不要拆散 Cluster、不要跨 Cluster 拼凑。\n\n"
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
        "          \"visit_duration\": 预计游玩分钟数(整数,必须等于候选列表中的值),\n"
        "          \"notes\": \"备注(字符串,可为 null)\"\n"
        "        }\n"
        "        // 可多个,后端会自动按地理最优排序\n"
        "      ],\n"
        "      \"hotel_area_hint\": \"酒店区域建议(字符串)\"\n"
        "      // 例:\"建议住在春熙路/太古里附近,出行方便\"\n"
        "    }\n"
        "    // 天数需等于用户要求的 travel_days\n"
        "  ],\n"
        "  \"notes\": [\"贴士1\", \"贴士2\", ...]\n"
        "}\n\n"
        "字段约束:\n"
        "- 所有数字必须 >= 0。\n"
        "- 日期格式必须为 YYYY-MM-DD。\n"
        "- 天数必须等于用户要求的 travel_days。\n"
        "- attractions 数量参考 LLM 自定(每天 2-6 个常见),后端会自动按 haversine 最短路径重排。\n"
        "- visit_duration 必须照抄候选 POI 列表中的值(候选列表每个 POI 都标注了游玩分钟数),不得自行估算或编造。\n"
        "- 每天总游玩时间(Σ visit_duration)+ 交通缓冲(景点间按 15min/段)应 ≤ 每日可用时间。\n"
        "- hotel_area_hint 是自然语言建议,不是候选池中的具体酒店;用户自己根据建议订房。\n"
        "- 请根据用户偏好(preferences)和负面约束(negative_constraints)调整景点推荐。\n"
        "- 输出必须合法 JSON,键名和嵌套结构与上述示例完全一致。"
    )

    user_prompt = (
        f"请为我规划一次旅行:\n"
        f"- 目的地:{req.destination}\n"
        f"- 出发日期:{start_date_str}\n"
        f"- 旅行天数:{req.travel_days} 天\n"
        f"- 人数:成人 {req.party.adults} 人,儿童 {req.party.children} 人,老人 {req.party.elders} 人(总 {req.party.total} 人),出行类型:{req.party.companion_type}\n" if req.party else "- 人数:未指定\n"
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


async def plan_trip(req: TripRequest, task_id: str | None = None, _ctx: PlannerContext | None = None) -> TripPlan:
    """
    规划行程的主入口:

    1. 编译 PlannerContext
    2. 主循环:LLM 生成 → 解析 + 业务校验,失败则把错误反馈给 LLM 重试
       最多 BUSINESS_MAX_ATTEMPTS 次(默认 2 次)
    3. 主循环结束仍未通过业务校验 → 调 reviewer 提出改进方案
    4. Planner 基于 reviewer 方案再生成一次(第 3 次,作为最终版)
    5. Pydantic schema 致命错统一抛 ValueError

    task_id: 可选,传入时上报进度给前端
    _ctx: 可选,评测时传入冻结的 PlannerContext 跳过 build_context 的外部 API 调用
    """
    async def report(stage: str, progress_pct: int):
        if task_id:
            await progress.update_progress(task_id, stage, progress_pct)

    await report("⏳ 准备中...", 0)
    ctx = _ctx if _ctx is not None else await build_context(req, reporter=report)
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
    _enrich_weather(plan, ctx)

    # 路径优化:对每个 day 暴力枚举景点全排列,重算 dist_from_prev_km
    # 在 _enrich_locations 之后调,保证 location 已填,优化算法才能算距离
    for day in plan.days:
        optimized_day, _ = optimize_day(day)
        # 写回优化结果(dist_from_prev_km 已在优化时填好)
        day.attractions = optimized_day.attractions

    return plan


def _enrich_weather(plan, ctx) -> None:
    """按日期把 ctx.weather 里的天气快照填到 plan.days（前端展示用）。"""
    weather_by_date = {w.day.isoformat(): w for w in ctx.weather}
    for day in plan.days:
        w = weather_by_date.get(day.date)
        if w and w.weather != "unknown":
            day.weather = w.weather
            day.temp_max = w.temp_max
            day.temp_min = w.temp_min


def _enrich_locations(plan, ctx) -> None:
    """
    把 ctx 里的景点坐标填到 plan 里,给前端地图用。

    LLM 输出 TripPlan 时不输出坐标(怕它编),后端基于 name 映射回填真实坐标。
    系统不再规划酒店和餐厅,只 enrich attractions。
    """
    name_to_loc = {p.name: p.location for p in ctx.attractions}

    for day in plan.days:
        for a in day.attractions:
            if a.location is None and a.name in name_to_loc:
                a.location = name_to_loc[a.name]