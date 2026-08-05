"""兴趣图谱路由"""

import threading
import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from analysis.graph import build_interest_graph
from api.deps import get_current_user, get_db
from api.schemas import GraphOut
from core.database import Database

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])

_GRAPH_TTL = 300.0
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


@router.get("", response_model=GraphOut)
def interest_graph(
    window_days: int = Query(90, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """返回兴趣共现图（nodes/edges），进程内缓存 5 分钟"""
    cache_key = f"{user['id']}:window:{window_days}"
    now = time.monotonic()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _GRAPH_TTL:
            return cached[1]

    since = datetime.now() - timedelta(days=window_days)
    events = db.get_events(user_id=user["id"], since=since, limit=10000)
    data = build_interest_graph(events)

    with _CACHE_LOCK:
        _CACHE[cache_key] = (now, data)
    return data
