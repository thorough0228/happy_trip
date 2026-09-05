"""
通用异步缓存(Redis 后端,优雅降级)。

Redis 可用时:key 带 `ht:cache:` 前缀,JSON 序列化,TTL 1h 默认。
Redis 不可用时:所有操作静默降级 — get 返回 None(视为 miss),set / clear / stats no-op。

整个降级无副作用:不影响主流程稳定性,只是重复请求会每次都重新查高德 API。
"""
import json
from typing import Any

from app.core import redis_client

DEFAULT_TTL = 3600  # 1 小时
KEY_PREFIX = "ht:cache:"


def _full_key(key: str) -> str:
    return f"{KEY_PREFIX}{key}"


async def get(key: str) -> Any | None:
    """读取缓存。命中返回 value,未命中 / Redis 不可用 返回 None。"""
    redis = redis_client.get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(_full_key(key))
        if raw is None:
            return None
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw  # 兜底:旧数据或非 JSON 字符串原样返回
    except Exception:
        return None  # 网络抖动等 → 当作 miss


async def set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
    """写入缓存。Redis 不可用时静默 no-op。"""
    redis = redis_client.get_redis()
    if redis is None:
        return
    try:
        payload = json.dumps(value, ensure_ascii=False, default=str)
        await redis.set(_full_key(key), payload, ex=ttl)
    except Exception as e:
        # 写入失败不应阻塞主流程,降级为不缓存
        print(f"[cache] set({key}) 失败: {e}")


async def clear() -> None:
    """清空所有 happy_trip 缓存。Redis 不可用时 no-op。"""
    redis = redis_client.get_redis()
    if redis is None:
        return
    try:
        cursor = 0
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=f"{KEY_PREFIX}*", count=100)
            if keys:
                await redis.delete(*keys)
            if cursor == 0:
                break
    except Exception as e:
        print(f"[cache] clear 失败: {e}")


async def stats() -> dict:
    """查看缓存状态。Redis 不可用时返回 size=0。"""
    redis = redis_client.get_redis()
    if redis is None:
        return {"size": 0, "keys": [], "available": False}
    try:
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
            "available": True,
        }
    except Exception as e:
        return {"size": 0, "keys": [], "available": False, "error": str(e)}