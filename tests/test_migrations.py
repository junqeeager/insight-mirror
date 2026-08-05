"""schema 迁移测试（离线）。"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text  # noqa: E402

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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 迁移测试通过！")
