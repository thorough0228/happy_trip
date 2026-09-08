"""
硬规则校验(简化版)。

LLM 通过 schema 校验 ≠ 输出合法。LLM 可能违反业务规则:
- 编了候选外的景点
- 同一景点在同一天重复出现
- 同一景区被拆成多个 POI(地理近邻 + 名称相关),如"玄武湖" + "玄武湖情侣园"

系统不校验酒店 / 餐厅 / 预算(产品层已去掉),只校验景点相关。
"""
from app.models.schemas import TripPlan
from app.planner.context import PlannerContext
from app.planner.geo import haversine_km


# 同一景区重复判定阈值
GEO_NEARBY_KM = 1.0        # 两景点 haversine < 1km 视为近邻
NAME_OVERLAP_MIN = 2       # 共同子串最短字符数(防"杭州"撞"杭州市")


def _name_overlap(a: str, b: str) -> str:
    """返回两个景点名最长共同子串(>= NAME_OVERLAP_MIN 字符)。无交集返回 ''。"""
    if not a or not b:
        return ""
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    best = ""
    n = len(shorter)
    for i in range(n):
        # j 是开区间右端,至少包含 NAME_OVERLAP_MIN 字符
        for j in range(i + NAME_OVERLAP_MIN, n + 1):
            sub = shorter[i:j]
            if sub in longer and len(sub) > len(best):
                best = sub
    return best


def validate_plan(plan: TripPlan, ctx: PlannerContext) -> list[str]:
    """
    对 LLM 输出的 TripPlan 做硬规则校验。

    Returns:
        错误列表。空列表 = 通过校验。
    """
    errors: list[str] = []
    attraction_names = {p.name for p in ctx.attractions}

    # 1. 景点候选约束
    for i, day in enumerate(plan.days):
        for a in day.attractions:
            if a.name not in attraction_names:
                errors.append(
                    f"day{i+1}:景点'{a.name}'不在候选列表中"
                )

    # 2. 多样性:同一天景点重复(同名 + 地理近邻 + 名称相关)
    for i, day in enumerate(plan.days):
        atts = day.attractions

        # 2a. 完全同名
        seen_names: set[str] = set()
        for a in atts:
            name = a.name.strip()
            if name in seen_names:
                errors.append(
                    f"day{i+1}:景点'{name}'重复出现"
                )
            else:
                seen_names.add(name)

        # 2b. 疑似同景区:地理近邻(haversine < GEO_NEARBY_KM)+ 名称有共同子串
        for j in range(len(atts)):
            aj = atts[j]
            if not aj.location:
                continue
            for k in range(j + 1, len(atts)):
                ak = atts[k]
                if not ak.location:
                    continue
                km = haversine_km(aj.location, ak.location)
                if km > GEO_NEARBY_KM:
                    continue
                overlap = _name_overlap(aj.name, ak.name)
                if overlap:
                    errors.append(
                        f"day{i+1}:景点'{aj.name}'与'{ak.name}'距离 {km:.2f}km,"
                        f" 共享名称片段'{overlap}',疑似同一景区,二选一"
                    )

    return errors