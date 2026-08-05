"""schema 迁移测试（离线）。"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from core.database import Database  # noqa: E402
from scripts.migrate import run_migrations  # noqa: E402


def _legacy_db() -> Database:
    db = Database(":memory:")
    db.init_tables()
    uid = db.create_user("legacy-user", "x" * 60, role="user", status="active")
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO topics (id, user_id, name, category, frequency) "
                "VALUES ('topic-Python', :uid, 'Python', 'general', 5)"
            ),
            {"uid": uid},
        )
        conn.execute(
            text(
                "INSERT INTO topics (id, user_id, name, category, frequency) "
                "VALUES ('topic-实战', :uid, '实战', 'cluster_1', 3)"
            ),
            {"uid": uid},
        )
        conn.execute(
            text(
                "INSERT INTO event_topics (event_id, topic_id, user_id, relevance) "
                "VALUES ('ev-1', 'topic-Python', :uid, 0.8)"
            ),
            {"uid": uid},
        )
    return db


def test_migration_namespaces_legacy_topic_ids():
    db = _legacy_db()
    try:
        applied = run_migrations(db=db)
        assert "001_namespace_topic_ids" in applied

        with db.engine.connect() as conn:
            ids = {
                row[0]
                for row in conn.execute(text("SELECT id FROM topics"))
            }
        assert "topic-general-Python" in ids
        assert "topic-cluster-cluster_1-实战" in ids
        assert "topic-Python" not in ids
        assert "topic-实战" not in ids

        with db.engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT topic_id FROM event_topics "
                    "WHERE event_id='ev-1'"
                )
            ).mappings().one()
        assert row["topic_id"] == "topic-general-Python"
    finally:
        db.close()


def test_migrations_idempotent_on_fresh_and_migrated_db():
    db = _legacy_db()
    try:
        run_migrations(db=db)
        second = run_migrations(db=db)
        assert second == [], "重复执行不应再应用迁移"

        fresh = Database(":memory:")
        try:
            fresh.init_tables()
            first = run_migrations(db=fresh)
            assert "001_namespace_topic_ids" in first
            assert run_migrations(db=fresh) == []
        finally:
            fresh.close()
    finally:
        db.close()


def test_migration_002_dedupes_running_tasks_and_creates_index():
    db = Database(":memory:")
    try:
        # 模拟旧库：tasks 表无 idx_tasks_running 索引，且存在重复 running 任务
        with db.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE tasks ("
                    "  id VARCHAR PRIMARY KEY,"
                    "  user_id VARCHAR NOT NULL,"
                    "  kind VARCHAR NOT NULL,"
                    "  status VARCHAR NOT NULL,"
                    "  params JSON,"
                    "  result JSON,"
                    "  error TEXT,"
                    "  created_at DATETIME NOT NULL,"
                    "  finished_at DATETIME"
                    ")"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO tasks (id, user_id, kind, status, created_at) VALUES "
                    "('dup-1', 'u1', 'sync', 'running', '2026-08-01 10:00:00'), "
                    "('dup-2', 'u1', 'sync', 'running', '2026-08-02 10:00:00')"
                )
            )

        applied = run_migrations(db=db)
        assert "002_task_running_unique" in applied

        with db.engine.connect() as conn:
            running = [
                row[0]
                for row in conn.execute(
                    text("SELECT id FROM tasks WHERE status = 'running'")
                )
            ]
            idx = conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'index' AND name = 'idx_tasks_running'"
                )
            ).first()
        assert running == ["dup-2"], "应保留最新一条 running 任务"
        assert idx is not None, "应创建 running 任务部分唯一索引"

        # 索引生效：同一 user_id/kind 再次 running 插入应失败
        try:
            with db.engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO tasks (id, user_id, kind, status, created_at) "
                        "VALUES ('dup-3', 'u1', 'sync', 'running', '2026-08-03 10:00:00')"
                    )
                )
            raise AssertionError("重复 running 任务应被唯一索引拒绝")
        except IntegrityError:
            pass
    finally:
        db.close()


def test_migration_003_creates_oauth_flows_and_cleanup():
    db = Database(":memory:")
    try:
        db.init_tables()
        # 模拟旧库：先删除新表，再通过迁移重建
        with db.engine.begin() as conn:
            conn.execute(text("DROP TABLE oauth_flows"))

        applied = run_migrations(db=db)
        assert "003_oauth_flows" in applied

        db.save_oauth_flow(
            "u1",
            "state-1",
            "verifier-1",
            datetime.now() + timedelta(minutes=5),
        )
        db.save_oauth_flow(
            "u1",
            "state-expired",
            "verifier-2",
            datetime.now() - timedelta(minutes=1),
        )
        assert db.cleanup_expired_oauth_flows() == 1

        flow = db.consume_oauth_flow("u1", "state-1")
        assert flow is not None
        assert flow["code_verifier"] == "verifier-1"
        assert db.consume_oauth_flow("u1", "state-1") is None

        # 其他用户不能消费别人的 state
        db.save_oauth_flow(
            "u2",
            "state-1",
            "verifier-3",
            datetime.now() + timedelta(minutes=5),
        )
        assert db.consume_oauth_flow("u1", "state-1") is None
        assert db.consume_oauth_flow("u2", "state-1") is not None
    finally:
        db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 迁移测试通过！")
