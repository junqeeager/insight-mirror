"""统计路由"""

from fastapi import APIRouter, Depends

from core.database import Database
from api.deps import get_current_user, get_db
from api.schemas import StatsOut

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
def stats(
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """数据库整体统计"""
    return StatsOut(**db.get_stats(user["id"]))
