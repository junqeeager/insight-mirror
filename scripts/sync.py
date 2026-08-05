"""数据同步脚本（按用户同步各自的数据源）"""

import logging
import sys
import argparse
from pathlib import Path
from typing import Optional

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import Database, database_url
from core.sync_service import sync_all_users, sync_user
from core.utils import load_config, setup_logging

logger = logging.getLogger("sync")


def _resolve_user(db: Database, username: Optional[str]) -> Optional[dict]:
    """按用户名解析用户；未指定时返回 None。"""
    if not username:
        return None
    user = db.get_user_by_username(username.strip())
    if not user:
        logger.error("❌ 用户 %s 不存在", username)
    return user


def main():
    parser = argparse.ArgumentParser(description="数据同步工具")
    parser.add_argument(
        "--source",
        type=str,
        help="指定同步的数据源（不指定则同步所有）",
    )
    parser.add_argument(
        "--user",
        type=str,
        help="指定同步的用户名（不指定则同步所有 active 用户）",
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
    db_url = database_url(config)
    db = Database(db_url)
    db.init_tables()

    if args.daemon:
        import time

        interval = 3600  # 1 小时
        logger.info("🔄 守护进程模式，每 %d 秒同步一次（遍历所有 active 用户）", interval)
        while True:
            sync_all_users(db, config)
            time.sleep(interval)
    else:
        if args.user:
            user = _resolve_user(db, args.user)
            if not user:
                return 1
            results = sync_user(db, config, user["id"], source=args.source)
        else:
            results = sync_all_users(db, config)
        for user_id, sources in results.items():
            for source_name, info in sources.items():
                if "error" in info:
                    logger.error("  ❌ %s: %s", source_name, info["error"])
                else:
                    logger.info("  ✅ %s: 新增 %d 条", source_name, info.get("count", 0))

    db.close()


if __name__ == "__main__":
    main()
