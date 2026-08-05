"""FastAPI 依赖"""

import os
import threading

from fastapi import Depends, Header, HTTPException

from core.auth import hash_token
from core.database import Database, database_url
from core.utils import load_config

_CONFIG_CACHE: dict = {}
_INITIALIZED_URLS: set = set()
_INIT_LOCK = threading.Lock()


def get_config() -> dict:
    """加载配置（进程内缓存）"""
    if "config" not in _CONFIG_CACHE:
        _CONFIG_CACHE["config"] = load_config()
    return _CONFIG_CACHE["config"]


def get_db_url(config: dict) -> str:
    """解析数据库 URL；PROFILE_DB_PATH 仅保留测试兼容。"""
    legacy_path = os.environ.get("PROFILE_DB_PATH")
    if legacy_path:
        return legacy_path
    return database_url(config)


def ensure_initialized(db: Database) -> None:
    """确保建表只执行一次（进程内按 URL 去重）。"""
    with _INIT_LOCK:
        if db.db_url not in _INITIALIZED_URLS:
            db.init_tables()
            _INITIALIZED_URLS.add(db.db_url)


def get_db():
    """每个请求使用共享 engine 的连接，建表只执行一次。"""
    db = Database(get_db_url(get_config()))
    ensure_initialized(db)
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    authorization: str = Header(default=""),
    db: Database = Depends(get_db),
) -> dict:
    """从 Bearer token 解析当前登录用户（无效/过期/未启用均拒绝）。"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token_hash = hash_token(authorization[len("Bearer "):].strip())
    user = db.get_session_user(token_hash)
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """仅允许 admin 角色访问。"""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
