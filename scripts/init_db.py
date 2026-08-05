"""初始化数据库"""

import logging
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import Database, database_url
from core.utils import load_config, setup_logging
from scripts.migrate import run_migrations

logger = logging.getLogger("init_db")


def main():
    """初始化数据库"""
    setup_logging()
    logger.info("🔧 初始化数据库...")

    # 加载配置
    config = load_config()
    db_url = database_url(config)

    # 创建数据库
    db = Database(db_url)
    db.init_tables()
    applied = run_migrations(db=db)
    if applied:
        logger.info("🔁 已应用迁移: %s", ", ".join(applied))

    logger.info("✅ 数据库已初始化: %s", db_url)
    logger.info("👤 当前用户数: %d", len(db.list_users()))

    db.close()


if __name__ == "__main__":
    main()
