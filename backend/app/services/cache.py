"""
通用异步缓存(Redis 后端,带键前缀)。

接口签名兼容旧内存版(get/set/clear/stats),但所有函数改为 async,
调用方需要 await。

适用场景:
- 高德 API 调用缓存(同一城市+关键词的结果短期不变)
- 任何"短期不变"的查询

键前缀 `ht:cache:` 防止与其它 Redis 用户冲突。
"""
import json
from typing import Any

from app.core.redis_client import get_redis

DEFAULT_TTL = 3600  # 1 小时
KEY_PREFIX = "ht:cache:"


def _full_key(key: str) -> str:
    return f"{KEY_PREFIX}{key}"


async def get(key: str) -> Any | None:
    """读取缓存。命中且未过期返回 value,否则返回 None。"""
    redis = get_redis()
    raw = await redis.get(_full_key(key))
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw  # 兜底:旧数据或非 JSON 字符串原样返回


async def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """写入缓存,默认 1 小时过期。value 用 JSON 序列化。"""
    redis = get_redis()
    payload = json.dumps(value, ensure_ascii=False, default=str)
    await redis.set(_full_key(key), payload, ex=ttl)


async def clear() -> None:
    """清空所有 happy_trip 缓存(不影响其它 Redis 用户)。"""
    redis = get_redis()
    cursor = 0
    while True:
        cursor, keys = await redis.scan(cursor=cursor, match=f"{KEY_PREFIX}*", count=100)
        if keys:
            await redis.delete(*keys)
        if cursor == 0:
            break


async def stats() -> dict:
    """查看缓存状态:大小、命中 key 列表(粗略统计)。"""
    redis = get_redis()
    keys: list[str] = []
    cursor = 0
    while True:
        cursor, batch = await redis.scan(cursor=cursor, match=f"{KEY_PREFIX}*", count=100)
        keys.extend(batch)
        if cursor == 0:
            break
    return {
        "size": len(keys),
        "keys": [k[len(KEY_PREFIX):] for k in keys[:20]],
    }