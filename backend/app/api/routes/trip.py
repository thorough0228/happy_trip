from fastapi import APIRouter

from app.agents.planner import plan_trip
from app.models.schemas import TripRequest, TripPlan

router = APIRouter(prefix="/trip", tags=["trip"])


@router.post("/plan", response_model=TripPlan)
def plan(req: TripRequest) -> TripPlan:
    """接收用户请求,调用 Planner Agent 生成行程计划。"""
    return plan_trip(req)