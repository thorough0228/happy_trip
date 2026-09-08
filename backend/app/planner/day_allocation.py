"""
Cluster → Day 分配启发式。

目标:在 N=travel_days 前提下,把若干 cluster 分配到 N 个 day,使得:
1. 每个 cluster 完整分配到某一个 day(尽量不拆,除非很大)
2. 同一天不跨越地理上相距很远的 cluster
3. 各天 POI 数基本平衡(避免 1 天 8 个/2 天 0 个)

算法:贪心 + 距离惩罚
- 按 cluster 中心距离"上一个 cluster"最近优先合并到同一天
- 距离过远(> SAME_DAY_MAX_KM)即使 POI 多也不合并
- 当 cluster 数量 > days,最大的 cluster 拆分到多天
- 当 cluster 数量 < days,最小的 cluster 单独成一天(地理连续性 > 平衡)

输入/输出都是 list,索引即 day 编号 0..N-1。
"""
from typing import Iterable

from app.models.poi import POI
from app.planner.geo import haversine_km


# 启发式参数(可配置)
SAME_DAY_MAX_KM = 3.0     # 同一天允许的"两个 cluster 中心"最大距离,超过则必须分天
MERGE_MIN_POIS = 1        # 至少 N 个 POI 才考虑合并,防止把单点 cluster 拉到一起
TARGET_POIS_PER_DAY = 5   # 每"天容量"目标值,决定拆分阈值


def cluster_centers(clusters: list[list[POI]]) -> list[tuple[float, float] | None]:
    """计算每个 cluster 的中心点(POI 经纬度均值)。空 cluster 返回 None。"""
    centers: list[tuple[float, float] | None] = []
    for cluster in clusters:
        locs = [p.location for p in cluster if p.location is not None]
        if not locs:
            centers.append(None)
            continue
        lng = sum(l[0] for l in locs) / len(locs)
        lat = sum(l[1] for l in locs) / len(locs)
        centers.append((lng, lat))
    return centers


def allocate_clusters_to_days(
    clusters: list[list[POI]],
    travel_days: int,
) -> list[list[list[POI]]]:
    """
    把 clusters 分配到 N 天。

    Args:
        clusters: 聚类结果 list[list[POI]]
        travel_days: 用户游玩天数

    Returns:
        list[length=travel_days] of list[list[POI]] —
            days[i] 是第 i 天的 POI 列表(可能为空,通常不为空)
    """
    n_clusters = len(clusters)
    if n_clusters == 0 or travel_days <= 0:
        return [[] for _ in range(max(travel_days, 1))]

    if n_clusters == 1:
        # 1 个 cluster → 1 天(可能超容量,后面路径优化器可铺)
        days = [[clusters[0][0]]]  # 先放一个
        for p in clusters[0][1:]:
            days[0].append(p)
        # 剩余 day 留空
        for _ in range(travel_days - 1):
            days.append([])
        return days

    # 多 cluster,贪心按"与上一个 cluster 中心距离"升序串到 day 上
    centers = cluster_centers(clusters)
    order = sorted(
        range(n_clusters),
        key=lambda i: (centers[i] is None, centers[i] or (0, 0)),
    )
    # 按"地理上相近"串成 chain:从一个 cluster 出发,贪心找最近的下一个
    chain: list[int] = [order[0]]
    remaining = set(order[1:])
    last_center = centers[order[0]]
    while remaining:
        candidates = [i for i in remaining if centers[i] is not None] or list(remaining)
        # 找距 last_center 最近的 cluster
        nxt = min(
            candidates,
            key=lambda i: (
                haversine_km(last_center, centers[i])
                if last_center and centers[i]
                else 0
            ),
        )
        chain.append(nxt)
        remaining.remove(nxt)
        if centers[nxt] is not None:
            last_center = centers[nxt]

    # chain 是按地理相邻的 cluster 序列,切成 N 段(如果 N < len(chain))
    if travel_days >= len(chain):
        # days 多了,每个 cluster 各占一天,剩余天留空
        days = [[clusters[i][j] for j in range(len(clusters[i]))] for i in chain]
        for _ in range(travel_days - len(chain)):
            days.append([])
        return days

    # travel_days < len(chain):需要合并多个 cluster 到同一天
    # 贪心:从 chain 头开始,逐 cluster 累加,到容量或最后一天就开新 day
    days: list[list[POI]] = []
    cur_day: list[POI] = []
    cur_count = 0
    cur_center = None

    # 已分配的天数(用于"剩下 cluster 全收尾到最后一天"逻辑)
    # 最后一天不触发容量上限,避免丢 POI
    for idx_pos, idx in enumerate(chain):
        c_pois = clusters[idx]
        c_center = centers[idx]
        c_count = len(c_pois)
        remaining_clusters = len(chain) - idx_pos - 1
        # 剩余 cluster 还需要多少天(每集群至少 1 天)
        # 如果剩 N-idx_pos-1 个 cluster 且只剩 days-len(days)-1 天可分配,需合并
        # 简化:如果"剩余 cluster 数 + 已用天数" > days,最后一天要容纳多余 cluster

        is_last_day = len(days) == travel_days - 1  # 是否即将到第 N 天

        # 决策:加入当前 day 还是新开 day
        if not cur_day:
            cur_day.extend(c_pois)
            cur_count = c_count
            cur_center = c_center
            continue

        # 距离判定:超阈值必须新开一天
        if cur_center and c_center:
            dist = haversine_km(cur_center, c_center)
        else:
            dist = 0.0

        # 距离超阈值 → 新开 day(除非已是最后一天,强塞避免丢 POI)
        if dist > SAME_DAY_MAX_KM and not is_last_day:
            days.append(cur_day)
            cur_day = list(c_pois)
            cur_count = c_count
            cur_center = c_center
            continue

        # 距离可接受,但当天 POI 数已超 target → 新开(同样避开最后一天)
        if cur_count >= TARGET_POIS_PER_DAY and not is_last_day:
            days.append(cur_day)
            cur_day = list(c_pois)
            cur_count = c_count
            cur_center = c_center
            continue

        # 合并(可能跨城市 — 但 days 不足时这是次优解,保 POI 不丢)
        cur_day.extend(c_pois)
        cur_count += c_count
        if c_center and cur_center:
            cur_center = (
                (cur_center[0] * (cur_count - c_count) + c_center[0] * c_count) / cur_count,
                (cur_center[1] * (cur_count - c_count) + c_center[1] * c_count) / cur_count,
            )

    if cur_day:
        days.append(cur_day)

    # days 数量可能不等于 travel_days(如 cluster 极少,合并后只 1 天)
    # 用空日补到 travel_days
    while len(days) < travel_days:
        days.append([])
    # 反过来可能多于 travel_days(极端情况),截断多余空天
    days = days[:travel_days]
    return days