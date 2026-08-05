"""画像路由"""

from fastapi import APIRouter, Depends, HTTPException

from core.database import Database
from api.deps import get_current_user, get_db
from api.schemas import ProfileOut, RefreshTaskOut, TaskStatusOut
from api.tasks import get_task_for_user, refresh_profile

router = APIRouter(prefix="/api/v1/profile", tags=["profile"])


@router.get("/latest", response_model=ProfileOut)
def latest_profile(
    period: str = "weekly",
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """返回最近一次画像快照（不现场计算）"""
    profiles = db.get_profiles(user_id=user["id"], period=period, limit=1)
    if not profiles:
        raise HTTPException(
            status_code=404,
            detail=f"暂无 {period} 画像快照，请先调用 POST /api/v1/profile/refresh",
        )
    return ProfileOut.from_profile(profiles[0])


@router.post("/refresh", response_model=RefreshTaskOut, status_code=202)
def refresh(
    period: str = "weekly",
    user: dict = Depends(get_current_user),
):
    """触发后台重建画像（基于已同步数据）"""
    task_id = refresh_profile(period=period, user_id=user["id"])
    return RefreshTaskOut(task_id=task_id, message="画像重建任务已启动")


@router.get("/refresh/{task_id}", response_model=TaskStatusOut)
def task_status(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """查询画像重建任务状态"""
    task = get_task_for_user(task_id, user["id"])
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return TaskStatusOut(task_id=task_id, **task)
