"""天气快照业务层。"""
from datetime import date

from app.models.schemas import WeatherDay
from app.services.amap import get_weather


async def get_weather_forecast(city: str, dates: list[date]) -> list[WeatherDay]:
    """
    获取行程日期的天气预报。

    高德 V3 通常返回未来 3 天预报,超过 3 天的行程,超出部分用 unknown 占位。
    失败时整段降级为 unknown,不抛错。
    """
    raw_casts = await get_weather(city)

    if not raw_casts:
        # 高德失败,整段降级
        return [
            WeatherDay(day=d, weather="unknown", temp_max=0, temp_min=0)
            for d in dates
        ]

    # 建索引: day -> cast
    by_date: dict[str, dict] = {}
    for cast in raw_casts:
        by_date[cast.get("date", "")] = cast

    result: list[WeatherDay] = []
    for d in dates:
        cast = by_date.get(d.isoformat())
        if cast:
            result.append(
                WeatherDay(
                    day=d,
                    weather=cast.get("dayweather", "unknown"),
                    temp_max=_safe_int(cast.get("daytemp", "0")),
                    temp_min=_safe_int(cast.get("nighttemp", "0")),
                )
            )
        else:
            # 超出预报范围(>3 天)
            result.append(WeatherDay(day=d, weather="unknown", temp_max=0, temp_min=0))
    return result


def _safe_int(v) -> int:
    """把可能是 None/空字符串/数字的字段安全转 int。"""
    try:
        return int(v)
    except (ValueError, TypeError):
        return 0