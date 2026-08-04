"""数据同步脚本"""

import logging
import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import Database
from core.plugin_loader import PluginManager
from core.utils import load_config, setup_logging

logger = logging.getLogger("sync")


def sync_source(db: Database, plugin_manager: PluginManager, source_name: str):
    """同步单个数据源"""
    logger.info("🔄 同步数据源: %s", source_name)

    try:
        plugin = plugin_manager.load(source_name)
    except KeyError:
        logger.error("❌ 插件 %s 未找到", source_name)
        return

    # 检查连接
    logger.info("  📡 测试连接...")
    if not plugin.test_connection():
        logger.error("  ❌ 连接失败，请检查配置")
        return
    logger.info("  ✅ 连接成功")

    # 获取上次同步时间
    last_sync = db.get_last_sync(source_name)
    if last_sync is None:
        # 首次同步，拉取最近 30 天
        since = datetime.now() - timedelta(days=30)
        logger.info("  📅 首次同步，拉取最近 30 天数据")
    else:
        since = last_sync
        logger.info("  📅 从 %s 开始同步", since.strftime("%Y-%m-%d %H:%M"))

    # 拉取数据
    logger.info("  📥 拉取数据...")
    try:
        events = plugin.fetch(since)
        logger.info("  📦 获取到 %d 条数据", len(events))
    except Exception as e:
        logger.error("  ❌ 拉取失败: %s", e)
        return

    # 存入数据库
    if events:
        count = db.insert_events(events)
        logger.info("  💾 新增 %d 条数据", count)

        # 更新同步状态
        last_event_id = events[0].id if events else None
        db.update_sync_state(source_name, last_event_id, count)
        logger.info("  ✅ 同步完成")
    else:
        logger.info("  ℹ️ 无新数据")


def sync_all(db: Database, plugin_manager: PluginManager):
    """同步所有已启用的数据源"""
    logger.info("🔄 同步所有数据源...")

    enabled_plugins = plugin_manager.get_enabled_plugins()
    if not enabled_plugins:
        logger.error("❌ 没有已启用的数据源")
        return

    logger.info("📦 找到 %d 个已启用的数据源", len(enabled_plugins))

    for plugin in enabled_plugins:
        sync_source(db, plugin_manager, plugin.name)

    logger.info("✅ 所有同步完成")


def main():
    parser = argparse.ArgumentParser(description="数据同步工具")
    parser.add_argument(
        "--source",
        type=str,
        help="指定同步的数据源（不指定则同步所有）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="守护进程模式（定时同步）",
    )

    args = parser.parse_args()

    setup_logging()

    # 加载配置
    config = load_config(args.config)

    # 初始化数据库
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]

    db = Database(db_path)
    db.init_tables()

    # 加载插件
    plugin_manager = PluginManager(config["system"]["plugins_dir"], config)
    discovered = plugin_manager.discover()
    logger.info("📦 发现插件: %s", discovered)

    if args.daemon:
        # 守护进程模式
        import time
        interval = 3600  # 1 小时
        logger.info("🔄 守护进程模式，每 %d 秒同步一次", interval)
        while True:
            sync_all(db, plugin_manager)
            time.sleep(interval)
    elif args.source:
        # 同步单个数据源
        sync_source(db, plugin_manager, args.source)
    else:
        # 同步所有
        sync_all(db, plugin_manager)

    db.close()


if __name__ == "__main__":
    main()
