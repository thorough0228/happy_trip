"""
硬规则打分手(G1–G8)。

每条 grader 接收 fixture + plan，返回 (passed: bool, detail: str)。
设计原则:
- 纯 Python 确定性,零 LLM 成本
- 复用生产 helpers (haversine_km / validate_plan 已有逻辑)
- 一条 grader = 一个明确的业务不变量
"""
from __future__ import annotations

from typing import Tuple

from app.models.schemas import TripPlan, TripRequest
from app.planner.context import PlannerContext
from app.planner.geo import haversine_km

GraderResult = Tuple[bool, str]


# ---- G1:候选池封闭(无 LLM 幻觉)----
def g1_in_candidate_pool(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    names = {p.name for p in ctx.attractions}
    for i, day in enumerate(plan.days, 1):
        for a in day.attractions:
            if a.name not in names:
                return False, f"day{i}:'{a.name}' 不在 ctx 候选池(幻觉)"
    return True, f"{sum(len(d.attractions) for d in plan.days)} 个景点全部来自候选"


# ---- G2:visit_duration 与候选一致(防 LLM 自编时长)----
def g2_visit_duration_consistent(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    name_to_dur = {p.name: getattr(p, "visit_duration", None) for p in ctx.attractions}
    for i, day in enumerate(plan.days, 1):
        for a in day.attractions:
            ref = name_to_dur.get(a.name)
            if ref and a.visit_duration != ref:
                return False, f"day{i}:'{a.name}' duration={a.visit_duration} vs 候选 {ref}"
    return True, "全部时长一致"


# ---- G3:每日时长合理(包含交通缓冲 ≤ 每日预算)----
def g3_daily_time_budget(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    budget = ctx.daily_available_minutes
    for i, day in enumerate(plan.days, 1):
        dur = sum(a.visit_duration or 0 for a in day.attractions)
        travel = max(0, len(day.attractions) - 1) * 15
        total = dur + travel
        if total > budget:
            return False, f"day{i}:游玩{dur}+交通{travel}={total}min 超预算 {budget}min"
    return True, "每日时长均在预算内"


# ---- G4:结构合法(天/景点数)----
def g4_structure_valid(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    if len(plan.days) != req.travel_days:
        return False, f"days={len(plan.days)} vs travel_days={req.travel_days}"
    if not all(len(d.attractions) >= 1 for d in plan.days):
        empty = [i+1 for i, d in enumerate(plan.days) if len(d.attractions) == 0]
        return False, f"day {empty} 没有景点"
    return True, f"{len(plan.days)} 天,每天均有 ≥1 景点"


# ---- G5:多样性(同一天无重复/近邻+名称冲突)----
def g5_diversity(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    for i, day in enumerate(plan.days, 1):
        atts = day.attractions
        seen = set()
        for a in atts:
            if a.name in seen:
                return False, f"day{i}:'{a.name}' 重复"
            seen.add(a.name)
        # 近邻 + 名称重叠
        for j in range(len(atts)):
            for k in range(j+1, len(atts)):
                aj, ak = atts[j], atts[k]
                if not (aj.location and ak.location):
                    continue
                km = haversine_km(aj.location, ak.location)
                if km > 1.0:
                    continue
                # 简单 name overlap
                if any(t in aj.name for t in ak.name.split()) or any(t in ak.name for t in aj.name.split()):
                    if len(set(ak.name.split()) & set(aj.name.split())) > 0:
                        return False, f"day{i}:'{aj.name}'与'{ak.name}' 距离 {km:.2f}km,疑似同景区"
    return True, "无重复/无近邻冲突"


# ---- G6:路径优化(后端真的跑了优化)----
def g6_route_optimized(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    total = sum(a.dist_from_prev_km or 0 for day in plan.days for a in day.attractions)
    if total <= 0:
        return False, "无任何 dist_from_prev_km > 0(后端未跑优化)"
    return True, f"累计路径 {total:.1f}km"


# ---- G7:天气数据落地(高德返回了可用天气)----
def g7_weather_loaded(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    if not ctx.weather:
        return False, "ctx.weather 为空(高德天气 API 未返回)"
    days_with_weather = sum(1 for d in plan.days if d.weather and d.weather != "unknown")
    if days_with_weather == 0:
        return False, "plan.days 没有 weather 字段(后端 _enrich_weather 未生效)"
    return True, f"{days_with_weather}/{len(plan.days)} 天有天气"


# ---- G8:LLM 调用成功(产出有效 plan)----
def g8_llm_responded(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> GraderResult:
    if not plan.title:
        return False, "plan.title 为空"
    if not plan.days:
        return False, "plan.days 为空"
    return True, f"title='{plan.title[:30]}', days={len(plan.days)}"


ALL_GRADERS = [
    ("g1_in_candidate_pool", g1_in_candidate_pool),
    ("g2_visit_duration_consistent", g2_visit_duration_consistent),
    ("g3_daily_time_budget", g3_daily_time_budget),
    ("g4_structure_valid", g4_structure_valid),
    ("g5_diversity", g5_diversity),
    ("g6_route_optimized", g6_route_optimized),
    ("g7_weather_loaded", g7_weather_loaded),
    ("g8_llm_responded", g8_llm_responded),
]


def grade_all(plan: TripPlan, ctx: PlannerContext, req: TripRequest) -> dict[str, GraderResult]:
    """跑全部硬规则,返回 {grader_id: (passed, detail)}。"""
    return {name: fn(plan, ctx, req) for name, fn in ALL_GRADERS}