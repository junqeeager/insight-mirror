"""数据访问层：优先调用 FastAPI，失败时回退直连 SQLite（带 TTL 缓存）"""

import functools
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import List, Optional

import httpx

from core.auth import decrypt_config, encrypt_config, mask_config
from core.models import Depth, Event, EventType, Profile, Topic
from core.database import Database, database_url
from analysis.profile import ProfileGenerator
from core.plugin_loader import PluginManager
from core.sync_service import sync_user

logger = logging.getLogger("frontend.data_access")

_API_TIMEOUT = 3.0

# 进程内 TTL 缓存：低流量个人项目足够，无需 Redis
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()

_SENSITIVE_KEYWORDS = ("cookie", "csrf", "token", "secret")


def _stable_config(config: dict, user: dict) -> tuple:
    """提取影响数据来源的配置指纹（含用户，防止串数据）。"""
    return (
        user.get("id", ""),
        config.get("frontend", {}).get("api_base", "http://localhost:8502"),
        config.get("frontend", {}).get("use_api", True),
        config.get("database", {}).get("url", "sqlite:///./data/profile.db"),
    )


def _ttl_cache(ttl_seconds: float):
    """按 (函数名, 配置指纹, 用户, 参数) 缓存结果，TTL 过期后重算"""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(config, user, *args, **kwargs):
            key = (
                fn.__name__,
                _stable_config(config, user),
                args,
                tuple(sorted((k, v) for k, v in kwargs.items() if v is not None)),
            )
            now = time.monotonic()
            with _CACHE_LOCK:
                hit = _CACHE.get(key)
                if hit is not None and now - hit[0] < ttl_seconds:
                    return hit[1]
            result = fn(config, user, *args, **kwargs)
            with _CACHE_LOCK:
                _CACHE[key] = (now, result)
            return result
        return wrapper
    return deco


def _use_api(config: dict) -> bool:
    return config.get("frontend", {}).get("use_api", True)


def _api_base(config: dict) -> str:
    return config.get("frontend", {}).get("api_base", "http://localhost:8502").rstrip("/")


def _headers(user: dict) -> dict:
    token = user.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _db(config: dict) -> Database:
    db = Database(database_url(config))
    db.init_tables()
    return db


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
    user: dict,
    source: Optional[str] = None,
    event_type: Optional[str] = None,
    since: Optional[datetime] = None,
    limit: int = 1000,
) -> List[Event]:
    """查询当前用户事件（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            params = {"limit": limit}
            if source:
                params["source"] = source
            if event_type:
                params["event_type"] = event_type
            if since:
                params["since"] = since.isoformat()
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/events",
                params=params,
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return [_event_from_dict(x) for x in resp.json()]
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 查询事件", exc_info=True)
    db = _db(config)
    try:
        return db.get_events(
            user_id=user["id"],
            source=source,
            event_type=event_type,
            since=since,
            limit=limit,
        )
    finally:
        db.close()


@_ttl_cache(30)
def get_topics(config: dict, user: dict, category: Optional[str] = None, limit: int = 50) -> List[Topic]:
    """查询当前用户主题（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            params = {"limit": limit}
            if category:
                params["category"] = category
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/topics",
                params=params,
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return [_topic_from_dict(x) for x in resp.json()]
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 查询主题", exc_info=True)
    db = _db(config)
    try:
        return db.get_topics(user_id=user["id"], category=category, limit=limit)
    finally:
        db.close()


@_ttl_cache(30)
def get_stats(config: dict, user: dict) -> dict:
    """查询当前用户统计（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/stats",
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 查询统计", exc_info=True)
    db = _db(config)
    try:
        return db.get_stats(user["id"])
    finally:
        db.close()


def get_latest_profile(
    config: dict,
    user: dict,
    period: str = "weekly",
    fresh: bool = False,
) -> Optional[Profile]:
    """获取当前用户最近画像快照（60s 缓存；fresh=True 时跳过缓存并刷新缓存）"""
    key = ("get_latest_profile", _stable_config(config, user), period)
    now = time.monotonic()
    if not fresh:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit and now - hit[0] < 60:
                return hit[1]
    profile = _fetch_latest_profile(config, user, period)
    if profile is not None:
        with _CACHE_LOCK:
            _CACHE[key] = (now, profile)
    return profile


def _fetch_latest_profile(config: dict, user: dict, period: str) -> Optional[Profile]:
    """实际获取最近画像快照（API 优先，失败回退直连）"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/profile/latest",
                params={"period": period},
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            if resp.status_code == 200:
                return _profile_from_dict(resp.json())
        except Exception:
            logger.warning("API 不可用，回退直连 SQLite 获取画像", exc_info=True)
    db = _db(config)
    try:
        profiles = db.get_profiles(user_id=user["id"], period=period, limit=1)
        return profiles[0] if profiles else None
    finally:
        db.close()


