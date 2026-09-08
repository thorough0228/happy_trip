"""
单天路线优化。

完整路径模型(三段 + 三餐):
  hotel → breakfast → 上午景点 → lunch → 下午景点 → dinner → 晚上景点 → hotel

为什么不"晚餐后回酒店":实际场景里夜市、夫子庙、城市阳台、灯光秀等都是晚上活动,
晚上逛完才回酒店。evening 段是**可选项**,全部白天景点就让 evening 为空,
算法自动处理(无 evening 段就是下午结束直接回酒店)。

自适应算法:
- N ≤ BRUTE_FORCE_MAX_N (10):暴力枚举所有 (切分点 split1, split2) × 3 段子排列
- N > 10:罕见,LLM 受 prompt 约束一般不会输出这么多景点,直接保留 LLM 顺序

暴力枚举在 splits 维度受限,不会像单层 N! 那样爆炸。
"""
from dataclasses import dataclass
from itertools import permutations

from app.models.schemas import Day
from app.planner.geo import haversine_km

# N ≤ 10 走暴力;split 组合 = O(N²),子排列 ≤ O(N!),总开销合理
BRUTE_FORCE_MAX_N = 10


@dataclass
class _OptimResult:
    perm: list                  # 最佳 attractions 排列(整体)
    split1: int                 # morning 结束位置(午餐前),[0..N]
    split2: int                 # afternoon 结束位置(晚餐前),[split1..N]


def optimize_day(day: Day) -> tuple[Day, float]:
    """
    优化单天景点顺序。完整路径含 3 段 3 餐:
    hotel → breakfast → morning → lunch → afternoon → dinner → evening → hotel

    Returns:
        (优化后的 Day, 原始总 km — 仅用于评测对照,不写入 plan)
    """
    atts = day.attractions
    hotel_loc = day.hotel.location if day.hotel and day.hotel.location else None

    if len(atts) < 2:
        # 太短不分段,整段归 afternoon
        _fill_dists(atts, 0, 0, day.meals, hotel_loc)
        return day, _total_path_km(atts, 0, 0, day.meals, hotel_loc)

    # 优化路径
    result = _optimize(atts, day.meals, hotel_loc)

    # 写回 dist_from_prev_km
    _fill_dists(result.perm, result.split1, result.split2, day.meals, hotel_loc)

    # 原始总路径 km(供评测对照,假设全在 evening)
    original_km = _total_path_km(atts, len(atts), len(atts), day.meals, hotel_loc)

    return Day(
        date=day.date,
        theme=day.theme,
        attractions=result.perm,
        meals=day.meals,
        hotel=day.hotel,
        split1=result.split1,
        split2=result.split2,
    ), original_km


def _optimize(atts: list, meals: dict, hotel_loc: tuple | None) -> _OptimResult:
    """N ≤ 10 走暴力;N > 10 保留 LLM 顺序。"""
    if len(atts) > BRUTE_FORCE_MAX_N:
        return _OptimResult(perm=list(atts), split1=len(atts), split2=len(atts))
    return _brute_force_optimize(atts, meals, hotel_loc)


def _brute_force_optimize(atts: list, meals: dict, hotel_loc: tuple | None) -> _OptimResult:
    """枚举切分点 (split1, split2) × 3 段子排列,选总路径最短。"""
    N = len(atts)
    best_perm = list(atts)
    best_km = float("inf")
    best_split1 = N
    best_split2 = N

    # split1 ∈ [0, N]: morning 长度
    # split2 ∈ [split1, N]: afternoon 长度 = split2 - split1;evening = N - split2
    for split1 in range(0, N + 1):
        for split2 in range(split1, N + 1):
            morning = atts[:split1]
            afternoon = atts[split1:split2]
            evening = atts[split2:]

            # 暴力枚举 3 段子排列(空列表 → 单个 () 排列)
            m_perms = list(permutations(morning)) or [()]
            a_perms = list(permutations(afternoon)) or [()]
            e_perms = list(permutations(evening)) or [()]

            for m_perm in m_perms:
                for a_perm in a_perms:
                    for e_perm in e_perms:
                        perm = list(m_perm) + list(a_perm) + list(e_perm)
                        km = _total_path_km(perm, split1, split2, meals, hotel_loc)
                        if km < best_km - 1e-9:
                            best_km = km
                            best_perm = list(perm)
                            best_split1 = split1
                            best_split2 = split2

    return _OptimResult(perm=best_perm, split1=best_split1, split2=best_split2)


