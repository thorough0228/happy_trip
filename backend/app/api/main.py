"""
FastAPI 应用入口。

新增 lifespan:启动时 init_redis()(硬失败,Redis 不可用则进程退出);
                关闭时 close_redis()。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.trip import router as trip_router
from app.core import redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动期校验 Redis,失败抛错让 uvicorn 退出;关闭期释放连接。"""
    await redis_client.init_redis()
    try:
        yield
    finally:
        await redis_client.close_redis()


app = FastAPI(title="Happy Trip Planner API", lifespan=lifespan)

# CORS:开发期放开,生产期改白名单
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查
@app.get("/health")
def health():
    return {"status": "ok"}


# 业务路由
app.include_router(trip_router, prefix="/api")