"""酒店候选召回业务层。"""
from app.models.poi import POI
from app.services.amap import search_poi


def search_hotels(city: str, limit: int = 10) -> list[POI]:
    """
    搜索目的地的酒店。

    高德 V3 中酒店分类是 `住宿服务`(更细的 `住宿服务;酒店` 也是合法)。
    """
    pois = search_poi(
        keywords="酒店",
        region=city,
        types="住宿服务",
        page_size=limit,
    )
    return pois[:limit]