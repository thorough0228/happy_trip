"""
启动入口。

L11 改造点:
- 使用 lifespan 启动期校验 Redis(连接失败进程报错退出,Redis 不可用不允许降级)
- 删除了原文件底部的旧测试 req 构造代码(已无意义)
"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.api.main:app",
        host="0.0.0.0",
        port=7000,
        reload=True,
        lifespan="on",
    )