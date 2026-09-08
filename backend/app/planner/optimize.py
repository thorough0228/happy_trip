"""
单天路线优化(简化版)。

设计:不再管餐饮/酒店,只优化景点顺序。
完整路径 = A1 → A2 → ... → → AN,无起终点约束。
总路径 = Σ haversine(A_i, A_{i+1})

自适应算法:
- N ≤ BRUTE_FORCE_MAX_N (7):暴力枚举全排列,精确最优(N! ≤ 5040)
- N > 7:2-opt 多起点(1 原始 + N_RESTARTS 随机起点),O(N² × restarts)

dist_from_prev_km 重算:
- 第一个景点 = None(无"前一个节点")
- 第 2..N 个 = haversine(前一景点, 当前景点)
"""
import random
from itertools import permutations

from app.models.schemas import Day
from app.planner.geo import haversine_km

# N > 7 时,N! 超过 5040,单次 2-opt 优势明显;N ≤ 7 时暴力枚举保证精确最优
BRUTE_FORCE_MAX_N = 7

# 2-opt 多起点次数。随机起点越多越接近最优,但计算量线性增加。
N_RESTARTS = 20

# 2-opt 单起点最大迭代轮数,防止极端情况下死循环(基本不会触发,但兜底)
MAX_ITERS = 50


def optimize_day(day: Day) -> tuple[Day, float]:
    """
    优化单天景点顺序。简化版:无 hotel 起终点,无 meal 节点。

    Returns:
        (优化后的 Day, 原始总 km — 仅用于评测对照,不写入 plan)
    """
    atts = day.attractions
    if len(atts) < 2:
        _fill_dists(atts)
        return day, _path_km(atts)

    if len(atts) <= BRUTE_FORCE_MAX_N:
        best_perm = _brute_force(atts)
    else:
        best_perm = _two_opt_multi(atts)

    _fill_dists(best_perm)
    original_km = _path_km(atts)

    return Day(
        date=day.date,
        theme=day.theme,
        attractions=best_perm,
        hotel_area_hint=day.hotel_area_hint,
    ), original_km


def _brute_force(atts: list) -> list:
    """暴力枚举所有排列,选 haversine 总距最短(N ≤ 7 时使用)。"""
    original_km = _path_km(atts)
    best_perm = list(atts)
    best_km = original_km
    for perm in permutations(atts):
        km = _path_km(list(perm))
        if km < best_km - 1e-9:
            best_km = km
            best_perm = list(perm)
    return best_perm


def _two_opt(atts: list, max_iters: int = MAX_ITERS) -> list:
    """单起点 2-opt 局部搜索。返回局部最优排列(可能不是全局最优)。"""
    current = list(atts)
    if len(current) < 4:
        return current

    best_km = _path_km(current)
    improved = True
    iters = 0

    while improved and iters < max_iters:
        improved = False
        iters += 1
        for i in range(len(current) - 1):
            for j in range(i + 2, len(current)):
                # 2-opt:翻转 [i+1, j+1] 段
                candidate = current[: i + 1] + list(reversed(current[i + 1 : j + 1])) + current[j + 1 :]
                cand_km = _path_km(candidate)
                if cand_km < best_km - 1e-9:
                    current = candidate
                    best_km = cand_km
                    improved = True

    return current


def _two_opt_multi(atts: list, restarts: int = N_RESTARTS) -> list:
    """多起点 2-opt。从原始顺序 + restarts 个随机顺序出发,选最优。"""
    best = _two_opt(atts)
    best_km = _path_km(best)

    for _ in range(restarts):
        random_start = list(atts)
        random.shuffle(random_start)
        candidate = _two_opt(random_start)
        cand_km = _path_km(candidate)
        if cand_km < best_km - 1e-9:
            best = candidate
            best_km = cand_km

    return best


def _path_km(atts: list) -> float:
    """累计相邻两点的 haversine 距离(km)。第一个景点为 None。"""
    total = 0.0
    prev = None
    for a in atts:
        if a.location and prev:
            total += haversine_km(prev, a.location)
        if a.location:
            prev = a.location
    return total


def _fill_dists(atts: list) -> None:
    """原地修改 atts[i].dist_from_prev_km = haversine(atts[i-1], atts[i])。第一个景点为 None。"""
    prev_loc = None
    for a in atts:
        if a.location and prev_loc:
            a.dist_from_prev_km = round(haversine_km(prev_loc, a.location), 2)
        else:
            a.dist_from_prev_km = None
        if a.location:
            prev_loc = a.location