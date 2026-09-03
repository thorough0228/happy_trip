"""
价格规则与静态票价表。

L6 核心:不让 LLM 编价格。三类价格来源不同:
- 景点:静态票价表(attraction_price.json)
- 酒店:城市档位 + 住宿类型 → 规则估价
- 餐饮:餐次 + 人数 → 规则估价(POI 暂没 cost 字段,先规则)

LLM 只能引用这些价格,不能自估。
"""
import json
from pathlib import Path

# 加载静态票价表(只在模块导入时读一次)
_TABLE_PATH = Path(__file__).parent / "attraction_price.json"
with open(_TABLE_PATH, "r", encoding="utf-8") as f:
    _PRICE_TABLE = json.load(f)

# 建索引: (city, name) -> item
_TABLE_INDEX: dict[tuple[str, str], dict] = {}
for item in _PRICE_TABLE.get("items", []):
    key = (item["city"], item["name"])
    _TABLE_INDEX[key] = item


# 城市档位系数(简化版,可后续接入更细的城市分级)
_CITY_TIER = {
    "北京": 1.5, "上海": 1.5, "深圳": 1.4, "广州": 1.3,
    "杭州": 1.2, "成都": 1.1, "西安": 1.0, "南京": 1.0,
    "厦门": 1.0, "大理": 0.8, "丽江": 0.8, "青岛": 0.9,
}

# 住宿类型系数
_ACCOMMODATION_COEFF = {
    "hotel": 1.0,
    "hostel": 0.5,
    "youth_hostel": 0.4,
}

# 餐次人均(CNY)
_MEAL_PER_PERSON = {
    "breakfast": 20,
    "lunch": 50,
    "dinner": 80,
}


def get_attraction_price(city: str, name: str, season: str = "normal") -> float:
    """
    查询景点票价。

    Args:
        city: 城市名
        name: 景点名(必须与票价表完全一致)
        season: "off" / "normal" / "peak"

    Returns:
        成人票价(CNY)。表中查不到返回 0.0(景点可能免费)。
    """
    item = _TABLE_INDEX.get((city, name))
    if not item:
        return 0.0
    profile = item.get("ticket_price_profile", {})
    return float(profile.get(f"{season}_season", profile.get("normal", 0.0)))


def estimate_hotel_cost(
    city: str,
    accommodation_type: str,
    party_size: int = 1,
    nights: int = 1,
) -> float:
    """
    酒店估价(规则)。

    简化规则: 基础价 × 城市系数 × 住宿类型系数 × 间数 × 晚数
    一间房默认住 2 人,party_size > 2 时按需算多间。
    """
    base = 200.0
    city_tier = _CITY_TIER.get(city, 1.0)
    accom_coeff = _ACCOMMODATION_COEFF.get(accommodation_type, 1.0)
    rooms = max(1, (party_size + 1) // 2)

    return round(base * city_tier * accom_coeff * rooms * nights, 2)


def estimate_food_cost(meal_type: str, party_size: int = 1) -> float:
    """
    餐饮估价(简化规则)。

    按餐次类型给一个合理价位,乘以人数。
    meal_type: "breakfast" / "lunch" / "dinner"
    """
    per_person = _MEAL_PER_PERSON.get(meal_type, 60.0)
    return round(per_person * party_size, 2)