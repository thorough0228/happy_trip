"""
PlannerContext:整个项目的"产品逻辑心脏"。

把所有外部事实(景点/票价/天气)打包,让 LLM 在事实范围内做编排。
LLM 不再是事实源,只是编排器。
"""
from datetime import date
from typing import Awaitable, Callable

from pydantic import BaseModel, Field

from app.models.poi import POI
from app.models.schemas import TripRequest, WeatherDay
from app.planner.dates import expand_dates
from app.planner.pois import search_attractions
from app.planner.pricing import get_attraction_price
from app.planner.weather import get_weather_forecast

# 进度上报回调签名:async def reporter(stage: str, pct: int) -> None
ProgressReporter = Callable[[str, int], Awaitable[None]]


class PlannerContext(BaseModel):
    """所有外部事实的打包结构,LLM 唯一能看到的事实源。"""

    request: TripRequest                        # 用户原始请求
    destination: str                            # 目的地(冗余,方便访问)
    dates: list[date] = Field(default_factory=list)  # 行程日期列表(L7 才完整)
    attractions: list[POI] = Field(default_factory=list)  # 景点候选
    weather: list[WeatherDay] = Field(default_factory=list)  # 天气快照(L7)

    def summary(self) -> str:
        """序列化成可读字符串,用于塞进 LLM prompt。"""
        lines = [f"目的地: {self.destination}"]
        if self.dates:
            lines.append(f"日期: {', '.join(d.isoformat() for d in self.dates)}")
        lines.append(f"\n【景点候选】共 {len(self.attractions)} 个")
        for p in self.attractions[:15]:  # 截断避免 prompt 过长
            price = f"{p.cost}元" if p.cost > 0 else "免费"
            lines.append(f"  - {p.name} | {p.address} | {p.location} | {price}")
        if self.weather:
            lines.append(f"\n【天气】共 {len(self.weather)} 天")
            for w in self.weather:
                lines.append(f"  - {w.day}: {w.weather}, {w.temp_min}°C ~ {w.temp_max}°C")
        return "\n".join(lines)


async def build_context(
    req: TripRequest,
    reporter: ProgressReporter | None = None,
) -> PlannerContext:
    """
    编译 PlannerContext。

    当前阶段:景点召回 + 价格填充 + 日期展开 + 天气快照。
    系统不再规划酒店和餐厅,任何一步失败都不抛错,降级为空/默认值,PlannerContext 仍然返回。

    reporter:可选进度回调,被调用方传入时会按子阶段上报(stage + pct)。
              上报节点:
                10% 搜索景点候选
                45% 获取天气预报
              价格填充和日期展开是同步操作,不单独上报。
    """
    async def step(stage: str, pct: int) -> None:
        if reporter is not None:
            await reporter(stage, pct)

    await step("🔍 搜索景点候选...", 10)
    attractions = await search_attractions(req.destination, limit=10)

    # L6: 给景点填价格(LLM 后续只能引用,不能编)
    for p in attractions:
        if p.cost == 0.0:
            p.cost = get_attraction_price(req.destination, p.name)

    # L7: 日期展开 + 天气快照
    await step("🌤 获取天气预报...", 45)
    dates = expand_dates(req.start_date, req.travel_days)
    weather = await get_weather_forecast(req.destination, dates)

    return PlannerContext(
        request=req,
        destination=req.destination,
        dates=dates,
        attractions=attractions,
        weather=weather,
    )