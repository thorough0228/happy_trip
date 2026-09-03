# 负责"组装 prompt + 调 LLM + 解析 JSON + 硬规则校验 + 重试"。
import json
from app.models.schemas import TripRequest, TripPlan
from app.services.llm import chat
from app.services.progress import update_progress
from app.planner.context import PlannerContext, build_context
from app.planner.validation import validate_plan

MAX_RETRIES = 2  # 校验失败最多重试 2 次


def build_prompt(req: TripRequest, ctx: PlannerContext) -> list[dict]:
    """
    构造发送给 LLM 的 messages 列表。
    包含 system 角色（角色、输出格式、约束）和 user 角色（用户需求）。
    """
    # 将日期转换为字符串（Pydantic date 会自动序列化为 ISO 格式，但用于提示词我们显式格式化）
    start_date_str = req.start_date.isoformat()

    # 硬约束覆盖所有事实类型
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
    )

    system_prompt = (
        "你是一位专业的旅行规划助手。你的任务是基于 PlannerContext 中的真实事实,为用户编排一份详细、合理的行程计划。\n\n"
        + hard_constraint + "\n"
        "【PlannerContext - 所有事实来源】\n"
        + ctx.summary() + "\n\n"
        "你必须严格按以下 JSON 格式输出结果，不要包含任何额外解释、不要用 markdown 代码块包裹，只输出纯 JSON。\n"
        "输出的 JSON 必须完全符合下面的结构：\n\n"
        "{\n"
        "  \"title\": \"行程标题（字符串）\",\n"
        "  \"destination\": \"目的地（字符串）\",\n"
        "  \"date_range\": \"YYYY-MM-DD ~ YYYY-MM-DD（字符串）\",\n"
        "  \"party\": {\n"
        "    \"adults\": 整数,\n"
        "    \"children\": 整数,\n"
        "    \"elders\": 整数,\n"
        "    \"total\": 整数（自动等于三者之和）,\n"
        "    \"companion_type\": \"couple\" | \"family\" | \"friends\" | \"solo\"\n"
        "  },\n"
        "  \"days\": [\n"
        "    {\n"
        "      \"date\": \"YYYY-MM-DD\",\n"
        "      \"theme\": \"主题（字符串，可为 null）\",\n"
        "      \"attractions\": [\n"
        "        {\n"
        "          \"name\": \"景点名\",\n"
        "          \"address\": \"地址\",\n"
        "          \"cost\": 花费（数字，>=0）,\n"
        "          \"notes\": \"备注（字符串，可为 null）\"\n"
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
        "        \"cost\": 每晚费用（数字）,\n"
        "        \"nights\": 入住晚数（整数）\n"
        "      }  // 若当天无住宿，可为 null\n"
        "    }\n"
        "    // 天数需等于用户要求的 travel_days\n"
        "  ],\n"
        "  \"budget\": {\n"
        "    \"total_attractions\": 数字,\n"
        "    \"total_hotels\": 数字,\n"
        "    \"total_meals\": 数字,\n"
        "    \"total_transportation\": 数字,\n"
        "    \"total\": 数字（等于上述四项之和）\n"
        "  },\n"
        "  \"notes\": [\"贴士1\", \"贴士2\", ...]\n"
        "}\n\n"
        "字段约束：\n"
        "- 所有数字必须 >= 0。\n"
        "- 日期格式必须为 YYYY-MM-DD。\n"
        "- 天数必须等于用户要求的 travel_days。\n"
        "- 预算明细应合理分配，且总和不应超过用户总预算（但不必完全相等，需在合理范围内）。\n"
        "- 住宿类型需匹配用户选择的 accommodation（酒店/民宿/青旅），交通方式需匹配 transportation。\n"
        "- 请根据用户偏好（preferences）和负面约束（negative_constraints）调整景点、餐饮推荐。\n"
        "- 输出必须合法 JSON，键名和嵌套结构与上述示例完全一致。"
    )

    # 构造 User prompt，包含所有用户输入信息
    user_prompt = (
        f"请为我规划一次旅行：\n"
        f"- 目的地：{req.destination}\n"
        f"- 出发日期：{start_date_str}\n"
        f"- 旅行天数：{req.travel_days} 天\n"
        f"- 人数：成人 {req.party.adults} 人，儿童 {req.party.children} 人，老人 {req.party.elders} 人（总 {req.party.total} 人），出行类型：{req.party.companion_type}\n"
        f"- 总预算：{req.budget_constraint.amount} 元，预算档位：{req.budget_constraint.level}\n"
        f"- 交通方式：{req.transportation}\n"
        f"- 住宿类型：{req.accommodation}\n"
        f"- 偏好：{', '.join(req.preferences) if req.preferences else '无特别偏好'}\n"
        f"- 负面约束：{', '.join(req.negative_constraints) if req.negative_constraints else '无'}\n"
        "\n请严格按照上述 JSON 格式输出完整行程计划。"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_retry_messages(req: TripRequest, ctx: PlannerContext, errors: list[str]) -> list[dict]:
    """
    校验失败时,把错误反馈追加到 messages,让 LLM 重生成。

    关键:把 errors 作为新的 user 消息追加,而不是修改 system prompt。
    LLM 看到"上次输出有哪些错",基于这些错修正。
    """
    base = build_prompt(req, ctx)
    base.append({
        "role": "user",
        "content": (
            "上一次输出未通过校验,以下问题必须修复:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\n请重新输出完整 JSON,严格遵守硬约束。"
        ),
    })
    return base


def plan_trip(req: TripRequest, task_id: str | None = None) -> TripPlan:
    """
    规划行程的主入口:
    1. 编译 PlannerContext
    2. 调 LLM → 解析 JSON → 硬规则校验
    3. 校验失败:带错误反馈重试,最多 MAX_RETRIES 次
    4. 全部失败:返回最后一次结果(带 warning)

    task_id: 可选,传入时上报进度给前端
    """
    def report(stage: str, progress: int):
        if task_id:
            update_progress(task_id, stage, progress)

    report("搜索景点/酒店/餐厅候选 + 获取天气...", 10)
    ctx = build_context(req)
    messages = build_prompt(req, ctx)

    last_plan: TripPlan | None = None
    last_errors: list[str] = []

    for attempt in range(MAX_RETRIES + 1):
        stage = f"LLM 生成行程(第 {attempt + 1} 次)..."
        report(stage, 30 + attempt * 20)
        raw_text = chat(messages, temperature=0.7)

        report("解析 + 校验...", 35 + attempt * 20)
        try:
            plan = TripPlan.model_validate_json(raw_text)
            errors = validate_plan(plan, ctx)

            if not errors:
                report("完成", 100)
                _enrich_locations(plan, ctx)
                return plan

            last_plan = plan
            last_errors = errors
            print(f"[planner] 第{attempt+1}次校验失败: {len(errors)} 个错误")
        except Exception as e:
            last_errors = [f"JSON 解析失败: {e}"]
            print(f"[planner] 第{attempt+1}次 JSON 解析失败: {e}")

        if attempt < MAX_RETRIES:
            messages = _build_retry_messages(req, ctx, last_errors)

    report("完成(含未修复的警告)", 100)
    _enrich_locations(last_plan, ctx)
    # 兜底:返回最后一次成功解析的 plan
    return last_plan


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

