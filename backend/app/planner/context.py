"""
PlannerContext:整个项目的"产品逻辑心脏"。

把所有外部事实(景点/酒店/餐饮/天气/预算)打包,让 LLM 在事实范围内做编排。
LLM 不再是事实源,只是编排器。
"""
from datetime import date

from pydantic import BaseModel, Field

from app.models.poi import POI
from app.models.schemas import BudgetRule, TripRequest, WeatherDay
from app.planner.dates import expand_dates
from app.planner.food import search_food
from app.planner.hotels import search_hotels
from app.planner.pois import search_attractions
from app.planner.pricing import (
    estimate_hotel_cost,
    get_attraction_price,
)
from app.planner.weather import get_weather_forecast


class PlannerContext(BaseModel):
    """所有外部事实的打包结构,LLM 唯一能看到的事实源。"""

    request: TripRequest                        # 用户原始请求
    destination: str                            # 目的地(冗余,方便访问)
    dates: list[date] = Field(default_factory=list)  # 行程日期列表(L7 才完整)
    attractions: list[POI] = Field(default_factory=list)  # 景点候选
    hotels: list[POI] = Field(default_factory=list)       # 酒店候选
    food: list[POI] = Field(default_factory=list)         # 餐饮候选
    weather: list[WeatherDay] = Field(default_factory=list)  # 天气快照(L7)
    budget_rule: BudgetRule | None = None               # 预算规则(L6)

    def summary(self) -> str:
        """序列化成可读字符串,用于塞进 LLM prompt。"""
        lines = [f"目的地: {self.destination}"]
        if self.dates:
            lines.append(f"日期: {', '.join(d.isoformat() for d in self.dates)}")
        lines.append(f"\n【景点候选】共 {len(self.attractions)} 个")
        for p in self.attractions[:15]:  # 截断避免 prompt 过长
            price = f"{p.cost}元" if p.cost > 0 else "免费"
            lines.append(f"  - {p.name} | {p.address} | {p.location} | {price}")
        lines.append(f"\n【酒店候选】共 {len(self.hotels)} 个")
        for p in self.hotels[:10]:
            lines.append(f"  - {p.name} | {p.address} | {p.location} | {p.cost}元/晚")
        lines.append(f"\n【餐饮候选】共 {len(self.food)} 个")
        for p in self.food[:20]:
            lines.append(f"  - {p.name} | {p.address} | {p.type}")
        if self.weather:
            lines.append(f"\n【天气】共 {len(self.weather)} 天")
            for w in self.weather:
                lines.append(f"  - {w.day}: {w.weather}, {w.temp_min}°C ~ {w.temp_max}°C")
        if self.budget_rule:
            lines.append(f"\n【预算】总额 {self.budget_rule.total} 元,档位 {self.budget_rule.level}")
        return "\n".join(lines)


async def build_context(req: TripRequest) -> PlannerContext:
    """
    编译 PlannerContext。

    当前阶段:景点+酒店+餐饮三类 POI 召回 + 价格填充 + 日期展开 + 天气快照。
    任何一步失败都不抛错,降级为空/默认值,PlannerContext 仍然返回。
    """
    attractions = await search_attractions(req.destination, limit=10)
    hotels = await search_hotels(req.destination, limit=10)
    food = await search_food(req.destination, keyword="", limit=30)

    # L6: 给 POI 填价格(LLM 后续只能引用,不能编)
    for p in attractions:
        if p.cost == 0.0:
            p.cost = get_attraction_price(req.destination, p.name)

    party_size = req.party.total
    for h in hotels:
        h.cost = estimate_hotel_cost(
            req.destination, req.accommodation, party_size, 1
        )

    # L7: 日期展开 + 天气快照
    dates = expand_dates(req.start_date, req.travel_days)
    weather = await get_weather_forecast(req.destination, dates)

    return PlannerContext(
        request=req,
        destination=req.destination,
        dates=dates,
        attractions=attractions,
        hotels=hotels,
        food=food,
        weather=weather,
    )