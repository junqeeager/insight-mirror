"""个人认知画像系统 - 主入口"""

import logging
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from core.database import Database, database_url
from core.plugin_loader import PluginManager
from core.utils import load_config, setup_logging

logger = logging.getLogger("main")


def main():
    """主函数"""
    setup_logging()
    logger.info("🧠 个人认知画像系统")
    logger.info("=" * 50)

    # 1. 加载配置
    logger.info("📄 加载配置...")
    config = load_config()
    logger.info("  ✅ 配置已加载")

    # 2. 初始化数据库
    logger.info("🗄️ 初始化数据库...")
    db_url = database_url(config)
    db = Database(db_url)
    db.init_tables()
    logger.info("  ✅ 数据库已初始化: %s", db_url)

    # 3. 加载插件
    logger.info("🔌 加载插件...")
    plugin_manager = PluginManager(config["system"]["plugins_dir"], config)
    discovered = plugin_manager.discover()
    logger.info("  ✅ 发现插件: %s", discovered)

    # 4. 显示统计
    admin = next((u for u in db.list_users() if u["role"] == "admin"), None)
    if admin:
        stats = db.get_stats(admin["id"])
        logger.info("📊 数据库统计（管理员 %s）:", admin["username"])
        logger.info("  总事件数: %d", stats["total"])
        for source, count in stats.get("by_source", {}).items():
            logger.info("  - %s: %d 条", source, count)
    else:
        logger.info("⚠️ 暂无用户，请先运行: python scripts/manage_users.py create-admin")

    # 5. 显示已启用的数据源
    logger.info("📦 已启用的数据源:")
    for plugin in plugin_manager.get_enabled_plugins():
        logger.info("  - %s %s", plugin.icon, plugin.display_name)

    db.close()
    logger.info("✅ 系统就绪！")
    logger.info("下一步:")
    logger.info("  1. 配置数据源: 编辑 config.yaml")
    logger.info("  2. 同步数据: python scripts/sync.py")
    logger.info("  3. 生成报告: python scripts/generate_report.py")
    logger.info("  4. 启动前端: streamlit run frontend/app.py")


if __name__ == "__main__":
    main()
