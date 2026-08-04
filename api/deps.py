"""FastAPI 依赖"""

import os

from core.database import Database, database_url
from core.utils import load_config

_CONFIG_CACHE: dict = {}


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


def get_db():
    """每个请求独立连接池实例，避免跨线程复用同一连接"""
    db = Database(get_db_url(get_config()))
    db.init_tables()
    try:
        yield db
    finally:
        db.close()
