"""
Trip 路由(SSE 异步任务版)。

接口契约:
- POST /api/trip/plan → 立即返回 {task_id},后端 BackgroundTasks 跑 plan_trip
- GET  /api/trip/stream/{task_id} → SSE 流,持续推送进度,终态携带 result
"""
import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, BackgroundTasks
from sse_starlette.sse import EventSourceResponse

from app.agents.planner import plan_trip
from app.models.schemas import TripRequest
from app.services import progress

router = APIRouter(prefix="/trip", tags=["trip"])


@router.post("/plan")
async def plan(req: TripRequest, bg: BackgroundTasks):
    """
    接收用户请求,创建任务并后台跑 plan_trip。

    Returns:
        {task_id: str}  前端拿 task_id 去订阅 SSE 流。
    """
    task = await progress.create_task()
    bg.add_task(_run_plan, task.task_id, req)
    return {"task_id": task.task_id}


async def _run_plan(task_id: str, req: TripRequest) -> None:
    """后台任务:实际跑规划,根据结果标记完成或失败。"""
    try:
        plan_result = await plan_trip(req, task_id=task_id)
        await progress.complete_task(task_id, plan_result.model_dump())
    except Exception as e:
        await progress.fail_task(task_id, f"{type(e).__name__}: {e}")


@router.get("/stream/{task_id}")
async def stream(task_id: str):
    """
    SSE 流端端点:持续推送 task 进度,终态后关闭流。

    事件名:
    - progress: {stage, progress, status}  阶段性进度
    - done:     TripPlan                    任务完成,data 是完整计划
    - failed:   {error: str}                任务失败或 task 不存在

    注意:不用 "error" 是因为 EventSource 的 'error' 既是我们推送的自定义事件名,
    也是浏览器原生连接错误事件名,会冲突。改用 'failed' 区分。
    """
    return EventSourceResponse(_event_generator(task_id))


async def _event_generator(task_id: str) -> AsyncIterator[dict]:
    """async generator:轮询 progress,推送 SSE 事件,终态收尾。"""
    poll_interval = 0.5
    last_progress = -1
    last_stage = ""

    # 第一次推送:让前端立即拿到任务存在性确认
    task = await progress.get_task(task_id)
    if task is None:
        yield {"event": "failed", "data": json.dumps({"error": "task not found"}, ensure_ascii=False)}
        return

    while True:
        task = await progress.get_task(task_id)
        if task is None:
            # 中途被清理(TTL 过期或服务重启)
            yield {"event": "failed", "data": json.dumps({"error": "task expired"}, ensure_ascii=False)}
            return

        # 只在进度或阶段变化时推送 progress 事件(避免噪音)
        if task.progress != last_progress or task.stage != last_stage:
            last_progress = task.progress
            last_stage = task.stage
            yield {
                "event": "progress",
                "data": json.dumps(
                    {
                        "status": task.status,
                        "stage": task.stage,
                        "progress": task.progress,
                    },
                    ensure_ascii=False,
                ),
            }

        # 终态:推送最终事件后退出(流关闭,浏览器停止重连)
        if task.status == "done":
            yield {
                "event": "done",
                "data": json.dumps(task.result, ensure_ascii=False, default=str),
            }
            return
        if task.status == "error":
            yield {
                "event": "failed",
                "data": json.dumps({"error": task.error or "unknown error"}, ensure_ascii=False),
            }
            return

        await asyncio.sleep(poll_interval)