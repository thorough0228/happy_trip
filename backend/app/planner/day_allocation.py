"""
Cluster → Day 分配启发式。

目标:在 N=travel_days 前提下,把若干 cluster 分配到 N 个 day,使得:
1. 每个 cluster 完整分配到某一个 day(尽量不拆,除非很大)
2. 同一天不跨越地理上相距很远的 cluster
3. 各天 POI 数基本平衡(避免 1 天 8 个/2 天 0 个)

算法:贪心 + 距离惩罚
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

    # cluster 数 > 天数:贪心把相邻 cluster 合并到同一天(保留 cluster 边界)
    days = []
    cur_day: list[list] = []        # 当前天含的 cluster 们
    cur_count = 0
    cur_center = None

    for idx_pos, idx in enumerate(chain):
        c_pois = clusters[idx]
        c_center = centers[idx]
        c_count = len(c_pois)

        is_last_day = len(days) == travel_days - 1
        # 是否必须开始最后一天(剩的 cluster 只能塞最后一天):当已开 days 数 == days-1 时,
        # 后续所有 cluster 必须合到 cur_day 或最后一个 day。此处用 is_last_day 近似:
        # 若当前已是最后一个可用 day(还差一天就开满),合并阈值失效
        must_merge = len(days) >= travel_days - 1  # 已开 days-1 天,当前只能往最后一个塞

        if not cur_day:
            cur_day.append(list(c_pois))
            cur_count = c_count
            cur_center = c_center
            continue

        # 距离判定:超阈值必须新开一天(除非必须合并)
        if cur_center and c_center:
            dist = haversine_km(cur_center, c_center)
        else:
            dist = 0.0

        too_far = dist > SAME_DAY_MAX_KM
        too_many = cur_count >= TARGET_POIS_PER_DAY

        if not must_merge and (too_far or too_many):
            # 新开一天
            days.append(cur_day)
            cur_day = [list(c_pois)]
            cur_count = c_count
            cur_center = c_center
            continue

        # 合并进当前天(cluster 边界保留)
        cur_day.append(list(c_pois))
        cur_count += c_count
        if c_center and cur_center:
            cur_center = (
                (cur_center[0] * (cur_count - c_count) + c_center[0] * c_count) / cur_count,
                (cur_center[1] * (cur_count - c_count) + c_center[1] * c_count) / cur_count,
            )

    if cur_day:
        days.append(cur_day)

    # 补齐/截断到 travel_days
    while len(days) < travel_days:
        days.append([])
    days = days[:travel_days]
    return days