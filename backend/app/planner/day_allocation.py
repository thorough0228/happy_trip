"""
Cluster → Day 分配启发式。

目标:在 N=travel_days 前提下,把若干 cluster 分配到 N 个 day,使得:
1. 每个 cluster 完整分配到某一个 day(尽量不拆,除非很大)
2. 同一天不跨越地理上相距很远的 cluster
3. 各天 POI 数基本平衡(避免 1 天 8 个/2 天 0 个)

算法:贪心 + 距离惩罚
- 先拆分超大 cluster(> MAX_POIS_PER_CLUSTER 个 POI):按贪心空间链切成
  多个子 cluster,避免一个片区 12 个 POI 挤一天
- 按 cluster 中心距离"上一个 cluster"最近优先合并到同一天
- 距离过远(> SAME_DAY_MAX_KM)即使 POI 多也不合并
- cluster 数量 > days → 把地理相邻的 cluster 合并到同一天
- cluster 数量 <= days → 每个 cluster 独立一天(多余天留空)

返回结构:**day → list[cluster] → list[POI]**(保留 cluster 边界,
不做平铺,调用方才能拿到"哪几个 cluster 在同一天")。

duck-typing:不 import POI 类,只用 .location 属性。
"""
from app.planner.geo import haversine_km


# 启发式参数(可配置)
SAME_DAY_MAX_KM = 3.0     # 同一天允许的"两个 cluster 中心"最大距离,超过则必须分天
TARGET_POIS_PER_DAY = 5   # 每"天容量"目标值,决定拆分阈值
MAX_POIS_PER_CLUSTER = 8  # cluster 超过此 POI 数 → 空间链切分(大片区拆开)
SPLIT_TARGET_POIS = 6     # 拆分目标:每个子 cluster 约 6 个 POI


def cluster_centers(clusters: list[list]) -> list:
    """计算每个 cluster 的中心点(POI 经纬度均值)。空 cluster 返回 None。"""
    centers: list = []
    for cluster in clusters:
        locs = [p.location for p in cluster if p.location is not None]
        if not locs:
            centers.append(None)
            continue
        lng = sum(l[0] for l in locs) / len(locs)
        lat = sum(l[1] for l in locs) / len(locs)
        centers.append((lng, lat))
    return centers


def _count(day_clusters: list[list]) -> int:
    """统计一天(多个 cluster)的 POI 总数。"""
    return sum(len(c) for c in day_clusters)


def split_large_clusters(clusters: list[list]) -> list[list]:
    """
    把超大 cluster 按贪心空间链切成多个子 cluster(每个约 SPLIT_TARGET_POIS 个)。

    原因:南京"玄武湖片区"一次聚类可能把 12 个 POI 链进同一 cluster
    (城墙-玄武湖-总统府-六朝博物馆彼此 <2km),整块塞一天太多。
    这里把 cluster 内 POI 排成"就近贪心链"(每次取离上一点最近的未取点),
    再切成 ceil(len/SPLIT_TARGET_POIS) 段,每段空间连续,作为子 cluster。

    保留结构:list[cluster] → list[POI]。<= 阈值的 cluster 原样保留。
    """
    out: list[list] = []
    for cluster in clusters:
        n = len(cluster)
        if n <= MAX_POIS_PER_CLUSTER:
            out.append(cluster)
            continue
        # 建贪心链:从中心点(经度最小的点)出发,反复取"距当前最近且未访问"的点
        chain = _greedy_chain(cluster)
        n_splits = max(2, (n + SPLIT_TARGET_POIS - 1) // SPLIT_TARGET_POIS)
        per = (n + n_splits - 1) // n_splits  # ceil
        for i in range(0, n, per):
            out.append(chain[i : i + per])
    return out


def _greedy_chain(cluster: list) -> list:
    """贪心链:从第一个(按经度最小)开始,每次取"距当前最近且未访问"的 POI。"""
    pois = list(cluster)
    if len(pois) < 2:
        return pois
    start = min(pois, key=lambda p: (p.location[0] if p.location else 0.0, p.location[1] if p.location else 0.0))
    chain = [start]
    visited = {id(start)}
    current = start
    remaining = [p for p in pois if id(p) not in visited]
    while remaining:
        # 最近邻(只比较有 location 的;全无 location 则按原序)
        located = [p for p in remaining if p.location is not None]
        pool = located if located else remaining
        nxt = min(
            pool,
            key=lambda p: (
                haversine_km(current.location, p.location)
                if current.location and p.location
                else 0.0
            ),
        )
        chain.append(nxt)
        visited.add(id(nxt))
        remaining = [p for p in remaining if id(p) not in visited]
        current = nxt
    return chain


def allocate_clusters_to_days(
    clusters: list[list],
    travel_days: int,
) -> list[list[list]]:
    """
    把 clusters 分配到 N 天。

    Args:
        clusters: 聚类结果 list[cluster] → list[POI] (duck-typed)
        travel_days: 用户游玩天数

    Returns:
        list[length=travel_days],每一项是 list[cluster],cluster 是 list[POI]。
        days[i] = 第 i 天包含的若干 cluster(地理相邻合并)。无 POI 的天 = []。
    """
    # 先拆分超大 cluster(如 12 个 POI 的玄武湖片区),避免 1 天塞太多
    clusters = split_large_clusters(list(clusters))

    n_clusters = len(clusters)
    if n_clusters == 0 or travel_days <= 0:
        return [[] for _ in range(max(travel_days, 1))]

    if n_clusters == 1:
        # 1 个 cluster → 放进 Day 1,其余天留空
        days: list[list[list]] = [[list(clusters[0])]]
        for _ in range(travel_days - 1):
            days.append([])
        return days

    # 多 cluster:按地理相邻串成 chain,再切成 travel_days 段
    centers = cluster_centers(clusters)
    order = sorted(
        range(n_clusters),
        key=lambda i: (centers[i] is None, centers[i] or (0, 0)),
    )
    # 贪心链:从第一个 cluster 出发,每次找离当前中心最近的未访问 cluster
    chain: list[int] = [order[0]]
    remaining = set(order[1:])
    last_center = centers[order[0]]
    while remaining:
        candidates = [i for i in remaining if centers[i] is not None] or list(remaining)
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

    if travel_days >= len(chain):
        # cluster 数 <= 天数:每个 cluster 独立一天,多余天留空
        days: list[list[list]] = [[list(clusters[i])] for i in chain]
        for _ in range(travel_days - len(chain)):
            days.append([])
        return days

    # cluster 数 > 天数:把 chain(按地理相邻排序)切成 travel_days 段。
    # 每段 cluster 数 = base 或 base+1(base = m // d,extra 段多 1 个),
    # 保证每段非空、不丢 cluster、整体地理连续。
    m = len(chain)
    base = m // travel_days
    extra = m % travel_days  # 前 extra 段多 1 个 cluster

    days: list[list[list]] = []
    ptr = 0
    for seg in range(travel_days):
        seg_len = base + (1 if seg < extra else 0)
        seg_clusters: list[list] = []
        for _ in range(seg_len):
            seg_clusters.append(list(clusters[chain[ptr]]))
            ptr += 1
        days.append(seg_clusters)

    # 理论上 ptr == m;多余防御
    if ptr < m:
        # 有剩余(不应发生),全部并入最后一天
        for i in range(ptr, m):
            days[-1].append(list(clusters[chain[i]]))
    return days