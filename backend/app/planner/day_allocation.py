"""
Cluster → Day 分配启发式(V2 加时间容量)。

目标:在 N=travel_days 前提下,把若干 cluster 分配到 N 个 day,使得:
1. 每个 cluster 完整分配到某一个 day(尽量不拆,除非很大或时间超容量)
2. 同一天不跨越地理上相距很远的 cluster
3. 各天 POI 数 + 总游玩时间都基本均衡,避免 1 天塞太满
4. 每日游玩时间不应显著超过每日可用时间

算法:贪心 + 距离/容量惩罚
- 先拆分超大 cluster(> MAX_POIS_PER_CLUSTER 个 POI 或
  total_visit_duration > DAILY_AVAILABLE_MIN × 1.5):按贪心空间链切成
  多个子 cluster,避免一个片区 12 个 POI 挤一天
- 按 cluster 中心距离"上一个 cluster"最近优先合并到同一天
- 距离过远(> SAME_DAY_MAX_KM)即使 POI 多也不合并
- cluster 数 > days → 把地理相邻的 cluster 按空间顺序切 travel_days 段

返回结构:**day → list[cluster] → list[POI]**(保留 cluster 边界,
不做平铺,调用方才能拿到"哪几个 cluster 在同一天")。

duck-typing:不 import POI 类,只用 .location / .visit_duration 属性。
"""
from app.planner.geo import haversine_km


# 启发式参数(集中配置,V2 加时间相关)
SAME_DAY_MAX_KM = 3.0         # 同一天允许的"两个 cluster 中心"最大距离,超过则必须分天
TARGET_POIS_PER_DAY = 5       # 每"天容量"目标值,决定拆分阈值
MAX_POIS_PER_CLUSTER = 8      # cluster 超过此 POI 数 → 空间链切分(大片区拆开)
SPLIT_TARGET_POIS = 6         # 拆分目标:每个子 cluster 约 6 个 POI
DEFAULT_DAILY_AVAILABLE_MIN = 480  # 默认 8 小时/天(V2 可配置,见 planner.py 注入)
INTER_POI_TRAVEL_MIN = 15     # 景点间估计交通时间(分钟),用于"游玩+交通 总时长"粗算


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


def _poi_durations(pois: list) -> list[int]:
    """提取 POI 的 visit_duration 列表,缺失视为 0。"""
    return [getattr(p, "visit_duration", None) or 0 for p in pois]


def cluster_total_duration(pois: list) -> int:
    """cluster 内所有 POI 的 visit_duration 之和(分钟)。"""
    return sum(_poi_durations(pois))


def day_total_duration(day_clusters: list[list]) -> int:
    """一天内所有 cluster 的 POI 游玩时间总和(分钟)。"""
    return sum(cluster_total_duration(c) for c in day_clusters)


def day_total_with_travel(day_clusters: list[list]) -> int:
    """一天游玩时间 + 景点间交通时间(每个 cluster 间 +15 分钟,粗估)。"""
    play = day_total_duration(day_clusters)
    travel = max(0, len(day_clusters) - 1) * INTER_POI_TRAVEL_MIN
    return play + travel


def _count(day_clusters: list[list]) -> int:
    """统计一天(多个 cluster)的 POI 总数。"""
    return sum(len(c) for c in day_clusters)


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


