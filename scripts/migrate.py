"""轻量 schema 迁移工具（SQLite / PostgreSQL 通用）。"""

import argparse
import importlib.util
import logging
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.database import Database, database_url, schema_migrations  # noqa: E402
from core.utils import load_config, setup_logging  # noqa: E402

logger = logging.getLogger("migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _discover_migrations() -> list:
    """返回 (version, module_path) 列表，按文件名排序。"""
    found = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        found.append((path.stem, path))
    return found


def _load_module(version: str, path: Path):
    spec = importlib.util.spec_from_file_location(f"migration_{version}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations(db: Database = None, db_url: str = None) -> list:
    """执行未应用的迁移，返回已应用版本列表。"""
    config = load_config()
    own_db = db is None
    if own_db:
        db = Database(db_url or database_url(config))
    try:
        db.init_tables()
        schema_migrations.create(db.engine, checkfirst=True)

        with db.engine.connect() as conn:
            applied = {
                row[0]
                for row in conn.execute(
                    schema_migrations.select().order_by(schema_migrations.c.version)
                )
            }

        newly_applied = []
        for version, path in _discover_migrations():
            if version in applied:
                continue
            logger.info("应用迁移: %s", version)
            module = _load_module(version, path)
            module.upgrade(db)
            with db.engine.begin() as conn:
                conn.execute(schema_migrations.insert().values(version=version))
            newly_applied.append(version)
        return newly_applied
    finally:
        if own_db:
            db.close()


def main():
    parser = argparse.ArgumentParser(description="schema 迁移工具")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    parser.add_argument("--url", type=str, help="数据库 URL（默认读配置）")
    args = parser.parse_args()

    setup_logging()
    applied = run_migrations(db_url=args.url)
    if applied:
        logger.info("✅ 已应用迁移: %s", ", ".join(applied))
    else:
        logger.info("数据库已是最新 schema")


if __name__ == "__main__":
    main()
