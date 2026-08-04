"""数据访问层：优先调用 FastAPI，失败时回退直连 SQLite"""

import time
from datetime import datetime
from typing import List, Optional

import httpx

from core.models import Depth, Event, EventType, Profile, Topic
from core.database import Database
from analysis.profile import ProfileGenerator

_API_TIMEOUT = 3.0


def _use_api(config: dict) -> bool:
    return config.get("frontend", {}).get("use_api", True)


def _api_base(config: dict) -> str:
    return config.get("frontend", {}).get("api_base", "http://localhost:8502").rstrip("/")


def _db(config: dict) -> Database:
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]
    return Database(db_path)


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
            pass
    db = _db(config)
    try:
        return db.get_events(source=source, event_type=event_type, since=since, limit=limit)
    finally:
        db.close()


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
            pass
    db = _db(config)
    try:
        return db.get_topics(category=category, limit=limit)
    finally:
        db.close()


def get_stats(config: dict) -> dict:
    """查询统计（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            resp = httpx.get(f"{_api_base(config)}/api/v1/stats", timeout=_API_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            pass
    db = _db(config)
    try:
        return db.get_stats()
    finally:
        db.close()


def get_latest_profile(config: dict, period: str = "weekly") -> Optional[Profile]:
    """获取最近画像快照（不现场计算）"""
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
            pass
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
            pass
    db = _db(config)
    try:
        generator = ProfileGenerator(db, config.get("analysis", {}))
        return generator.generate(period=period, persist=True)
    finally:
        db.close()
