"""
通用内存缓存(TTL 过期)。

简单 key-value 缓存,带过期时间。适合:
- 高德 API 调用缓存(同一城市+关键词的结果短期不变)
- LLM 调用缓存(同一 prompt 复用)
- 任何"短期不变"的查询
"""
import time
from typing import Any

DEFAULT_TTL = 3600  # 1 小时

_cache: dict[str, tuple[float, Any]] = {}


def get(key: str) -> Any | None:
    """读取缓存。命中且未过期返回 value,否则返回 None。"""
    if key in _cache:
        expire_at, value = _cache[key]
        if time.time() < expire_at:
            return value
        # 过期,清理
        del _cache[key]
    return None


def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """写入缓存,默认 1 小时过期。"""
    _cache[key] = (time.time() + ttl, value)


def clear() -> None:
    """清空所有缓存(主要用于测试)。"""
    _cache.clear()


def stats() -> dict:
    """查看缓存状态:大小、命中次数(粗略统计)。"""
    return {
        "size": len(_cache),
        "keys": list(_cache.keys())[:20],  # 只展示前 20 个
    }