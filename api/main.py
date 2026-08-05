"""FastAPI 应用入口"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.routers import (
    admin,
    auth,
    events,
    graph,
    profile,
    sources,
    stats,
    sync,
    topics,
)

logger = logging.getLogger("api")

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


class SPAStaticFiles(StaticFiles):
    """托管 React 构建产物；浏览器路由（非 /api 路径）回退到 index.html。"""

    async def get_response(self, path: str, scope):
        def is_spa_route(p: str) -> bool:
            return not (
                p.startswith("api/")
                or p.startswith("health")
                or p.startswith("assets/")
            )

        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or not is_spa_route(path):
                raise
            response = await super().get_response("index.html", scope)
        if response.status_code == 404 and is_spa_route(path):
            response = await super().get_response("index.html", scope)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预热 jieba，避免首个请求的冷启动延迟"""
    try:
        from analysis.keywords import segment_text
        segment_text("预热")
    except Exception:
        logger.warning("jieba 预热失败", exc_info=True)
    yield


app = FastAPI(
    title="Personal Profile API",
    version="1.0.0",
    description="个人认知画像系统 API（第二阶段）",
    lifespan=lifespan,
)

# 开发期放开跨域，便于浏览器直连与前端联调
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router)
app.include_router(topics.router)
app.include_router(profile.router)
app.include_router(stats.router)
app.include_router(graph.router)
app.include_router(auth.router)
app.include_router(sources.router)
app.include_router(sync.router)
app.include_router(admin.router)


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# 生产同源托管：uvicorn :8501 同时提供 React SPA 与 /api
if WEB_DIST.is_dir():
    app.mount("/", SPAStaticFiles(directory=str(WEB_DIST), html=True), name="spa")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """未捕获异常统一返回 JSON 500 并记录 traceback"""
    logger.exception("未捕获异常: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "内部错误"})
