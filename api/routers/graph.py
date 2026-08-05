"""兴趣图谱路由"""

import threading
import time
from collections import OrderedDict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from analysis.graph import build_interest_graph
from api.deps import get_config, get_current_user, get_db
from api.schemas import GraphOut
from core.database import Database

router = APIRouter(prefix="/api/v1/graph", tags=["graph"])

_GRAPH_TTL = 300.0
_CACHE_MAX = 64
_CACHE: "OrderedDict[str, tuple]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _cache_get(key: str):
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached and time.monotonic() - cached[0] < _GRAPH_TTL:
            _CACHE.move_to_end(key)
            return cached[1]
    return None


def _cache_set(key: str, value) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


@router.get("", response_model=GraphOut)
def interest_graph(
    window_days: int = Query(90, ge=1, le=365),
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """返回兴趣共现图（nodes/edges），进程内缓存 5 分钟"""
    cache_key = f"{user['id']}:window:{window_days}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    since = datetime.now() - timedelta(days=window_days)
    events = db.get_events(user_id=user["id"], since=since, limit=10000)
    max_nodes = config.get("visualization", {}).get("max_nodes_graph", 50)
    data = build_interest_graph(events, max_nodes=max_nodes)

    _cache_set(cache_key, data)
    return data