def generate_profile(config: dict, user: dict, period: str = "weekly") -> Profile:
    """生成当前用户画像（API 后台任务优先，失败回退本地现算）"""
    if _use_api(config):
        try:
            base = _api_base(config)
            with httpx.Client(base_url=base, timeout=5.0) as client:
                resp = client.post(
                    "/api/v1/profile/refresh",
                    params={"period": period},
                    headers=_headers(user),
                )
                resp.raise_for_status()
                task_id = resp.json()["task_id"]
                for _ in range(120):  # 最多等待 60 秒
                    time.sleep(0.5)
                    status = client.get(
                        f"/api/v1/profile/refresh/{task_id}",
                        headers=_headers(user),
                    ).json()
                    if status["status"] == "done":
                        latest = client.get(
                            "/api/v1/profile/latest",
                            params={"period": period},
                            headers=_headers(user),
                        )
                        latest.raise_for_status()
                        return _profile_from_dict(latest.json())
                    if status["status"] == "error":
                        raise RuntimeError(status.get("error") or "画像重建失败")
        except Exception:
            logger.warning("API 不可用，回退为本地同步生成画像", exc_info=True)
    db = _db(config)
    try:
        generator = ProfileGenerator(db, config.get("analysis", {}))
        return generator.generate(user_id=user["id"], period=period, persist=True)
    finally:
        db.close()


@_ttl_cache(300)
def get_graph(config: dict, user: dict, window_days: int = 90) -> dict:
    """获取当前用户兴趣共现图（后端预计算；5 分钟缓存，失败回退直连本地计算）"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/graph",
                params={"window_days": window_days},
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("API 不可用，回退本地计算兴趣图谱", exc_info=True)
    from analysis.graph import build_interest_graph

    db = _db(config)
    try:
        since = datetime.now() - timedelta(days=window_days)
        events = db.get_events(user_id=user["id"], since=since, limit=10000)
        return build_interest_graph(events)
    finally:
        db.close()


def start_profile_refresh(config: dict, user: dict, period: str = "weekly") -> Optional[str]:
    """触发当前用户后台画像重建，返回 task_id；API 不可用时返回 None"""
    if _use_api(config):
        try:
            resp = httpx.post(
                f"{_api_base(config)}/api/v1/profile/refresh",
                params={"period": period},
                headers=_headers(user),
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json().get("task_id")
        except Exception:
            logger.warning("API 不可用，报告将回退为本地同步生成", exc_info=True)
    return None


def get_task_status(config: dict, user: dict, task_id: str) -> Optional[dict]:
    """查询画像重建任务状态；API 不可用时返回 None"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/profile/refresh/{task_id}",
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("查询任务状态失败", exc_info=True)
    return None


# ---------- 用户数据源配置与同步 ----------


