"""
PlannerContext:整个项目的"产品逻辑心脏"。

把所有外部事实(景点/票价/天气)打包,让 LLM 在事实范围内做编排。
LLM 不再是事实源,只是编排器。

新流程(在 LLM 前加地理聚类 + Day Allocation):
  检索 20 个候选 POI
  → DBSCAN 聚类(haversine, eps=2km)
  → Day Allocation(贪心,按地理相邻合并)
  → ctx.clusters / ctx.day_assignment 给 LLM 看到
"""
from datetime import date
from typing import Awaitable, Callable, Optional

from pydantic import BaseModel, Field

from app.models.poi import POI
from app.models.schemas import TripRequest, WeatherDay
from app.planner.clustering import cluster_pois
from app.planner.dates import expand_dates
from app.planner.day_allocation import allocate_clusters_to_days
from app.planner.pois import search_attractions
from app.planner.pricing import get_attraction_price
from app.planner.weather import get_weather_forecast

# 进度上报回调签名:async def reporter(stage: str, pct: int) -> None
ProgressReporter = Callable[[str, int], Awaitable[None]]


class ClusterGroup(BaseModel):
    """一天内的一个地理 cluster(保留 cluster 边界,给 LLM 清晰分组)。"""
    cluster_id: str = ""               # "cluster_1" ...
    pois: list[POI] = Field(default_factory=list)  # 该 cluster 的候选 POI


class DayAssignment(BaseModel):
    """Day Allocation 结果:一天分配到的若干 ClusterGroup。"""
    day: int                          # 0-indexed(LLM 输出 1-indexed 时记得 +1)
    clusters: list[ClusterGroup] = Field(default_factory=list)  # 该天含的 cluster(可多个,地理相邻)
    poi_count: int = 0                # 该天 POI 总数


class PlannerContext(BaseModel):
    """所有外部事实的打包结构,LLM 唯一能看到的事实源。"""

    request: TripRequest                        # 用户原始请求
    destination: str                            # 目的地(冗余,方便访问)
    dates: list[date] = Field(default_factory=list)  # 行程日期列表
    attractions: list[POI] = Field(default_factory=list)  # 景点候选(原始,平铺,供 LLM 反查)
    weather: list[WeatherDay] = Field(default_factory=list)  # 天气快照

    # 聚类 + Day Allocation 结果(LLM 看到的主要信息)
    day_assignments: list[DayAssignment] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def summary(self) -> str:
        """序列化成可读字符串,用于塞进 LLM prompt。"""
        lines = [f"目的地: {self.destination}"]
        if self.dates:
            lines.append(f"日期: {', '.join(d.isoformat() for d in self.dates)}")
        lines.append(f"游玩天数: {len(self.dates) if self.dates else self.request.travel_days} 天")

        # ---- 聚类 + Day Allocation(主要信息)----
        if self.day_assignments:
            lines.append(f"\n【地理聚类 + Day 分配】共 {self._cluster_count()} 个 cluster")
            for da in self.day_assignments:
                cluster_parts = []
                for c in da.clusters:
                    names = [p.name for p in c.pois]
                    center = self._format_center(c.pois)
                    cluster_parts.append(f"[{'; '.join(names)} @ {center}]")
                if not cluster_parts:
                    cluster_parts = ["(该天未分配 cluster)"]
                lines.append(
                    f"  Day {da.day + 1}(共 {da.poi_count} 个景点): {', '.join(cluster_parts)}"
                )

        # 详细 POI 列表(供 LLM 反查具体字段如 cost/address)
        lines.append(f"\n【完整候选 POI】共 {len(self.attractions)} 个")
        for p in self.attractions:
            price = f"{p.cost}元" if p.cost > 0 else "免费"
            loc = f"({p.location[0]:.4f},{p.location[1]:.4f})" if p.location else "(无坐标)"
            lines.append(f"  - {p.name} | {p.address} | {loc} | {price}")

        if self.weather:
            lines.append(f"\n【天气】共 {len(self.weather)} 天")
            for w in self.weather:
                lines.append(f"  - {w.day}: {w.weather}, {w.temp_min}°C ~ {w.temp_max}°C")
        return "\n".join(lines)

    def _cluster_count(self) -> int:
        return sum(len(da.clusters) for da in self.day_assignments)

    def _format_center(self, cluster: list[POI]) -> str:
        locs = [p.location for p in cluster if p.location is not None]
        if not locs:
            return "无坐标"
        lng = sum(l[0] for l in locs) / len(locs)
        lat = sum(l[1] for l in locs) / len(locs)
        return f"({lng:.4f},{lat:.4f})"


async def build_context(
    req: TripRequest,
    reporter: ProgressReporter | None = None,
    cluster_eps_km: float = 2.0,
) -> PlannerContext:
    """
    编译 PlannerContext。

    流程:
      1. 检索约 20 个景点候选(高德 POI text search)
      2. 填充价格
      3. DBSCAN 地理聚类
      4. Cluster → Day 分配
      5. 日期展开 + 天气快照

    系统不再规划酒店和餐厅,任何一步失败都不抛错,降级为空/默认值。

    reporter:可选进度回调,被调用方传入时按子阶段上报。
              上报节点:
                10% 搜索景点候选
                30% 地理聚类
                45% 获取天气预报
    """
    async def step(stage: str, pct: int) -> None:
        if reporter is not None:
            await reporter(stage, pct)

    # 多取一些候选(原 10 → 20),给聚类留出余量
    await step("🔍 搜索景点候选...", 10)
    raw_attractions = await search_attractions(req.destination, limit=20)

    # L6: 给景点填价格
    for p in raw_attractions:
        if p.cost == 0.0:
            p.cost = get_attraction_price(req.destination, p.name)

    # ---- 聚类(代码层真正做,不在 prompt 里说)----
    await step("🗺 地理聚类 + Day 分配...", 30)
    clusters = cluster_pois(raw_attractions, eps_km=cluster_eps_km)
    # Day Allocation
    day_alloc = allocate_clusters_to_days(clusters, req.travel_days)

    # 调试日志(开发期验证聚类效果)
    print(f"[cluster] POI 候选 {len(raw_attractions)} 个 → {len(clusters)} 个 cluster")
    for i, c in enumerate(clusters, 1):
        names = [p.name for p in c]
        print(f"[cluster]   Cluster {i}: {names}")

    # 组装 DayAssignment:day_alloc[i] = 第 i 天含的若干 cluster,每 cluster 是 POI list
    day_assignments: list[DayAssignment] = []
    for i, day_clusters in enumerate(day_alloc):
        all_pois = [p for c in day_clusters for p in c]
        groups = []
        for c_idx, c in enumerate(day_clusters):
            groups.append(
                ClusterGroup(cluster_id=f"cluster_{c_idx + 1}", pois=list(c))
            )
        day_assignments.append(
            DayAssignment(day=i, clusters=groups, poi_count=len(all_pois))
        )

    # 调试日志:Day 分配
    for da in day_assignments:
        clusters_desc = []
        for g in da.clusters:
            clusters_desc.append(f"Cluster[{', '.join(p.name for p in g.pois)}]")
        print(f"[alloc]   Day {da.day + 1} ← {' + '.join(clusters_desc)} ({da.poi_count} 个景点)")

    # L7: 日期展开 + 天气快照
    await step("🌤 获取天气预报...", 45)
    dates = expand_dates(req.start_date, req.travel_days)
    weather = await get_weather_forecast(req.destination, dates)

    return PlannerContext(
        request=req,
        destination=req.destination,
        dates=dates,
        attractions=raw_attractions,
        weather=weather,
        day_assignments=day_assignments,
    )