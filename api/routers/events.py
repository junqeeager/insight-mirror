"""事件查询路由"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query

from core.database import Database
from api.deps import get_db
from api.schemas import EventOut

router = APIRouter(prefix="/api/v1/events", tags=["events"])


@router.get("", response_model=list[EventOut])
def list_events(
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = Query(100, ge=1, le=10000),
    db: Database = Depends(get_db),
):
    """查询事件列表（可按来源、类型、时间过滤）"""
    events = db.get_events(source=source, event_type=event_type, since=since, limit=limit)
    return [EventOut.from_event(e) for e in events]
