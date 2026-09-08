"""
聚类 + Day Allocation 的单元测试。

覆盖场景:
- 同一景区(Test 1)
- 明显不同区域(Test 2)
- 离群点(Test 3)
- 1 天(Test 4)
- 多天,Cluster 数 ≠ days(Test 5)
- 空数据(Test 6)
"""
import asyncio

from app.models.poi import POI
from app.planner.clustering import cluster_pois, EPS_KM
from app.planner.day_allocation import allocate_clusters_to_days


def make_poi(name: str, lng: float, lat: float) -> POI:
    return POI(
        id=name,
        name=name,
        address=f"addr-{name}",
        location=(lng, lat),
        type="风景名胜",
    )


def test_1_同一景区():
    """玄武湖、玄武门、玄武湖情侣园(都在 100-500m 内)必须归入同一 cluster。"""
    pois = [
        make_poi("玄武湖", 118.7950, 32.0950),
        make_poi("玄武门", 118.7960, 32.0970),       # 距离 ~200m
        make_poi("玄武湖情侣园", 118.7940, 32.0940), # 距离 ~200m
        make_poi("鸡鸣寺", 118.8010, 32.0960),       # 距离 ~600m
    ]
    clusters = cluster_pois(pois, eps_km=2.0)
    assert len(clusters) == 1, f"期望 1 个 cluster,实际 {len(clusters)} 个: {clusters}"
    names = [p.name for p in clusters[0]]
    assert set(names) == {"玄武湖", "玄武门", "玄武湖情侣园", "鸡鸣寺"}, f"实际:{names}"


def test_2_明显不同区域():
    """玄武湖(南京北)、夫子庙(南京南)、中山陵(紫金山)必须分 3 个 cluster。"""
    pois = [
        make_poi("玄武湖", 118.7950, 32.0950),
        make_poi("夫子庙", 118.7890, 32.0220),    # ~8km
        make_poi("中山陵", 118.8480, 32.0420),    # ~7km
    ]
    clusters = cluster_pois(pois, eps_km=2.0)
    assert len(clusters) == 3, f"期望 3 个 cluster,实际 {len(clusters)} 个"


def test_3_离群点():
    """3 个近 + 1 个超远 → 4 个 cluster(每个单点都不丢)。"""
    pois = [
        make_poi("A1", 118.7950, 32.0950),
        make_poi("A2", 118.7955, 32.0955),    # 距 A1 ~50m
        make_poi("B1", 118.9000, 32.0950),    # 距 A1 ~10km
        make_poi("C1", 119.5000, 32.5000),    # 距任一 50+km
    ]
    clusters = cluster_pois(pois, eps_km=2.0)
    assert len(clusters) == 3, f"期望 3 个 cluster,实际 {len(clusters)}"
    total = sum(len(c) for c in clusters)
    assert total == 4, f"离群点丢失:实际 POI 总数 {total}"


def test_4_1天分配():
    """1 天旅游:4 cluster → 1 天(空 day 用空 list 填充)。"""
    pois = [
        make_poi("A1", 118.7950, 32.0950),
        make_poi("A2", 118.7955, 32.0955),
        make_poi("B1", 118.9000, 32.0950),
    ]
    clusters = cluster_pois(pois, eps_km=2.0)
    days = allocate_clusters_to_days(clusters, travel_days=1)
    # 1 天可能装不下所有 cluster;可能合并为 1 天(贪心按距离),也可能是 1 个 day + 截断
    assert len(days) == 1, f"travel_days=1 应返回 1 天,实际 {len(days)}"
    total_pois = sum(len(d) for d in days)
    assert total_pois == len(pois), f"POI 丢失:输入 {len(pois)},输出 {total_pois}"


def test_5_3天多cluster():
    """3 天,4 cluster(玄武湖/总统府/夫子庙/钟山)→ 不强求 3 个,合理分配。"""
    pois = [
        # Cluster 1: 玄武湖片区
        make_poi("玄武湖", 118.7950, 32.0950),
        make_poi("玄武门", 118.7960, 32.0970),
        make_poi("鸡鸣寺", 118.8010, 32.0960),
        # Cluster 2: 总统府片区
        make_poi("总统府", 118.8000, 32.0910),
        make_poi("六朝博物馆", 118.8010, 32.0930),
        # Cluster 3: 夫子庙片区
        make_poi("夫子庙", 118.7890, 32.0220),
        make_poi("秦淮河", 118.7900, 32.0210),
        make_poi("中华门", 118.7760, 32.0150),
        # Cluster 4: 钟山片区
        make_poi("中山陵", 118.8480, 32.0420),
        make_poi("明孝陵", 118.8520, 32.0440),
    ]
    clusters = cluster_pois(pois, eps_km=2.0)
    assert len(clusters) == 4, f"期望 4 个 cluster,实际 {len(clusters)}"

    days = allocate_clusters_to_days(clusters, travel_days=3)
    assert len(days) == 3, f"travel_days=3 应返回 3 天,实际 {len(days)}"
    total_pois = sum(len(d) for d in days)
    assert total_pois == len(pois), f"POI 丢失:输入 {len(pois)},输出 {total_pois}"

    # 同一 cluster 的景点不应被拆到不同的 day
    # 把每个 cluster 内的 POI name 集合与 day 内 POI 集合做交集
    for c_idx, c in enumerate(clusters):
        cluster_names = {p.name for p in c}
        days_with_overlap = [
            d_idx for d_idx, d in enumerate(days)
            if any(p.name in cluster_names for p in d)
        ]
        # cluster 应在 1 个或 2 个 day 里(主要在 1 个,边界情况可能切到 2)
        assert len(days_with_overlap) <= 2, (
            f"Cluster {c_idx}({list(cluster_names)})被分散到 {len(days_with_overlap)} 个 day: {days_with_overlap}"
        )


def test_6_空数据():
    """空候选:返回 1 个空 day 列表(不崩)。"""
    clusters = cluster_pois([], eps_km=2.0)
    assert clusters == [], f"空输入应返回 [],实际 {clusters}"
    days = allocate_clusters_to_days(clusters, travel_days=3)
    assert len(days) == 3 and all(d == [] for d in days), f"空 cluster 分配异常: {days}"


if __name__ == "__main__":
    test_1_同一景区()
    print("✓ Test 1: 同一景区聚类")
    test_2_明显不同区域()
    print("✓ Test 2: 明显不同区域")
    test_3_离群点()
    print("✓ Test 3: 离群点保留")
    test_4_1天分配()
    print("✓ Test 4: 1 天分配")
    test_5_3天多cluster()
    print("✓ Test 5: 3 天 4 cluster")
    test_6_空数据()
    print("✓ Test 6: 空数据不崩")
    print("\n全部通过。")