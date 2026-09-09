"""用户行程历史记录路由。"""

from fastapi import APIRouter, HTTPException, Request, status

from app.core.auth import require_user_id_from_request
from app.core.database import delete_trip, get_trip_by_id, get_user_trips

router = APIRouter(prefix="/api/history", tags=["历史记录"])


@router.get("")
async def list_trips(request: Request):
    """获取当前用户的所有行程历史。"""
    user_id = require_user_id_from_request(request)
    trips = get_user_trips(user_id)
    return {"trips": trips}


@router.get("/{trip_id}")
async def get_trip(trip_id: str, request: Request):
    """获取指定行程详情。"""
    user_id = require_user_id_from_request(request)
    trip = get_trip_by_id(trip_id)
    if not trip:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行程不存在")
    if trip["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")
    return trip


@router.delete("/{trip_id}")
async def remove_trip(trip_id: str, request: Request):
    """删除指定行程。"""
    user_id = require_user_id_from_request(request)
    deleted = delete_trip(trip_id, user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="行程不存在或无权删除")
    return {"ok": True}
