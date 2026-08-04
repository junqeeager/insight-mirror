"""数据库迁移脚本：跨后端幂等拷贝（SQLite ↔ PostgreSQL）"""

import argparse
import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import func, select  # noqa: E402

from core.database import (  # noqa: E402
    Database,
    dialect_insert,
    event_topics,
    events,
    profiles,
    sync_state,
    topics,
)

_TABLE_ORDER = [events, topics, event_topics, profiles, sync_state]


def copy_table(src: Database, dst: Database, table) -> int:
    """把一张表从源库拷贝到目标库（主键冲突跳过，可重复执行）。"""
    with src.engine.connect() as conn:
        rows = conn.execute(select(table)).mappings().all()
    if not rows:
        return 0
    stmt = dialect_insert(table, dst.dialect).on_conflict_do_nothing()
    values = [dict(row) for row in rows]
    with dst.engine.begin() as conn:
        before = conn.execute(select(func.count()).select_from(table)).scalar_one()
        conn.execute(stmt, values)
        after = conn.execute(select(func.count()).select_from(table)).scalar_one()
    return after - before


def main():
    parser = argparse.ArgumentParser(
        description="跨后端幂等拷贝数据库（SQLite ↔ PostgreSQL）"
    )
    parser.add_argument(
        "--from-url",
        required=True,
        help="源数据库 URL，如 sqlite:///./data/profile.db",
    )
    parser.add_argument(
        "--to-url",
        required=True,
        help="目标数据库 URL，如 postgresql+psycopg://user:pass@host:5432/dbname",
    )
    args = parser.parse_args()

    src = Database(args.from_url)
    dst = Database(args.to_url)
    dst.init_tables()
    try:
        for table in _TABLE_ORDER:
            copied = copy_table(src, dst, table)
            print(f"{table.name}: 拷贝 {copied} 条")
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
