"""
任务进度跟踪(Redis 版)。

相比原内存版:
- 5 个函数全 async,与 FastAPI async event loop 兼容
- 任务存为 Redis STRING(JSON 序列化),key 格式 `ht:task:{task_id}`
- TTL 仅 create_task 设一次,update/complete 不重置(语义:600s 后自然过期)

终态(done/error)任务 600s 后自动消失,与原内存版一致。
"""
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from app.core.redis_client import get_redis

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


async def create_task() -> TaskProgress:
    """创建任务,初始状态 pending,TTL 从此刻开始 600s。"""
    task_id = uuid.uuid4().hex[:8]
    task = TaskProgress(task_id=task_id)
    redis = get_redis()
    await redis.set(
        _key(task_id),
        json.dumps(task.to_dict(), ensure_ascii=False, default=str),
        ex=TASK_TTL,
    )
    return task


async def update_progress(task_id: str, stage: str, progress: int) -> None:
    """更新进度(不重置 TTL)。"""
    redis = get_redis()
    raw = await redis.get(_key(task_id))
    if raw is None:
        return
    data = json.loads(raw)
    data["status"] = "running"
    data["stage"] = stage
    data["progress"] = progress
    data["updated_at"] = time.time()
    await redis.set(_key(task_id), json.dumps(data, ensure_ascii=False, default=str))


async def complete_task(task_id: str, result: Any) -> None:
    """标记任务完成(不重置 TTL)。"""
    redis = get_redis()
    raw = await redis.get(_key(task_id))
    if raw is None:
        return
    data = json.loads(raw)
    data["status"] = "done"
    data["stage"] = "完成"
    data["progress"] = 100
    data["result"] = result
    data["updated_at"] = time.time()
    await redis.set(_key(task_id), json.dumps(data, ensure_ascii=False, default=str))


async def fail_task(task_id: str, error: str) -> None:
    """标记任务失败(不重置 TTL)。"""
    redis = get_redis()
    raw = await redis.get(_key(task_id))
    if raw is None:
        return
    data = json.loads(raw)
    data["status"] = "error"
    data["error"] = error
    data["updated_at"] = time.time()
    await redis.set(_key(task_id), json.dumps(data, ensure_ascii=False, default=str))


async def get_task(task_id: str) -> TaskProgress | None:
    """读取任务;不存在或已过期返回 None。"""
    redis = get_redis()
    raw = await redis.get(_key(task_id))
    if raw is None:
        return None
    return TaskProgress.from_dict(json.loads(raw))