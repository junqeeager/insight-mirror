"""按用户执行数据源同步（脚本与 API 后台任务共用）。"""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Callable, List, Optional

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
        detail = getattr(plugin, "last_error", "") or "连接失败"
        logger.error("数据源 %s 连接失败: %s", source_name, detail)
        return {"source": source_name, "error": detail}

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
    on_source_done: Optional[Callable[[str, dict], None]] = None,
) -> dict:
    """同步某个用户的全部（或指定）已启用数据源。"""
    rows = db.list_source_configs(user_id)
    sources = build_user_sources(rows)
    global_sources = config.get("sources", {})
    for name, source_cfg in sources.items():
        global_cfg = dict(global_sources.get(name, {}).get("config", {}) or {})
        global_cfg.update(source_cfg.get("config", {}))
        sources[name] = {**source_cfg, "config": global_cfg}
    if source is not None:
        sources = {source: sources[source]} if source in sources else {}

    user_config = dict(config)
    user_config["sources"] = sources
    plugin_manager = PluginManager(config["system"]["plugins_dir"], user_config)
    plugin_manager.discover()

    enabled = {
        name: source_cfg
        for name, source_cfg in sources.items()
        if source_cfg.get("enabled", False)
    }
    results = {}

    def _run_one(name: str) -> tuple:
        return name, sync_source(db, plugin_manager, name, user_id)

    if len(enabled) <= 1:
        for name in enabled:
            name, result = _run_one(name)
            results[name] = result
            if on_source_done:
                on_source_done(name, result)
        return results

    with ThreadPoolExecutor(
        max_workers=min(4, len(enabled)),
        thread_name_prefix="sync-source",
    ) as pool:
        futures = {pool.submit(_run_one, name): name for name in enabled}
        for future in as_completed(futures):
            name = futures[future]
            try:
                _, result = future.result()
            except Exception as exc:
                result = {"source": name, "error": str(exc)}
            results[name] = result
            if on_source_done:
                on_source_done(name, result)
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
        global_cfg = dict(
            config.get("sources", {}).get(source_name, {}).get("config", {}) or {}
        )
        global_cfg.update(source_cfg["config"])
        source_cfg["config"] = global_cfg
        user_config = dict(config)
        user_config["sources"] = {source_name: source_cfg}
        plugin_manager = PluginManager(config["system"]["plugins_dir"], user_config)
        plugin_manager.discover()
        results[user_id][source_name] = sync_source(
            db, plugin_manager, source_name, user_id
        )
    return results
