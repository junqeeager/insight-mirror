"""按用户执行数据源同步（脚本与 API 后台任务共用）。"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from core.auth import decrypt_config
from core.database import Database
from core.plugin_loader import PluginManager

logger = logging.getLogger("sync_service")


def build_user_sources(source_configs: List[dict]) -> dict:
    """把数据库中的用户数据源配置转为 PluginManager 认识的 sources 结构。"""
    sources = {}
    for row in source_configs:
        sources[row["source"]] = {
            "enabled": bool(row.get("enabled", False)),
            "config": decrypt_config(row.get("config") or {}),
        }
    return sources


def sync_source(
    db: Database,
    plugin_manager: PluginManager,
    source_name: str,
    user_id: str,
) -> dict:
    """同步单个数据源（按用户写入）。"""
    try:
        plugin = plugin_manager.load(source_name)
    except KeyError:
        logger.error("插件 %s 未找到", source_name)
        return {"source": source_name, "error": "插件未找到"}

    logger.info("用户 %s 同步数据源: %s", user_id, source_name)
    if not plugin.test_connection():
        logger.error("数据源 %s 连接失败", source_name)
        return {"source": source_name, "error": "连接失败"}

    last_sync = db.get_last_sync(user_id, source_name)
    since = (
        last_sync
        if last_sync is not None
        else datetime.now() - timedelta(days=30)
    )
    try:
        events = plugin.fetch(since)
    except Exception as exc:
        logger.error("数据源 %s 拉取失败: %s", source_name, exc)
        return {"source": source_name, "error": str(exc)}

    count = 0
    if events:
        count = db.insert_events(events, user_id)
        db.update_sync_state(user_id, source_name, events[0].id, count)
    return {"source": source_name, "count": count, "since": since.isoformat()}


def sync_user(
    db: Database,
    config: dict,
    user_id: str,
    source: Optional[str] = None,
) -> dict:
    """同步某个用户的全部（或指定）已启用数据源。"""
    rows = db.list_source_configs(user_id)
    sources = build_user_sources(rows)
    if source is not None:
        sources = {source: sources[source]} if source in sources else {}

    user_config = dict(config)
    user_config["sources"] = sources
    plugin_manager = PluginManager(config["system"]["plugins_dir"], user_config)
    plugin_manager.discover()

    results = {}
    for source_name, source_cfg in sources.items():
        if not source_cfg.get("enabled", False):
            continue
        results[source_name] = sync_source(db, plugin_manager, source_name, user_id)
    return results


def sync_all_users(db: Database, config: dict) -> dict:
    """同步所有 active 用户的数据源（daemon / CLI 全量模式）。"""
    results = {}
    for row in db.list_active_user_source_configs():
        user_id = row["user_id"]
        if user_id not in results:
            results[user_id] = {}
        source_name = row["source"]
        source_cfg = {"enabled": True, "config": decrypt_config(row.get("config") or {})}
        user_config = dict(config)
        user_config["sources"] = {source_name: source_cfg}
        plugin_manager = PluginManager(config["system"]["plugins_dir"], user_config)
        plugin_manager.discover()
        results[user_id][source_name] = sync_source(
            db, plugin_manager, source_name, user_id
        )
    return results
