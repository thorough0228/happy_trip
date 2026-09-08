"""
POI 地理聚类(DBSCAN 风格的纯 Python 实现,无 sklearn 依赖)。

为什么不用 sklearn:项目没有装,引入新依赖增加部署成本,N≤20 的小规模下
纯 Python O(N²) 实现足够。

算法:DBSCAN (Density-Based Spatial Clustering of Applications with Noise)
- 核心点:在 eps 半径内至少 min_samples 个邻居(含自身)
- 边界点:邻居不够但落在某核心点的 eps 内
- 噪声点:既不是核心也不是边界 → 离群点(保留,作为单点 cluster)

距离:haversine(球面距离,经纬度友好)。

关键不变量:
- 输入 0 个 POI → 返回空 list
- 输入 1 个 POI → 返回 [[poi]] 单点 cluster
- 所有 POI 距离极近 → 形成 1 个 cluster(全部聚一起)
- 所有 POI 距离极远 → 每个 POI 自成 1 个 cluster(离群保留)
- 离群 POI 不丢失,作为单点 cluster 输出
"""
from typing import Iterable

from app.models.poi import POI
from app.planner.geo import haversine_km


# DBSCAN 参数 — 可配置(便于调优)
EPS_KM = 2.0           # 邻域半径:两个 POI 距离 < 2km 视为同片
MIN_SAMPLES = 1        # 核心点最少邻居数;1 = 允许单点成 cluster(候选少时不丢)


def cluster_pois(
    pois: Iterable[POI],
    eps_km: float = EPS_KM,
    min_samples: int = MIN_SAMPLES,
) -> list[list[POI]]:
    """
    把 POI 按经纬度聚类,返回 list[list[POI]]。

    每条 list 是一个 cluster。顺序按"确定性半径搜索"先后产生,
    同一输入每次结果一致(稳定排序)。

    Args:
        pois: POI 列表(可迭代)
        eps_km: DBSCAN 邻域半径(km),默认 2.0
        min_samples: 核心点最少邻居数,默认 1(允许孤立 POI 自成 cluster)

    Returns:
        list[cluster],每个 cluster 是 POI 列表(≥1 个)。
        输入为空 → 返回空 list。
    """
    # 过滤无 location 的 POI(无法聚类,放末尾作为离群组)
    geocoded = [p for p in pois if p.location is not None]
    no_loc = [p for p in pois if p.location is None]

    # 按 name 稳定排序(确定性),保证相同输入有相同 cluster 顺序
    geocoded.sort(key=lambda p: p.name)

    n = len(geocoded)
    if n == 0:
        # 全无 location → 把 no_loc 单独成组返回(不丢)
        if no_loc:
            return [no_loc]
        return []

    # DBSCAN 主流程
    labels = [-1] * n  # -1 = 未访问/噪声;0..k-1 = cluster id
    cluster_id = 0

    for i in range(n):
        if labels[i] != -1:
            continue
        # 计算 i 的邻居
        neighbors = _region_query(geocoded, i, eps_km)
        if len(neighbors) < min_samples:
            # 暂时标记为噪声(后续若被别的核心点纳入会改 label)
            continue
        # i 是核心点,扩展 cluster
        labels[i] = cluster_id
        seed_set = list(neighbors)
        j = 0
        while j < len(seed_set):
            q = seed_set[j]
            if labels[q] == -1:
                labels[q] = cluster_id  # 噪声→本次 cluster 成员
                q_neighbors = _region_query(geocoded, q, eps_km)
                if len(q_neighbors) >= min_samples:
                    seed_set.extend(q_neighbors)
            elif labels[q] == -1 or labels[q] is None:
                labels[q] = cluster_id
            j += 1
        cluster_id += 1

    # 处理剩余 -1(噪声/离群):作为单点 cluster 保留(不丢)
    clusters: list[list[POI]] = [[] for _ in range(cluster_id)]
    for i, label in enumerate(labels):
        if label == -1:
            clusters.append([geocoded[i]])
        else:
            clusters[label].append(geocoded[i])

    # 无 location 的 POI 加到末尾 group
    if no_loc:
        clusters.append(no_loc)

    return clusters


def _region_query(pois: list[POI], idx: int, eps_km: float) -> list[int]:
    """返回 poi[idx] 在 eps_km 半径内的所有索引(含自身)。"""
    neighbors = []
    origin = pois[idx].location
    if origin is None:
        return neighbors
    for j, p in enumerate(pois):
        if p.location is None:
            continue
        if haversine_km(origin, p.location) <= eps_km:
            neighbors.append(j)
    return neighbors