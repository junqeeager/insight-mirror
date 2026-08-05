"""事件查询路由"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from core.database import Database
from api.deps import get_current_user, get_db
from api.schemas import EventOut

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=list[EventOut])
def list_events(
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=10000),
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """查询事件列表（可按来源、类型、时间过滤）"""
    events = db.get_events(
        user_id=user["id"],
        source=source,
        event_type=event_type,
        since=since,
        limit=limit,
    )
    return [EventOut.from_event(e) for e in events]
