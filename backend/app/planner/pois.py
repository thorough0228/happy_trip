"""景点候选召回的业务层。

调 services/amap.py 拿到 POI,加上业务规则(关键词、上限、降级)。
"""
from app.models.poi import POI
from app.services.amap import search_poi


async def search_attractions(
    city: str,
    keyword: str = "",
    limit: int = 10,
) -> list[POI]:
    """
    搜索目的地的景点。

    Args:
        city: 目的地城市名(如 "杭州")
        keyword: 关键词(如 "博物馆"、"西湖");空字符串搜全部景点
        limit: 最多返回条数

    Returns:
        景点 POI 列表。高德失败或无结果时返回空列表,不抛错。
    """
    pois = await search_poi(
        keywords=keyword if keyword else "景点",
        region=city,
        types="风景名胜|博物馆",
        page_size=limit,
    )
    return pois[:limit]