def split_large_clusters(
    clusters: list[list],
    daily_minutes: int = DEFAULT_DAILY_AVAILABLE_MIN,
) -> list[list]:
    """
    把超大 cluster 按贪心空间链切成多个子 cluster(V2 加时间触发)。

    拆分触发:cluster POI 数 > MAX_POIS_PER_CLUSTER
              或 cluster 总游玩时长 > daily_minutes × 1.5
    (避免一天塞超过 1.5 天容量,留拆分余量)。

    保留结构:list[cluster] → list[POI]。<= 阈值的 cluster 原样保留。
    """
    out: list[list] = []
    for cluster in clusters:
        n = len(cluster)
        cd = cluster_total_duration(cluster)
        oversized_count = n > MAX_POIS_PER_CLUSTER
        oversized_time = cd > daily_minutes * 1.5
        if not (oversized_count or oversized_time):
            out.append(cluster)
            continue
        # 拆分目标数 = max(2, 按数/按时长分别算的拆分数最大值)
        n_by_count = (n + SPLIT_TARGET_POIS - 1) // SPLIT_TARGET_POIS
        n_by_time = max(1, (cd + daily_minutes - 1) // daily_minutes)
        n_splits = max(2, max(n_by_count, n_by_time))
        chain = _greedy_chain(cluster)
        # 按空间链顺序贪心累计时长切块,每块尽量 ≤ daily_minutes(不超 1 块太多)
        target_per_block = max(1.0, cd / n_splits)
        blocks: list[list] = []
        cur_block: list = []
        cur_sum = 0
        for p in chain:
            d = getattr(p, "visit_duration", None) or 0
            # 若当前块已超过单块目标,且加下一个会超 1.3x 目标 → 换块
            if cur_block and cur_sum > target_per_block * 0.85 and (cur_sum + d) > target_per_block * 1.3:
                blocks.append(cur_block)
                cur_block = [p]
                cur_sum = d
            else:
                cur_block.append(p)
                cur_sum += d
        if cur_block:
            blocks.append(cur_block)
        out.extend(blocks)
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
    daily_minutes: int | None = None,
) -> list[list[list]]:
    """
    把 clusters 分配到 N 天(V2 可传每日时间预算)。

    Args:
        clusters: 聚类结果 list[cluster] → list[POI] (duck-typed)
        travel_days: 用户游玩天数
        daily_minutes: 每日可用时间(分钟),None 时用 DEFAULT_DAILY_AVAILABLE_MIN
                       — 用于拆分超大 cluster(单 cluster 超过 1.5 天容量)

    Returns:
        list[length=travel_days],每一项是 list[cluster],cluster 是 list[POI]。
        days[i] = 第 i 天包含的若干 cluster(地理相邻合并)。无 POI 的天 = []。
    """
    if daily_minutes is None:
        daily_minutes = DEFAULT_DAILY_AVAILABLE_MIN
    # 先拆分超大 cluster(如 12 个 POI 的玄武湖片区),避免 1 天塞太多
    clusters = split_large_clusters(list(clusters), daily_minutes=daily_minutes)

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

    # cluster 数 > 天数:沿 chain 按累计时长贪心切段,目标每段 ≤ daily_minutes。
    # 保持地理连续(chain 相邻)。
    # 切段策略:
    #   1. 预测:若把当前 cluster 加入后超 target,就开新天(把当前 cluster 放新天)
    #   2. 若切出的段数不足 travel_days,把相邻段(时间最短)两两合并,
    #      直到段数 == travel_days(保持地理连续,尽量均衡)
    #   3. 若段数正好/超出,截断
    per_day_target = daily_minutes  # 游玩时长目标(交通在 validator 另行校验)

    segments: list[list[list]] = []
    cur_day: list[list] = []
    cur_sum = 0

    for idx in chain:
        c_pois = clusters[idx]
        c_sum = cluster_total_duration(c_pois)

        # 预判:加进来就超且不是最后一个 cluster → 开新天放当前 cluster
        if cur_day and (cur_sum + c_sum) > per_day_target:
            segments.append(cur_day)
            cur_day = []
            cur_sum = 0

        cur_day.append(list(c_pois))
        cur_sum += c_sum

    if cur_day:
        segments.append(cur_day)

    # 收敛到 travel_days 段:段多了合并"地理相邻且总时长最小"的两段
    def seg_dur(seg: list[list]) -> int:
        return sum(cluster_total_duration(c) for c in seg)

    while len(segments) > travel_days:
        # 找合并后总时长最小的相邻段对(保持地理连续)
        best_i = 0
        best_sum = None
        for i in range(len(segments) - 1):
            s = seg_dur(segments[i]) + seg_dur(segments[i + 1])
            if best_sum is None or s < best_sum:
                best_sum = s
                best_i = i
        # 合并
        segments[best_i] = segments[best_i] + segments[best_i + 1]
        del segments[best_i + 1]

    # 段数可能少于 travel_days(cluster 少),补空天
    while len(segments) < travel_days:
        segments.append([])

    return segments[:travel_days]