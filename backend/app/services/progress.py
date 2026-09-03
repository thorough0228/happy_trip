"""
任务进度跟踪(内存版,简单可靠)。

生产环境应该用 Redis,但 L9/L10 这个量级内存字典够用。
"""
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskProgress:
    task_id: str
    status: str = "pending"          # pending / running / done / error
    stage: str = ""                  # 当前阶段中文描述
    progress: int = 0                # 0-100
    result: Any = None               # TripPlan (status=done 时)
    error: str | None = None
    created_at: float = field(default_factory=time.time)


_tasks: dict[str, TaskProgress] = {}
_lock = threading.Lock()

# 任务过期时间(秒),超过会被清理
TASK_TTL = 600


def create_task() -> TaskProgress:
    task_id = uuid.uuid4().hex[:8]
    task = TaskProgress(task_id=task_id)
    with _lock:
        _cleanup_expired()
        _tasks[task_id] = task
    return task


def update_progress(task_id: str, stage: str, progress: int) -> None:
    with _lock:
        if task_id in _tasks:
            t = _tasks[task_id]
            t.status = "running"
            t.stage = stage
            t.progress = progress


def complete_task(task_id: str, result: Any) -> None:
    with _lock:
        if task_id in _tasks:
            t = _tasks[task_id]
            t.status = "done"
            t.stage = "完成"
            t.progress = 100
            t.result = result


def fail_task(task_id: str, error: str) -> None:
    with _lock:
        if task_id in _tasks:
            t = _tasks[task_id]
            t.status = "error"
            t.error = error


def get_task(task_id: str) -> TaskProgress | None:
    with _lock:
        return _tasks.get(task_id)


def _cleanup_expired() -> None:
    """清理超过 TTL 的已完成任务。"""
    now = time.time()
    expired = [
        tid for tid, t in _tasks.items()
        if now - t.created_at > TASK_TTL and t.status in ("done", "error")
    ]
    for tid in expired:
        _tasks.pop(tid, None)