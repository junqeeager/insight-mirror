"""数据访问层：优先调用 FastAPI，失败时回退直连 SQLite（带 TTL 缓存）"""

import functools
import logging
import threading
import time
from datetime import datetime
from typing import List, Optional

import httpx

from core.models import Depth, Event, EventType, Profile, Topic
from core.database import Database, database_url
from analysis.profile import ProfileGenerator

logger = logging.getLogger("frontend.data_access")

_API_TIMEOUT = 3.0

# 进程内 TTL 缓存：低流量个人项目足够，无需 Redis
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


def _stable_config(config: dict) -> tuple:
    """提取配置中影响数据来源的部分作为缓存键指纹"""
    return (
        config.get("frontend", {}).get("api_base", "http://localhost:8502"),
        config.get("frontend", {}).get("use_api", True),
        config.get("database", {}).get("url", "sqlite:///./data/profile.db"),
    )


def _ttl_cache(ttl_seconds: float):
    """按 (函数名, 配置指纹, 参数) 缓存结果，TTL 过期后重算"""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(config, *args, **kwargs):
            key = (
                fn.__name__,
                _stable_config(config),
                args,
                tuple(sorted((k, v) for k, v in kwargs.items() if v is not None)),
            )
            now = time.monotonic()
            with _CACHE_LOCK:
                hit = _CACHE.get(key)
                if hit is not None and now - hit[0] < ttl_seconds:
                    return hit[1]
            result = fn(config, *args, **kwargs)
            with _CACHE_LOCK:
                _CACHE[key] = (now, result)
            return result
        return wrapper
    return deco


def _use_api(config: dict) -> bool:
    return config.get("frontend", {}).get("use_api", True)


def _api_base(config: dict) -> str:
    return config.get("frontend", {}).get("api_base", "http://localhost:8502").rstrip("/")


def _db(config: dict) -> Database:
    return Database(database_url(config))


def _event_from_dict(d: dict) -> Event:
    d = dict(d)
    d["timestamp"] = datetime.fromisoformat(d["timestamp"])
    d["event_type"] = EventType(d["event_type"])
    d["depth"] = Depth(d.get("depth", "browse"))
    return Event(**d)


def _topic_from_dict(d: dict) -> Topic:
    return Topic(
        id=d["id"],
        name=d["name"],
        category=d["category"],
        frequency=d.get("frequency", 0),
        weight=d.get("weight", 0.0),
        first_seen=datetime.fromisoformat(d["first_seen"]) if d.get("first_seen") else None,
        last_seen=datetime.fromisoformat(d["last_seen"]) if d.get("last_seen") else None,
        related_topics=d.get("related_topics", []),
    )


def _profile_from_dict(d: dict) -> Profile:
    return Profile(
        id=d["id"],
        timestamp=datetime.fromisoformat(d["timestamp"]),
        period=d["period"],
        top_topics=[_topic_from_dict(t) for t in d.get("top_topics", [])],
        topic_clusters=d.get("topic_clusters", {}),
        total_events=d.get("total_events", 0),
        total_duration=d.get("total_duration", 0),
        active_days=d.get("active_days", 0),
        source_distribution=d.get("source_distribution", {}),
        emerging_topics=d.get("emerging_topics", []),
        declining_topics=d.get("declining_topics", []),
        insights=d.get("insights", []),
        event_ids=d.get("event_ids", []),
    )


@_ttl_cache(30)
def get_events(
    config: dict,
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 1000,
) -> List[Event]:
    """查询事件（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            params = {"limit": limit}
            if source:
                params["source"] = source
            if event_type:
                params["event_type"] = event_type
            if since:
                params["since"] = since.isoformat()
            resp = httpx.get(f"{_api_base(config)}/api/v1/events", params=params, timeout=_API_TIMEOUT)
            resp.raise_for_status()
            return [_event_from_dict(x) for x in resp.json()]
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 查询事件", exc_info=True)
    db = _db(config)
    try:
        return db.get_events(source=source, event_type=event_type, since=since, limit=limit)
    finally:
        db.close()


@_ttl_cache(30)
def get_topics(config: dict, category: Optional[str] = None, limit: int = 50) -> List[Topic]:
    """查询主题（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            params = {"limit": limit}
            if category:
                params["category"] = category
            resp = httpx.get(f"{_api_base(config)}/api/v1/topics", params=params, timeout=_API_TIMEOUT)
            resp.raise_for_status()
            return [_topic_from_dict(x) for x in resp.json()]
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 查询主题", exc_info=True)
    db = _db(config)
    try:
        return db.get_topics(category=category, limit=limit)
    finally:
        db.close()


