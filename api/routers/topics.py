"""主题查询路由"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from core.database import Database
from api.deps import get_current_user, get_db
from api.schemas import TopicOut

router = APIRouter(prefix="/api/v1/topics", tags=["topics"])


@router.get("", response_model=list[TopicOut])
def list_topics(
    category: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """查询主题列表（可按分类过滤）"""
    topics = db.get_topics(user_id=user["id"], category=category, limit=limit)
    return [TopicOut.from_topic(t) for t in topics]
