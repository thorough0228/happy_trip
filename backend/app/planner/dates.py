"""日期展开工具。"""
from datetime import date, timedelta


def expand_dates(start: date, days: int) -> list[date]:
    """把 start_date + travel_days 展开成具体日期列表。"""
    return [start + timedelta(days=i) for i in range(days)]