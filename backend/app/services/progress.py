"""
任务进度跟踪(Redis 主存,内存降级)。

- Redis 可用:任务存为 Redis STRING(JSON 序列化),key 格式 `ht:task:{task_id}`,TTL 600s
- Redis 不可用:降级为内存 dict(单进程有效,重启清空)。**SSE 流仍能跑**,
  只是后端重启后客户端会拿到"task expired"事件,然后前端跳回首页

为什么不完全 no-op:SSE 客户端订阅的 task 必须有地方存,完全透传会让整个异步任务
机制失效。降级到内存 dict 是最小可用方案。
"""
import asyncio
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core import redis_client

KEY_PREFIX = "ht:task:"
TASK_TTL = 600  # 秒


@dataclass
class TaskProgress:
    task_id: str
    status: str = "pending"          # pending / running / done / error
    stage: str = ""                  # 当前阶段中文描述
    progress: int = 0                # 0-100
    result: Any = None               # TripPlan (status=done 时)
    error: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TaskProgress":
        return cls(**data)


def _key(task_id: str) -> str:
    return f"{KEY_PREFIX}{task_id}"


# ---- 内存降级存储(Redis 不可用时使用)----
_memory_tasks: dict[str, TaskProgress] = {}
_memory_lock = asyncio.Lock()


async def _cleanup_memory_expired() -> None:
    """清理内存版里超过 TTL 的已完成任务(避免内存泄漏)。"""
    now = time.time()
    async with _memory_lock:
        expired = [
            tid for tid, t in _memory_tasks.items()
            if now - t.created_at > TASK_TTL and t.status in ("done", "error")
        ]
        for tid in expired:
            _memory_tasks.pop(tid, None)


async def create_task() -> TaskProgress:
    """创建任务,初始状态 pending。Redis 可用时 SET EX 600,降级时仅写内存。"""
    task_id = uuid.uuid4().hex[:8]
    task = TaskProgress(task_id=task_id)
    redis = redis_client.get_redis()
    if redis is None:
        async with _memory_lock:
            _memory_tasks[task_id] = task
        return task
    try:
        await redis.set(
            _key(task_id),
            json.dumps(task.to_dict(), ensure_ascii=False, default=str),
            ex=TASK_TTL,
        )
    except Exception as e:
        print(f"[progress] create_task Redis 失败,降级到内存: {e}")
        async with _memory_lock:
            _memory_tasks[task_id] = task
    return task


async def update_progress(task_id: str, stage: str, progress: int) -> None:
    """更新进度(不重置 TTL)。"""
    task = await get_task(task_id)
    if task is None:
        return
    task.status = "running"
    task.stage = stage
    task.progress = progress
    task.updated_at = time.time()
    await _persist_task(task, reset_ttl=False)


async def complete_task(task_id: str, result: Any) -> None:
    """标记任务完成(不重置 TTL)。"""
    task = await get_task(task_id)
    if task is None:
        return
    task.status = "done"
    task.stage = "完成"
    task.progress = 100
    task.result = result
    task.updated_at = time.time()
    await _persist_task(task, reset_ttl=False)


async def fail_task(task_id: str, error: str) -> None:
    """标记任务失败(不重置 TTL)。"""
    task = await get_task(task_id)
    if task is None:
        return
    task.status = "error"
    task.error = error
    task.updated_at = time.time()
    await _persist_task(task, reset_ttl=False)


async def get_task(task_id: str) -> TaskProgress | None:
    """读取任务;不存在或已过期返回 None。Redis 不可用时走内存 dict。"""
    redis = redis_client.get_redis()
    if redis is None:
        # 内存版顺便清理过期
        await _cleanup_memory_expired()
        async with _memory_lock:
            t = _memory_tasks.get(task_id)
            if t is None:
                return None
            # 检查 TTL(对终态生效,运行中不限制)
            if t.status in ("done", "error") and time.time() - t.created_at > TASK_TTL:
                _memory_tasks.pop(task_id, None)
                return None
            return TaskProgress.from_dict(t.to_dict())
    try:
        raw = await redis.get(_key(task_id))
    except Exception as e:
        print(f"[progress] get_task Redis 失败,降级到内存: {e}")
        async with _memory_lock:
            return _memory_tasks.get(task_id)
    if raw is None:
        return None
    return TaskProgress.from_dict(json.loads(raw))


async def _persist_task(task: TaskProgress, reset_ttl: bool) -> None:
    """把 task 写回存储。Redis 可用时 SET(不重置 TTL),不可用时写内存。"""
    redis = redis_client.get_redis()
    if redis is None:
        async with _memory_lock:
            _memory_tasks[task.task_id] = task
        return
    try:
        if reset_ttl:
            await redis.set(
                _key(task.task_id),
                json.dumps(task.to_dict(), ensure_ascii=False, default=str),
                ex=TASK_TTL,
            )
        else:
            await redis.set(
                _key(task.task_id),
                json.dumps(task.to_dict(), ensure_ascii=False, default=str),
            )
    except Exception as e:
        print(f"[progress] persist Redis 失败,降级到内存: {e}")
        async with _memory_lock:
            _memory_tasks[task.task_id] = task