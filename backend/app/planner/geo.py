"""地理距离工具(haversine 球面距离)。"""
import math

EARTH_RADIUS_KM = 6371.0


def haversine_km(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """
    两点球面 haversine 距离(km)。

    入参是 (lng, lat) 元组 — 与 POI.location / Attraction.location 一致。
    返回地球表面两点最短弧长(km)。
    """
    lng1, lat1 = p1
    lng2, lat2 = p2
    lat1_r, lat2_r = math.radians(lat1), math.radians(lat2)
    dlat = lat2_r - lat1_r
    dlng = math.radians(lng2) - math.radians(lng1)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))