def get_my_sources(config: dict, user: dict) -> List[dict]:
    """返回当前用户的数据源配置（敏感字段已脱敏）。"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/sources",
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            out = []
            for item in resp.json():
                spec = config.get("sources", {}).get(item["source"], {})
                item["plugin"] = spec.get("plugin", item["source"])
                item["display_name"] = spec.get("display_name", item["source"])
                out.append(item)
            return out
        except Exception:
            logger.warning("API 不可用，回退直连读取数据源配置", exc_info=True)
    db = _db(config)
    try:
        out = []
        for source, spec in config.get("sources", {}).items():
            saved = db.get_source_config(user["id"], source)
            cfg = decrypt_config(saved.get("config") or {}) if saved else {}
            enabled = bool(saved.get("enabled", spec.get("enabled", False))) if saved else bool(spec.get("enabled", False))
            out.append(
                {
                    "source": source,
                    "plugin": spec.get("plugin", source),
                    "display_name": spec.get("display_name", source),
                    "enabled": enabled,
                    "config": mask_config(cfg),
                    "has_secrets": {
                        k: bool(v)
                        for k, v in cfg.items()
                        if any(kw in k.lower() for kw in _SENSITIVE_KEYWORDS)
                    },
                }
            )
        return out
    finally:
        db.close()


def save_source_config(
    config: dict,
    user: dict,
    source: str,
    fields: dict,
    enabled: bool,
) -> dict:
    """保存数据源配置；敏感字段留空或 *** 时保持不变。"""
    if _use_api(config):
        try:
            resp = httpx.put(
                f"{_api_base(config)}/api/v1/sources/{source}",
                json={"source": source, "config": fields, "enabled": enabled},
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("API 不可用，回退直连保存数据源配置", exc_info=True)
    db = _db(config)
    try:
        saved = db.get_source_config(user["id"], source)
        existing = decrypt_config(saved.get("config") or {}) if saved else {}
        merged = dict(existing)
        for key, value in fields.items():
            if any(kw in key.lower() for kw in _SENSITIVE_KEYWORDS):
                if value in ("", "***") and key in merged:
                    continue
                merged[key] = value
            else:
                merged[key] = value
        db.set_source_config(user["id"], source, encrypt_config(merged), enabled)
        decrypted = decrypt_config(merged)
        return {
            "source": source,
            "enabled": enabled,
            "config": mask_config(decrypted),
            "has_secrets": {
                k: bool(v)
                for k, v in decrypted.items()
                if any(kw in k.lower() for kw in _SENSITIVE_KEYWORDS)
            },
        }
    finally:
        db.close()


def test_source_connection(config: dict, user: dict, source: str) -> dict:
    """测试当前用户该数据源配置。"""
    if _use_api(config):
        try:
            resp = httpx.post(
                f"{_api_base(config)}/api/v1/sources/{source}/test",
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            logger.warning("API 不可用，回退本地测试连接", exc_info=True)
    db = _db(config)
    try:
        saved = db.get_source_config(user["id"], source)
        cfg = decrypt_config(saved.get("config") or {}) if saved else {}
        user_config = dict(config)
        user_config["sources"] = {source: {"enabled": True, "config": cfg}}
        manager = PluginManager(config["system"]["plugins_dir"], user_config)
        manager.discover()
        plugin = manager.load(source)
        ok = plugin.test_connection()
        return {"ok": ok, "message": "连接成功" if ok else "连接失败，请检查配置"}
    except KeyError:
        return {"ok": False, "message": "插件未找到"}
    finally:
        db.close()


def start_sync(config: dict, user: dict, source: Optional[str] = None) -> Optional[str]:
    """触发当前用户后台同步，返回 task_id；API 不可用时返回 None"""
    if _use_api(config):
        try:
            resp = httpx.post(
                f"{_api_base(config)}/api/v1/sync",
                json={"source": source} if source else {},
                headers=_headers(user),
                timeout=5.0,
            )
            resp.raise_for_status()
            return resp.json().get("task_id")
        except Exception:
            logger.warning("API 不可用，回退为本地同步", exc_info=True)
    return None


def get_sync_status(config: dict, user: dict, task_id: str) -> Optional[dict]:
    """查询同步任务状态；API 不可用时返回 None"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/sync/{task_id}",
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("查询同步任务状态失败", exc_info=True)
    return None


def run_sync_direct(config: dict, user: dict, source: Optional[str] = None) -> dict:
    """API 不可用时在当前进程内同步（阻塞）。"""
    db = _db(config)
    try:
        return sync_user(db, config, user["id"], source=source)
    finally:
        db.close()


# ---------- 管理员 ----------


def admin_list_users(config: dict, user: dict) -> List[dict]:
    """管理员列出全部用户。"""
    if _use_api(config):
        try:
            resp = httpx.get(
                f"{_api_base(config)}/api/v1/admin/users",
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            logger.warning("API 不可用，回退直连列出用户", exc_info=True)
    db = _db(config)
    try:
        users = db.list_users()
        return [
            {
                "id": u["id"],
                "username": u["username"],
                "role": u["role"],
                "status": u["status"],
                "created_at": u.get("created_at"),
                "last_login_at": u.get("last_login_at"),
            }
            for u in users
        ]
    finally:
        db.close()


def admin_update_user(
    config: dict,
    user: dict,
    target_id: str,
    status: Optional[str] = None,
    password: Optional[str] = None,
) -> dict:
    """管理员更新用户状态/密码。"""
    if _use_api(config):
        try:
            body = {}
            if status:
                body["status"] = status
            if password:
                body["password"] = password
            resp = httpx.patch(
                f"{_api_base(config)}/api/v1/admin/users/{target_id}",
                json=body,
                headers=_headers(user),
                timeout=_API_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
    from core.auth import hash_password

    db = _db(config)
    try:
        if status:
            db.update_user_status(target_id, status)
        if password:
            db.update_user_password(target_id, hash_password(password))
        return db.get_user_by_id(target_id)
    finally:
        db.close()
