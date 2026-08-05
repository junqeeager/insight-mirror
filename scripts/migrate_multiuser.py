"""多用户迁移：给旧库增加 user_id，并把现有数据归入管理员。"""

import argparse
import getpass
import os
import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import inspect  # noqa: E402

from core.auth import encrypt_config, hash_password  # noqa: E402
from core.database import Database, database_url  # noqa: E402
from core.utils import load_config  # noqa: E402

_DATA_TABLES = {
    "events": "id, user_id",
    "topics": "id, user_id",
    "event_topics": "event_id, topic_id, user_id",
    "profiles": "id, user_id",
    "sync_state": "user_id, source",
}

_SQLITE_INDEXES = [
    "idx_events_timestamp",
    "idx_events_source",
    "idx_events_type",
    "idx_events_processed",
    "idx_topics_category",
    "idx_event_topics_topic",
    "idx_profiles_period",
]


def _already_migrated(db: Database) -> bool:
    insp = inspect(db.engine)
    tables = set(insp.get_table_names())
    if "users" not in tables or "events" not in tables:
        return False
    columns = {c["name"] for c in insp.get_columns("events")}
    return "user_id" in columns


def _ensure_admin(db: Database, username: str, password: str) -> str:
    user = db.get_user_by_username(username)
    if user:
        return user["id"]
    if not password:
        password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        password = getpass.getpass("请输入管理员密码（至少 8 位）: ")
    if len(password) < 8:
        raise SystemExit("❌ 管理员密码至少 8 位")
    return db.create_user(username, hash_password(password), role="admin", status="active")


def _seed_admin_sources(db: Database, admin_id: str, config: dict) -> None:
    if db.list_source_configs(admin_id) or not config.get("sources"):
        return
    for name, source_cfg in config.get("sources", {}).items():
        db.set_source_config(
            admin_id,
            name,
            encrypt_config(source_cfg.get("config") or {}),
            enabled=bool(source_cfg.get("enabled", False)),
        )


def _migrate_sqlite(db: Database, admin_id: str) -> None:
    insp = inspect(db.engine)
    existing = set(insp.get_table_names())
    with db.engine.begin() as conn:
        for index_name in _SQLITE_INDEXES:
            conn.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")
        for table in _DATA_TABLES:
            if table in existing:
                conn.exec_driver_sql(f"ALTER TABLE {table} RENAME TO {table}_legacy")

    from core.database import metadata

    metadata.create_all(db.engine)

    with db.engine.begin() as conn:
        if "events_legacy" in set(inspect(db.engine).get_table_names()):
            conn.exec_driver_sql(
                f"""INSERT INTO events
                    (id, user_id, timestamp, source, event_type, title, url, description,
                     tags, duration, progress, depth, metadata, processed, created_at)
                    SELECT id, '{admin_id}', timestamp, source, event_type, title, url, description,
                           tags, duration, progress, depth, metadata, processed, created_at
                    FROM events_legacy"""
            )
        if "topics_legacy" in set(inspect(db.engine).get_table_names()):
            conn.exec_driver_sql(
                f"""INSERT INTO topics
                    (id, user_id, name, category, frequency, weight, first_seen, last_seen, related_topics)
                    SELECT id, '{admin_id}', name, category, frequency, weight, first_seen, last_seen, related_topics
                    FROM topics_legacy"""
            )
        if "event_topics_legacy" in set(inspect(db.engine).get_table_names()):
            conn.exec_driver_sql(
                f"""INSERT INTO event_topics (event_id, topic_id, user_id, relevance)
                    SELECT event_id, topic_id, '{admin_id}', relevance FROM event_topics_legacy"""
            )
        if "profiles_legacy" in set(inspect(db.engine).get_table_names()):
            conn.exec_driver_sql(
                f"""INSERT INTO profiles (id, user_id, timestamp, period, data, created_at)
                    SELECT id, '{admin_id}', timestamp, period, data, created_at FROM profiles_legacy"""
            )
        if "sync_state_legacy" in set(inspect(db.engine).get_table_names()):
            conn.exec_driver_sql(
                f"""INSERT INTO sync_state
                    (user_id, source, last_sync, last_event_id, total_synced, config)
                    SELECT '{admin_id}', source, last_sync, last_event_id, total_synced, config
                    FROM sync_state_legacy"""
            )
        for table in _DATA_TABLES:
            conn.exec_driver_sql(f"DROP TABLE IF EXISTS {table}_legacy")


def _migrate_postgres(db: Database, admin_id: str) -> None:
    from core.database import metadata

    metadata.create_all(db.engine)
    insp = inspect(db.engine)
    existing = set(insp.get_table_names())
    with db.engine.begin() as conn:
        for table, pk_cols in _DATA_TABLES.items():
            if table not in existing:
                continue
            columns = {c["name"] for c in insp.get_columns(table)}
            if "user_id" not in columns:
                conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN user_id VARCHAR")
            conn.exec_driver_sql(
                f"UPDATE {table} SET user_id = '{admin_id}' WHERE user_id IS NULL"
            )
            conn.exec_driver_sql(f"ALTER TABLE {table} ALTER COLUMN user_id SET NOT NULL")
            pk_name = conn.exec_driver_sql(
                f"""SELECT conname FROM pg_constraint
                    WHERE conrelid = '{table}'::regclass AND contype = 'p'"""
            ).scalar()
            if pk_name:
                conn.exec_driver_sql(f"ALTER TABLE {table} DROP CONSTRAINT {pk_name}")
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD PRIMARY KEY ({pk_cols})")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_events_user ON events (user_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_topics_user ON topics (user_id)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_profiles_user ON profiles (user_id, period, timestamp)")
        conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS idx_event_topics_user ON event_topics (user_id)")


def migrate(
    db: Database,
    admin_username: str = "admin",
    admin_password: str = "",
    config: dict = None,
) -> dict:
    """执行迁移；已迁移时直接返回。"""
    if _already_migrated(db):
        return {"migrated": False, "reason": "already_migrated"}
    db.init_tables()
    admin_id = _ensure_admin(db, admin_username.strip().lower(), admin_password)
    if db.dialect == "sqlite":
        _migrate_sqlite(db, admin_id)
    else:
        _migrate_postgres(db, admin_id)
    if config:
        _seed_admin_sources(db, admin_id, config)
    return {"migrated": True, "admin_id": admin_id}


def main():
    parser = argparse.ArgumentParser(description="把旧版单用户数据库迁移为多用户结构")
    parser.add_argument("--config", type=str, default="config.yaml")
    parser.add_argument("--admin-username", default="admin")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    config = load_config(args.config)
    db = Database(database_url(config))
    db.init_tables()
    try:
        result = migrate(db, args.admin_username, args.password, config=config)
        if result.get("migrated"):
            print("✅ 迁移完成，现有数据已归入管理员")
        else:
            print("ℹ️ 无需迁移：数据库已是多用户结构")
    finally:
        db.close()


if __name__ == "__main__":
    main()
