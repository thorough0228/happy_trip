"""高德地图 HTTP API 异步封装。

相比 L9 的同步版:
- httpx.AsyncClient 全程异步,无线程开销
- cache.get/set 改为 await
- 失败时返回空列表,不抛错(让上层降级)

调用结果走 Redis 缓存(TTL=1 小时,见 app/services/cache.py):
- 同一城市+关键词的搜索结果短期不变,避免重复调用
- 高德 QPS 限制下,缓存能显著降低调用次数
"""
import os

import httpx
from dotenv import load_dotenv

from app.models.poi import POI
from app.services import cache

load_dotenv()

AMAP_API_KEY = os.getenv("AMAP_API_KEY")
BASE_URL = "https://restapi.amap.com/v3"

CACHE_TTL = 3600  # 1 小时

# 复用同一 httpx.AsyncClient,避免每次请求新建 TCP 连接
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def search_poi(
    keywords: str,
    region: str,
    types: str | None = None,
    page_size: int = 10,
) -> list[POI]:
    """
    调用高德 V3 POI 关键字搜索接口(带缓存)。

    Args:
        keywords: 搜索关键词(如 "西湖"、"博物馆")
        region: 限定城市(如 "杭州")
        types: 分类过滤(如 "风景名胜|博物馆",None 不过滤)
        page_size: 返回条数上限,V3 默认 10,最大 25

    Returns:
        POI 列表。失败或无结果时返回空列表,不抛错。
    """
    if not AMAP_API_KEY:
        print("[amap] 缺少 AMAP_API_KEY")
        return []

    cache_key = f"search_poi:{region}:{keywords}:{types or ''}:{page_size}"
    cached = await cache.get(cache_key)
    if cached is not None:
        # cache 存的是 list[dict],需要重建 POI 实例
        return [POI.model_validate(item) for item in cached]

    params = {
        "key": AMAP_API_KEY,
        "keywords": keywords,
        "region": region,
        "page_size": page_size,
        "output": "json",
    }
    if types:
        params["types"] = types

    try:
        resp = await _get_client().get(
            f"{BASE_URL}/place/text",
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[amap] HTTP 请求失败: {e}")
        return []

    if data.get("status") != "1":
        print(f"[amap] API 返回错误: {data.get('info')}")
        return []

    pois: list[POI] = []
    for item in data.get("pois", []):
        try:
            # 解析营业时间(高德 V3 place/text 在 business.opening_hours 字段)
            # 不是所有 POI 都有,缺失为 None — Time Check 会跳过
            opening_hours = item.get("business", {}).get("opening_hours") or None
            poi = POI(
                id=item["id"],
                name=item["name"],
                address=item.get("address", "") or item.get("pname", "") + item.get("cityname", ""),
                location=item["location"],
                type=item.get("type", ""),
                opening_hours=opening_hours,
            )
            pois.append(poi)
        except Exception as e:
            print(f"[amap] 跳过 POI {item.get('name')}: {e}")

    await cache.set(cache_key, [p.model_dump() for p in pois], ttl=CACHE_TTL)
    return pois


async def get_weather(city: str) -> list[dict]:
    """
    获取未来几天的天气预报(带缓存,V3 weather/weatherInfo 接口,extensions=all)。

    缓存 key 只包含 city,高德返回的是"未来 3 天预报"——同一城市短时间内查多次应该拿同一份数据。
    """
    if not AMAP_API_KEY:
        print("[amap] 缺少 AMAP_API_KEY")
        return []

    cache_key = f"get_weather:{city}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = await _get_client().get(
            f"{BASE_URL}/weather/weatherInfo",
            params={
                "key": AMAP_API_KEY,
                "city": city,
                "extensions": "all",
                "output": "json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[amap] 天气请求失败: {e}")
        return []

    if data.get("status") != "1":
        print(f"[amap] 天气 API 返回错误: {data.get('info')}")
        return []

    forecasts = data.get("forecasts", [])
    if not forecasts:
        return []

    casts = forecasts[0].get("casts", [])
    await cache.set(cache_key, casts, ttl=CACHE_TTL)
    return casts


async def get_walking_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict | None:
    """
    调用高德 V3 direction/walking,返回两点步行路线。

    入参:origin / destination 都是 (lng, lat) 元组(与 POI.location 一致)。
    出参:`{coords, distance, duration}` dict。
        - coords: `[[lng, lat], ...]` 已解析的 polyline 坐标序列
        - distance / duration: 高德原始返回值(米 / 秒)
    失败或无路径返回 None。
    """
    if not AMAP_API_KEY:
        print("[amap] 缺少 AMAP_API_KEY")
        return None

    # 缓存 key:坐标对排序后拼成 hash(避免 A→B 和 B→A 重复存)
    a, b = sorted([origin, destination])
    cache_key = f"walking_route:{a[0]:.5f},{a[1]:.5f}|{b[0]:.5f},{b[1]:.5f}"
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    params = {
        "key": AMAP_API_KEY,
        "origin": f"{origin[0]},{origin[1]}",
        "destination": f"{destination[0]},{destination[1]}",
        "output": "json",
    }
    try:
        resp = await _get_client().get(f"{BASE_URL}/direction/walking", params=params)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[amap] walking route 请求失败: {e}")
        return None

    if data.get("status") != "1":
        print(f"[amap] walking route API 返回错误: {data.get('info')}")
        return None

    paths = data.get("route", {}).get("paths", [])
    if not paths:
        return None
    path = paths[0]

    # 解析所有 step 的 polyline → [[lng, lat], ...]
    coords: list[list[float]] = []
    for step in path.get("steps", []):
        for pair in step.get("polyline", "").split(";"):
            pair = pair.strip()
            if not pair:
                continue
            parts = pair.split(",")
            if len(parts) == 2:
                try:
                    coords.append([float(parts[0]), float(parts[1])])
                except ValueError:
                    pass

    result = {
        "coords": coords,
        "distance": path.get("distance"),
        "duration": path.get("duration"),
    }
    await cache.set(cache_key, result, ttl=CACHE_TTL * 24)  # 路线 24h 缓存(POI 不变)
    return result