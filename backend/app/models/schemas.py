from datetime import date
from pydantic import BaseModel, Field, computed_field
from typing import Literal
# ---------- TripRequest 相关模型 ----------
class Party(BaseModel):
    """人数信息"""
    adults: int = Field(ge=0, default=1, description="成人人数")
    children: int = Field(ge=0, default=0, description="儿童人数")
    elders: int = Field(ge=0, default=0, description="老人人数")
    companion_type: Literal["couple", "family", "friends", "solo"] = Field(default="friends", description="出行类型")
    @computed_field
    @property
    def total(self) -> int:
        return self.adults + self.children + self.elders


class TripRequest(BaseModel):
    """用户输入的完整请求(简化版:无 transportation/accommodation/budget)"""
    destination: str = Field(min_length=1, description="目的地")
    start_date: date = Field(description="出发日期")
    travel_days: int = Field(ge=1, le=30, description="旅行天数（1-30）")
    party: Party = Field(description="人数细节")
    preferences: list[str] = Field(default=[], description="正向偏好标签")
    negative_constraints: list[str] = Field(default=[], description="负向约束标签")


# ---------- TripPlan 相关模型 ----------
class Attraction(BaseModel):
    """景点/活动项"""
    name: str = Field(min_length=1, description="名称")
    address: str = Field(min_length=1, description="地址")
    location: tuple[float, float] | None = Field(default=None, description="经纬度 [lng, lat]")
    cost: float = Field(ge=0, description="花费（元）")
    notes: str | None = Field(default=None, description="备注")
    dist_from_prev_km: float | None = Field(default=None, description="到上一个 POI 的 haversine 距离(km),第一个景点为 None")


class Day(BaseModel):
    """每日行程 — 简化版:只含景点 + 酒店区域建议,不含三餐/具体酒店"""
    date: str = Field(description="日期字符串，如 '2026-10-01'")
    theme: str | None = Field(default=None, description="当日主题")
    attractions: list[Attraction] = Field(default=[], description="景点列表(已按路径最优排序)")
    hotel_area_hint: str | None = Field(default=None, description="酒店区域建议(LLM 生成,自然语言,如'春熙路/太古里附近,出行方便')")


class TripPlan(BaseModel):
    """LLM 输出的完整行程计划"""
    title: str = Field(min_length=1, description="行程标题")
    destination: str = Field(min_length=1, description="目的地回显")
    date_range: str = Field(description="日期范围，如 '2026-10-01 ~ 2026-10-05'")
    party: Party = Field(description="人数信息回显")
    days: list[Day] = Field(default=[], description="每日行程列表")
    notes: list[str] = Field(default=[], description="实用贴士")


# ---------- PlannerContext 相关模型 ----------
class WeatherDay(BaseModel):
    """单日天气快照(L7 由高德天气 API 填充)。"""
    day: date = Field(description="日期")
    weather: str = Field(description="天气描述,晴/多云/小雨/...")
    temp_max: int = Field(description="最高气温(℃)")
    temp_min: int = Field(description="最低气温(℃)")