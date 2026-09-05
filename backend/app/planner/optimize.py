"""
单天路线优化(FloatTrip 风格简化版)。

- 暴力枚举 attractions 全排列,haversine 计算总路程,选最短排列
- 重排 + 重算每个 attraction.dist_from_prev_km
- meals / hotel / period 时段 保持原位不动(happy_trip 没有 period 概念)
- 保证 best_km ≤ original_km(原始排列是候选项之一,不会越优化越差)

复杂度 N!,实际行程 2-5 个景点完全可接受。
"""
from itertools import permutations

from app.models.schemas import Day
from app.planner.geo import haversine_km


def optimize_day(day: Day) -> tuple[Day, float]:
    """
    优化单天景点顺序。

    Returns:
        (优化后的 Day, 原始总 km — 仅用于评测对照,不写入 plan)
    """
    atts = day.attractions
    if len(atts) < 2:
        return day, 0.0

    locations = [a.location for a in atts]
    original_km = _path_km(locations)

    # 暴力枚举所有排列,选最短(haversine 总距)
    best_perm = list(atts)
    best_km = original_km
    for perm in permutations(atts):
        km = _path_km([a.location for a in perm])
        if km < best_km - 1e-9:
            best_km = km
            best_perm = list(perm)

    # 重算每个景点的 dist_from_prev_km
    _recompute_dists(best_perm)

    # 构造新 Day(保持其他字段,attractions 替换为最优排列)
    # 注:best_perm 里的 Attraction 对象已经被原地修改了 dist_from_prev_km
    return Day(
        date=day.date,
        theme=day.theme,
        attractions=best_perm,
        meals=day.meals,
        hotel=day.hotel,
    ), original_km


def _path_km(locations: list[tuple[float, float] | None]) -> float:
    """累计相邻两点的 haversine 距离(km)。location 为 None 的点跳过。"""
    total = 0.0
    prev: tuple[float, float] | None = None
    for loc in locations:
        if loc and prev:
            total += haversine_km(prev, loc)
        if loc:
            prev = loc
    return total


def _recompute_dists(atts: list) -> None:
    """原地修改 atts[i].dist_from_prev_km = haversine(atts[i-1], atts[i])。第一个景点为 None。"""
    prev_loc: tuple[float, float] | None = None
    for a in atts:
        if a.location and prev_loc:
            a.dist_from_prev_km = round(haversine_km(prev_loc, a.location), 2)
        else:
            a.dist_from_prev_km = None
        if a.location:
            prev_loc = a.location