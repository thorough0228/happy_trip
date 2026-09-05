"""
Redis 异步客户端单例(优雅降级版)。

设计原则:
- Redis 是**可选**依赖:启动期 ping 失败 → 静默返回 None,主流程不受影响
- 全链路复用同一个连接池,避免每个请求新建连接
- decode_responses=True:直接拿到 str,避免上层到处 decode

调用方约定:
- cache.py / progress.py 先调 get_redis() 拿到 Optional,None 表示不可用
- 此时降级为内存 / 透传,整个功能无副作用,不影响主流程稳定性
"""
import os

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

# 未配置 REDIS_URL 时,默认跳过 Redis(视为不可用)
REDIS_URL = os.getenv("REDIS_URL", "").strip()

_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis | None:
    """
    初始化全局 Redis 客户端。在 FastAPI lifespan 启动期调用一次。

    Returns:
        - 已通过 ping 校验的 redis.asyncio.Redis 实例(可用)
        - None(Redis 未配置或不可用 — 优雅降级,主流程照常运行)

    不抛错。日志区分"未配置"和"连接失败"两种情况。
    """
    global _client
    if _client is not None:
        return _client

    if not REDIS_URL:
        print("[redis] REDIS_URL 未配置,跳过 Redis(降级为内存 / 透传)")
        return None

    try:
        _client = aioredis.from_url(
            REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
        )
        await _client.ping()
        print(f"[redis] connected to {REDIS_URL}")
        return _client
    except Exception as e:
        print(
            f"[redis] 连接失败 ({e}),降级为内存 / 透传 — "
            "不影响主流程,功能正常但缓存和任务状态仅在内存生效"
        )
        _client = None
        return None


async def close_redis() -> None:
    """关闭 Redis 连接(lifespan 关闭期调用)。容忍未初始化。"""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except Exception:
            pass
        _client = None


def get_redis() -> aioredis.Redis | None:
    """
    获取已初始化的 Redis 客户端,失败或未配置时返回 None。

    调用方需自行判断 None 情况做降级处理。
    """
    return _client


def is_available() -> bool:
    """Redis 是否可用 — 缓存/任务模块快速判断的便捷方法。"""
    return _client is not None