def _total_path_km(
    atts_perm: list,
    split1: int,
    split2: int,
    meals: dict,
    hotel_loc: tuple | None,
) -> float:
    """
    完整路径:hotel → breakfast → morning → lunch → afternoon → dinner → evening → hotel
    返回 haversine 总距离(km)。所有 None 节点自动跳过。
    """
    breakfast = meals.get("breakfast")
    lunch = meals.get("lunch")
    dinner = meals.get("dinner")

    total = 0.0
    prev_loc: tuple | None = hotel_loc

    if breakfast and breakfast.location:
        total += _add(prev_loc, breakfast.location)
        prev_loc = breakfast.location

    # 上午景点 (split1 个)
    for i in range(split1):
        a = atts_perm[i]
        if a.location:
            total += _add(prev_loc, a.location)
            prev_loc = a.location

    if lunch and lunch.location:
        total += _add(prev_loc, lunch.location)
        prev_loc = lunch.location

    # 下午景点 (split2 - split1 个)
    for i in range(split1, split2):
        a = atts_perm[i]
        if a.location:
            total += _add(prev_loc, a.location)
            prev_loc = a.location

    if dinner and dinner.location:
        total += _add(prev_loc, dinner.location)
        prev_loc = dinner.location

    # 晚上景点 (N - split2 个;可为 0)
    for i in range(split2, len(atts_perm)):
        a = atts_perm[i]
        if a.location:
            total += _add(prev_loc, a.location)
            prev_loc = a.location

    # 回酒店
    total += _add(prev_loc, hotel_loc)

    return total


def _add(prev: tuple | None, cur: tuple | None) -> float:
    """两点 haversine 距离,任一为 None 返回 0。"""
    if prev and cur:
        return haversine_km(prev, cur)
    return 0.0


def _fill_dists(
    atts: list,
    split1: int,
    split2: int,
    meals: dict,
    hotel_loc: tuple | None,
) -> None:
    """
    原地修改 atts[i].dist_from_prev_km = 路径中前一节点的距离。
    第一个景点 = 距 breakfast 距离;午餐/晚餐后 = 下午/晚上段距离。
    不算回酒店的距离(没"下一个 POI")。
    """
    breakfast = meals.get("breakfast")
    lunch = meals.get("lunch")
    dinner = meals.get("dinner")

    prev_loc: tuple | None = hotel_loc
    if breakfast and breakfast.location:
        prev_loc = breakfast.location

    # 上午段
    for i in range(split1):
        a = atts[i]
        if a.location and prev_loc:
            a.dist_from_prev_km = round(haversine_km(prev_loc, a.location), 2)
        else:
            a.dist_from_prev_km = None
        if a.location:
            prev_loc = a.location

    if lunch and lunch.location:
        prev_loc = lunch.location

    # 下午段
    for i in range(split1, split2):
        a = atts[i]
        if a.location and prev_loc:
            a.dist_from_prev_km = round(haversine_km(prev_loc, a.location), 2)
        else:
            a.dist_from_prev_km = None
        if a.location:
            prev_loc = a.location

    if dinner and dinner.location:
        prev_loc = dinner.location

    # 晚上段
    for i in range(split2, len(atts)):
        a = atts[i]
        if a.location and prev_loc:
            a.dist_from_prev_km = round(haversine_km(prev_loc, a.location), 2)
        else:
            a.dist_from_prev_km = None
        if a.location:
            prev_loc = a.location