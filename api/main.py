"""FastAPI 应用入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import events, profile, stats, topics

app = FastAPI(
    title="Personal Profile API",
    version="1.0.0",
    description="个人认知画像系统 API（第二阶段）",
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


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}
