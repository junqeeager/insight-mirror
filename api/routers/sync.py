"""按用户触发数据同步"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_user
from api.schemas import SyncIn
from api.tasks import get_task_for_user, sync_user_task

router = APIRouter(prefix="/api/v1/sync", tags=["sync"])


@router.post("", status_code=202)
def start_sync(
    body: Optional[SyncIn] = None,
    user: dict = Depends(get_current_user),
):
    """后台同步当前用户的数据源。"""
    source = (body or SyncIn()).source
    task_id = sync_user_task(user["id"], source=source)
    return {"task_id": task_id, "status": "started"}


@router.get("/{task_id}")
def sync_status(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """查询同步任务状态。"""
    task = get_task_for_user(task_id, user["id"])
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    task.pop("user_id", None)
    return task
