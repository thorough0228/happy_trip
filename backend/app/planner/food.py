"""餐饮候选召回业务层。

L10.B 优化:多关键词召回,扩大候选多样性,提高 LLM 候选命中率。
"""
from app.models.poi import POI
from app.services.amap import search_poi


# 默认的多桶关键词:不同维度补充候选
DEFAULT_KEYWORDS = [
    "餐厅",       # 综合
    "美食",       # 美食推荐
    "本地特色",   # 当地特色
    "小吃",       # 小吃快餐
]


async def search_food(city: str, keyword: str = "", limit: int = 30) -> list[POI]:
    """
    搜索目的地的餐厅(多关键词合并召回)。

    Args:
        city: 城市名
        keyword: 用户偏好 cuisine(如 "火锅"、"川菜");为空用默认多桶
        limit: 返回条数上限

    Returns:
        POI 列表(去重)。
    """
    # 关键词列表:用户偏好 + 默认桶
    if keyword:
        keywords = [keyword] + DEFAULT_KEYWORDS
    else:
        keywords = DEFAULT_KEYWORDS

    # 多关键词搜索 + 去重
    seen_ids: set[str] = set()
    all_pois: list[POI] = []
    for kw in keywords:
        try:
            pois = await search_poi(
                keywords=kw,
                region=city,
                types="餐饮",
                page_size=20,  # 每个关键词取 20,合并去重
            )
        except Exception:
            continue
        for p in pois:
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                all_pois.append(p)
        # 提前够数就退出(节省 QPS)
        if len(all_pois) >= limit * 1.5:
            break

    return all_pois[:limit]