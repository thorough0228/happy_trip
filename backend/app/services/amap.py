"""高德地图 HTTP API 封装。

只负责"调 HTTP + 解析 + 转 POI",不涉及业务规则。
失败时返回空列表,不抛错(让上层降级)。

调用结果走 services.cache 内存缓存(TTL=1小时):
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


def search_poi(
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

    # 缓存 key:规范化所有参数
    cache_key = f"search_poi:{region}:{keywords}:{types or ''}:{page_size}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

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
        resp = httpx.get(
            f"{BASE_URL}/place/text",
            params=params,
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[amap] HTTP 请求失败: {e}")
        return []

    # 高德 status: "1" 成功, "0" 失败
    if data.get("status") != "1":
        print(f"[amap] API 返回错误: {data.get('info')}")
        return []

    # 把高德 dict 列表转 POI 列表
    pois: list[POI] = []
    for item in data.get("pois", []):
        try:
            poi = POI(
                id=item["id"],
                name=item["name"],
                address=item.get("address", "") or item.get("pname", "") + item.get("cityname", ""),
                location=item["location"],   # 由 POI 的 validator 解析
                type=item.get("type", ""),
            )
            pois.append(poi)
        except Exception as e:
            print(f"[amap] 跳过 POI {item.get('name')}: {e}")

    cache.set(cache_key, pois, ttl=CACHE_TTL)
    return pois


def get_weather(city: str) -> list[dict]:
    """
    获取未来几天的天气预报(带缓存,V3 weather/weatherInfo 接口,extensions=all)。

    缓存 key 只包含 city,高德返回的是"未来 3 天预报"——同一城市短时间内查多次应该拿同一份数据。
    """
    if not AMAP_API_KEY:
        print("[amap] 缺少 AMAP_API_KEY")
        return []

    cache_key = f"get_weather:{city}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        resp = httpx.get(
            f"{BASE_URL}/weather/weatherInfo",
            params={
                "key": AMAP_API_KEY,
                "city": city,
                "extensions": "all",
                "output": "json",
            },
            timeout=10.0,
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
    cache.set(cache_key, casts, ttl=CACHE_TTL)
    return casts