@_ttl_cache(30)
def get_stats(config: dict) -> dict:
    """查询统计（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            resp = httpx.get(f"{_api_base(config)}/api/v1/stats", timeout=_API_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 查询统计", exc_info=True)
    db = _db(config)
    try:
        return db.get_stats()
    finally:
        db.close()


def get_latest_profile(
    config: dict,
    period: str = "weekly",
    fresh: bool = False,
) -> Optional[Profile]:
    """获取最近画像快照（60s 缓存；fresh=True 时跳过缓存并刷新缓存）"""
    key = ("get_latest_profile", _stable_config(config), period)
    now = time.monotonic()
    if not fresh:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and now - hit[0] < 60:
                return hit[1]
    profile = _fetch_latest_profile(config, period)
    if profile is not None:
        with _CACHE_LOCK:
            _CACHE[key] = (now, profile)
    return profile


def _fetch_latest_profile(config: dict, period: str) -> Optional[Profile]:
    """实际获取最近画像快照（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/profile/latest",
                params={"period": period},
                timeout=_API_TIMEOUT,
            )
            if resp.status_code == 200:
                return _profile_from_dict(resp.json())
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 获取画像", exc_info=True)
    db = _db(config)
    try:
        profiles = db.get_profiles(period=period, limit=1)
        return profiles[0] if profiles else None
    finally:
        db.close()


def generate_profile(config: dict, period: str = "weekly") -> Profile:
    """生成画像（API 后台任务优先，失败回退本地现算）"""
    if _use_api(config):
        try:
            base = _api_base(config)
            with httpx.Client(base_url=base, timeout=5.0) as client:
                resp = client.post("/api/v1/profile/refresh", params={"period": period})
                resp.raise_for_status()
                task_id = resp.json()["task_id"]
                for _ in range(120):  # 最多等待 60 秒
                    time.sleep(0.5)
                    status = client.get(f"/api/v1/profile/refresh/{task_id}").json()
                    if status["status"] == "done":
                        latest = client.get("/api/v1/profile/latest", params={"period": period})
                        latest.raise_for_status()
                        return _profile_from_dict(latest.json())
                    if status["status"] == "error":
                        raise RuntimeError(status.get("error") or "画像重建失败")
        except Exception:
            logger.warning("API 不可用，回退为本地同步生成画像", exc_info=True)
    db = _db(config)
    try:
        generator = ProfileGenerator(db, config.get("analysis", {}))
        return generator.generate(period=period, persist=True)
    finally:
        db.close()


@_ttl_cache(300)
def get_graph(config: dict, window_days: int = 90) -> dict:
    """获取兴趣共现图（后端预计算；5 分钟缓存，失败回退直连本地计算）"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/graph",
                params={"window_days": window_days},
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("API 不可用，回退本地计算兴趣图谱", exc_info=True)
    from datetime import timedelta
    from analysis.graph import build_interest_graph

    db = _db(config)
    try:
        since = datetime.now() - timedelta(days=window_days)
        events = db.get_events(since=since, limit=10000)
        return build_interest_graph(events)
    finally:
        db.close()


def start_profile_refresh(config: dict, period: str = "weekly") -> Optional[str]:
    """触发后台画像重建，返回 task_id；API 不可用时返回 None（由调用方回退同步生成）"""
    if _use_api(config):
        try:
            resp = httpx.post(
                f"{_api_base(config)}/api/v1/profile/refresh",
                params={"period": period},
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json().get("task_id")
        except Exception:
            logger.warning("API 不可用，报告将回退为本地同步生成", exc_info=True)
    return None


def get_task_status(config: dict, task_id: str) -> Optional[dict]:
    """查询画像重建任务状态；API 不可用时返回 None"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/profile/refresh/{task_id}",
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("查询任务状态失败", exc_info=True)
    return None
