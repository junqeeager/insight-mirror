"""FastAPI 依赖"""

import os

from core.database import Database
from core.utils import load_config

_CONFIG_CACHE: dict = {}


def get_config() -> dict:
    """加载配置（进程内缓存）"""
    if "config" not in _CONFIG_CACHE:
        _CONFIG_CACHE["config"] = load_config()
    return _CONFIG_CACHE["config"]


def get_db_path(config: dict) -> str:
    """解析数据库路径，支持 PROFILE_DB_PATH 环境变量覆盖（测试用）"""
    env_path = os.environ.get("PROFILE_DB_PATH")
    if env_path:
        return env_path
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]
    return db_path


def get_db():
    """每个请求独立连接，避免 sqlite 连接跨线程复用"""
    db = Database(get_db_path(get_config()))
    db.init_tables()
    try:
        yield db
    finally:
        db.close()
