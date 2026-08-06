"""FastAPI 应用入口"""

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.deps import ensure_initialized, get_config, get_db_url
from api.routers import (
    account,
    admin,
    auth,
    events,
    graph,
    profile,
    report,
    sources,
    stats,
    sync,
    topics,
    youtube,
)
from core.database import Database

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
    """启动时建表、校验密钥并预热 jieba。"""
    config = get_config()
    if config.get("security", {}).get("require_secret_key") and not os.environ.get(
        "APP_SECRET_KEY"
    ):
        raise RuntimeError(
            "APP_SECRET_KEY 未配置；生产环境必须设置该密钥（可用 openssl rand -hex 32 生成）"
        )
    db = Database(get_db_url(config))
    try:
        ensure_initialized(db)
    finally:
        db.close()
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

_allowed_origins = get_config().get("security", {}).get("allowed_origins") or []
if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """补充基础安全响应头。"""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; script-src 'self'",
    )
    path = request.url.path
    content_type = response.headers.get("content-type", "")
    if path == "/" or (
        not path.startswith(("/api/", "/assets/", "/health"))
        and content_type.startswith("text/html")
    ):
        # SPA 入口不缓存，保证每次部署后用户都能拿到最新的 index.html
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    elif path.startswith("/assets/"):
        # 构建产物带内容哈希，可以安全长缓存
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@app.middleware("http")
async def request_logging(request: Request, call_next):
    """记录 API 请求耗时，便于定位慢接口（静态资源不记录）。"""
    start = time.monotonic()
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") or path == "/health":
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            path,
            response.status_code,
            elapsed_ms,
        )
    return response

app.include_router(events.router)
app.include_router(topics.router)
app.include_router(profile.router)
app.include_router(report.router)
app.include_router(stats.router)
app.include_router(graph.router)
app.include_router(auth.router)
app.include_router(account.router)
app.include_router(sources.router)
app.include_router(youtube.router)
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
