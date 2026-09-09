"""
FastAPI 应用入口。

新增 lifespan:启动时 init_db() + init_redis();
                关闭时 close_redis()。
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.history import router as history_router
from app.api.routes.trip import router as trip_router
from app.core import redis_client
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动期 init 数据库和 Redis;关闭期释放连接。"""
    init_db()
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
app.include_router(auth_router)
app.include_router(history_router)