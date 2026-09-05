"""
Time Check Agent — 校验行程日期 vs 景点开放时间冲突。

职责分离:
- reviewer: 候选约束、预算、餐厅多样性、预算利用率
- time_check: 开放时间、闭馆日(只做时间相关)

CoT 推理:对每个 attraction 逐个检查"该 POI 在当前 Day.date 是否开放",
最后汇总冲突点。

失败时降级:LLM 调用失败 / 解析失败 → 直接返回 approved=True,不阻塞主流程。
"""
import json
from typing import Any

from pydantic import BaseModel, Field

from app.models.schemas import TripPlan
from app.planner.context import PlannerContext
from app.services.llm import chat


class TimeCheckResult(BaseModel):
    """Time Check 输出。conflicts 是人话冲突点列表。"""
    approved: bool
    conflicts: list[str] = Field(default_factory=list)
    reasoning: str = ""


TIME_CHECK_SYSTEM_PROMPT = """你是行程时间检查员。任务:逐个检查 plan 里每个景点的开放时间是否与行程日期冲突。

检查维度:
1. **闭馆日**:周一/周二等博物馆、美术馆常闭馆。ctx.attractions 中 POI.opening_hours 含"周一闭馆"等提示。
2. **营业时段**:景点只在特定时段开放(如 09:00-17:00),如果只有日期冲突、没有时段冲突,就报。
3. **节假日**:特殊日期(国庆、春节)部分景点闭馆或限流。

输入:
- plan.days 里每个 day 的 date 和 attractions
- ctx.attractions 含 POI 的 opening_hours 字段(可能为 null)

要求:
- 对每个 attraction 推理(为什么冲突 / 为什么通过),最终只输出 conflicts 列表
- 上下文已有 POI 的 name → opening_hours 映射,直接 name 匹配
- 如果无冲突,approved=true,conflicts=[]
- 输出 JSON 格式,不要解释

示例 conflicts:
- "day1 故宫:周一闭馆,与 2026-10-05(周一)冲突"
- "day3 国家博物馆:周一闭馆日,行程安排在周一"
- "day2 西湖:开放 09:00-17:00,行程可能在闭馆时段"
"""


def _format_plan_summary(plan: TripPlan) -> str:
    """把 plan 压缩成紧凑文本(每天一个段落)。"""
    lines = [f"目的地:{plan.destination}"]
    weekday_zh = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for i, day in enumerate(plan.days, 1):
        atts = ", ".join(a.name for a in day.attractions) or "(空)"
        # 解析星期几(纯展示,不强制)
        try:
            from datetime import date as _date

            weekday = weekday_zh[_date.fromisoformat(day.date).weekday()]
        except Exception:
            weekday = "?"
        lines.append(f"Day {i} ({day.date} {weekday}): {atts}")
    return "\n".join(lines)


def _format_poi_hours(plan: TripPlan, ctx: PlannerContext) -> str:
    """把 plan 用到的 POI 的 opening_hours 整理成 name → hours 的列表。"""
    used_names: set[str] = set()
    for day in plan.days:
        for a in day.attractions:
            used_names.add(a.name)

    lines: list[str] = []
    for poi in ctx.attractions:
        if poi.name in used_names and poi.opening_hours:
            lines.append(f"- {poi.name}:{poi.opening_hours}")
    if not lines:
        lines.append("(本次行程涉及的 POI 均无营业时间数据,跳过检查)")
    return "\n".join(lines)


async def time_check(plan: TripPlan, ctx: PlannerContext) -> TimeCheckResult:
    """
    调一次 LLM 做 CoT 推理,返回冲突列表。

    失败时(LLM 调用失败 / 解析失败)降级通过,不阻塞主流程。
    """
    user_prompt = (
        "【行程概要】\n"
        + _format_plan_summary(plan)
        + "\n\n【本次行程涉及 POI 的开放时间】\n"
        + _format_poi_hours(plan, ctx)
        + "\n\n请输出 JSON 格式检查结果(approved: bool, conflicts: [], reasoning: ''):"
    )
    try:
        raw = await chat(
            [
                {"role": "system", "content": TIME_CHECK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        # extract_json 在 services/llm.py 已做最长合法 JSON 提取,直接 loads 即可
        data: dict[str, Any] = json.loads(raw)
        return TimeCheckResult(
            approved=bool(data.get("approved", True)),
            conflicts=[str(c) for c in data.get("conflicts", [])],
            reasoning=str(data.get("reasoning", "")),
        )
    except Exception as e:
        print(f"[time_check] 调用/解析失败: {e},降级通过")
        return TimeCheckResult(approved=True, conflicts=[], reasoning=f"Time Check 失败: {e}")