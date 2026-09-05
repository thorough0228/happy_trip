"""
Redis 异步客户端单例。

设计原则:
- 启动期 ping() 校验连接,失败抛 RuntimeError 让 uvicorn 退出(硬失败,不降级)
- 全链路复用同一个连接池,避免每个请求新建连接
- decode_responses=True:直接拿到 str,避免上层到处 decode
"""
import os

import redis.asyncio as aioredis
from dotenv import load_dotenv

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_client: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    """
    初始化全局 Redis 客户端。在 FastAPI lifespan 启动期调用一次。

    Returns:
        已通过 ping 校验的 redis.asyncio.Redis 实例。

    Raises:
        RuntimeError: 连接或 ping 失败时抛出,uvicorn 会将异常冒泡退出。
    """
    global _client
    if _client is not None:
        return _client

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
        raise RuntimeError(
            f"[redis] failed to connect to {REDIS_URL}: {e}. "
            "请确保 Redis 已启动,并在 .env 配置 REDIS_URL。"
        ) from e


async def close_redis() -> None:
    """关闭 Redis 连接(lifespan 关闭期调用)。"""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis() -> aioredis.Redis:
    """
    获取已初始化的 Redis 客户端。

    Raises:
        RuntimeError: 未先调用 init_redis() 时抛出。
    """
    if _client is None:
        raise RuntimeError("[redis] client not initialized; call init_redis() first")
    return _client