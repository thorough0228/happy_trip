"""
单天路线优化(简化版)。

自适应算法:
- N ≤ BRUTE_FORCE_MAX_N (7):暴力枚举全排列,精确最优(N! ≤ 5040,~100ms 内)
- N > 7:2-opt 局部搜索 + 多起点(restarts 个随机起点 + 原始起点)
  保证 best ≤ original,O(N² × restarts),~10ms

暴力枚举只在 N 小时用(实际行程 2-5 个景点常见),避免 N! 爆炸。
2-opt 是经典 TSP 启发式,从随机起点出发迭代 2-edge swap,质量足够好。

酒店固定约束:
酒店作为每日起终点(出发从酒店,结束回酒店)。attractions 在酒店之间优化顺序。
多天连住同一家酒店时,各 day 独立计算。
"""
import random
from itertools import permutations

from app.models.schemas import Day
from app.planner.geo import haversine_km

# N > 7 时,N! 超过 5040,单次 2-opt 优势明显;N ≤ 7 时暴力枚举保证精确最优
BRUTE_FORCE_MAX_N = 7

# 2-opt 多起点次数。随机起点越多越接近最优,但计算量线性增加。
TWO_OPT_RESTARTS = 20

# 2-opt 单起点最大迭代轮数,防止极端情况下死循环(基本不会触发,但兜底)
TWO_OPT_MAX_ITERS = 50


def optimize_day(day: Day) -> tuple[Day, float]:
    """
    优化单天景点顺序。酒店作为固定起终点,attractions 在内部优化。

    Returns:
        (优化后的 Day, 原始总 km — 仅用于评测对照,不写入 plan)
    """
    atts = day.attractions
    if len(atts) < 2:
        # 即使 <2 也要传 hotel 给 _recompute_dists(若有)
        hotel_loc = day.hotel.location if day.hotel else None
        _recompute_dists(atts, hotel_loc)
        return day, 0.0

    locations = [a.location for a in atts]
    hotel_loc = day.hotel.location if day.hotel and day.hotel.location else None
    original_km = _path_km(locations, hotel_loc)

    if len(atts) <= BRUTE_FORCE_MAX_N:
        best_perm = _brute_force(atts, hotel_loc)
    else:
        best_perm = _two_opt_multi(atts, hotel_loc)

    _recompute_dists(best_perm, hotel_loc)

    # 构造新 Day(保持其他字段,attractions 替换为最优排列)
    # 注:best_perm 里的 Attraction 对象已经被原地修改了 dist_from_prev_km
    return Day(
        date=day.date,
        theme=day.theme,
        attractions=best_perm,
        meals=day.meals,
        hotel=day.hotel,
    ), original_km


def _brute_force(atts: list, hotel_loc: tuple[float, float] | None) -> list:
    """暴力枚举所有排列,选 haversine 总距最短的(N ≤ 7 时使用)。"""
    original_km = _path_km([a.location for a in atts], hotel_loc)
    best_perm = list(atts)
    best_km = original_km
    for perm in permutations(atts):
        km = _path_km([a.location for a in perm], hotel_loc)
        if km < best_km - 1e-9:
            best_km = km
            best_perm = list(perm)
    return best_perm


def _two_opt(atts: list, hotel_loc: tuple[float, float] | None, max_iters: int = TWO_OPT_MAX_ITERS) -> list:
    """
    单起点 2-opt 局部搜索。返回局部最优排列(可能不是全局最优)。

    算法:重复检查所有 (i, j) 对(i < j),如果翻转 atts[i+1..j+1] 能缩短总距就接受。
    直到一轮无改进或达到 max_iters。
    """
    current = list(atts)
    if len(current) < 4:
        # 2-opt 需要至少 4 个点才能做 2-edge swap
        return current

    best_km = _path_km([a.location for a in current], hotel_loc)
    improved = True
    iters = 0

    while improved and iters < max_iters:
        improved = False
        iters += 1
        for i in range(len(current) - 1):
            for j in range(i + 2, len(current)):
                # 2-opt:翻转 [i+1, j+1] 段
                candidate = current[: i + 1] + list(reversed(current[i + 1 : j + 1])) + current[j + 1 :]
                cand_km = _path_km([a.location for a in candidate], hotel_loc)
                if cand_km < best_km - 1e-9:
                    current = candidate
                    best_km = cand_km
                    improved = True

    return current


def _two_opt_multi(atts: list, hotel_loc: tuple[float, float] | None, restarts: int = TWO_OPT_RESTARTS) -> list:
    """
    多起点 2-opt。从原始顺序 + restarts 个随机顺序出发,选最优结果。

    理由:2-opt 是局部搜索,容易陷局部最优。多起点可跳出局部最优,
    逼近全局最优。restarts 越大越接近最优,O(N² × restarts) 越大。
    """
    # 起点 1:原始顺序(保证 best ≤ original)
    best = _two_opt(atts, hotel_loc)
    best_km = _path_km([a.location for a in best], hotel_loc)

    # 起点 2..N:随机顺序
    for _ in range(restarts):
        random_start = list(atts)
        random.shuffle(random_start)
        candidate = _two_opt(random_start, hotel_loc)
        cand_km = _path_km([a.location for a in candidate], hotel_loc)
        if cand_km < best_km - 1e-9:
            best = candidate
            best_km = cand_km

    return best


def _path_km(
    locations: list[tuple[float, float] | None],
    hotel_loc: tuple[float, float] | None = None,
) -> float:
    """累计相邻两点的 haversine 距离(km)。

    路径形态:hotel_loc -> locations[0] -> ... -> locations[N-1] -> hotel_loc
    hotel_loc 为 None 时,只算 locations 内部(向后兼容)。
    location 为 None 的点跳过(haversine 需要两个有效坐标)。
    """
    total = 0.0
    prev: tuple[float, float] | None = hotel_loc
    for loc in locations:
        if loc and prev:
            total += haversine_km(prev, loc)
            prev = loc
        elif loc:
            # 第一个有效点(没有 hotel_loc 时)
            prev = loc
    # 回酒店(如果有有效景点 + hotel_loc)
    if hotel_loc and prev and prev != hotel_loc:
        total += haversine_km(prev, hotel_loc)
    return total


def _recompute_dists(
    atts: list,
    hotel_loc: tuple[float, float] | None = None,
) -> None:
    """
    原地修改 atts[i].dist_from_prev_km。

    起点是 hotel_loc(不是 None),所以第一个景点的距离 = 酒店到该景点的距离。
    hotel_loc 缺失时,第一个景点保持 None(向后兼容)。
    """
    prev_loc: tuple[float, float] | None = hotel_loc
    for a in atts:
        if a.location and prev_loc:
            a.dist_from_prev_km = round(haversine_km(prev_loc, a.location), 2)
        else:
            a.dist_from_prev_km = None
        if a.location:
            prev_loc = a.location