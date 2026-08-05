"""数据库双后端测试（SQLite 内存库 + PostgreSQL 方言/真库）"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from core.database import Database, dialect_insert, events, metadata  # noqa: E402
from core.models import Depth, Event, EventType, Profile, Topic  # noqa: E402


def _make_event(i: int, dt: datetime, title: str = "Python 编程 教程", tags=("编程",)):
    return Event(
        id=f"ev-{i}",
        timestamp=dt,
        source="test",
        event_type=EventType.VIEW,
        title=title,
        tags=list(tags),
        metadata={"channel": "bilibili"},
        processed=(i % 2 == 0),
    )


def _mem_db() -> Database:
    db = Database(":memory:")
    db.init_tables()
    return db


def _new_user(db: Database, username: str = "user", role: str = "user", status: str = "active") -> str:
    return db.create_user(username, "x" * 60, role=role, status=status)


def test_init_tables_creates_all_tables():
    db = _mem_db()
    try:
        with db.engine.connect() as conn:
            rows = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).all()
        names = {row[0] for row in rows}
        assert {
            "events",
            "topics",
            "event_topics",
            "profiles",
            "sync_state",
            "users",
            "sessions",
            "source_configs",
        } <= names
    finally:
        db.close()


def test_event_roundtrip_and_duplicate_ignore():
    db = _mem_db()
    try:
        uid = _new_user(db)
        event = _make_event(1, datetime(2026, 8, 1, 10, 0, 0))
        assert db.insert_event(event, uid) is True
        assert db.insert_event(event, uid) is False
        assert db.get_event_count(uid) == 1

        loaded = db.get_events(uid)[0]
        assert loaded.id == event.id
        assert loaded.source == "test"
        assert loaded.event_type == EventType.VIEW
        assert loaded.tags == ["编程"]
        assert loaded.metadata == {"channel": "bilibili"}
        assert loaded.processed is False
        assert loaded.depth == Depth.BROWSE
    finally:
        db.close()


def test_insert_events_batch_counts_inserted_only():
    db = _mem_db()
    try:
        uid = _new_user(db)
        base = datetime(2026, 8, 1, 10, 0, 0)
        events_list = [_make_event(i, base + timedelta(hours=i)) for i in range(3)]
        assert db.insert_events(events_list, uid) == 3
        assert db.insert_events([events_list[0]], uid) == 0
        assert db.get_event_count(uid) == 3
    finally:
        db.close()


def test_get_events_filters_and_ordering():
    db = _mem_db()
    try:
        uid = _new_user(db)
        base = datetime(2026, 8, 1, 10, 0, 0)
        db.insert_events(
            [
                _make_event(1, base, title="A"),
                _make_event(2, base + timedelta(hours=1), title="B"),
                _make_event(3, base + timedelta(hours=2), title="C"),
            ],
            uid,
        )
        rows = db.get_events(uid, limit=2)
        assert [e.title for e in rows] == ["C", "B"]
        rows = db.get_events(uid, source="missing")
        assert rows == []
        rows = db.get_events(uid, since=base + timedelta(hours=1))
        assert [e.title for e in rows] == ["C", "B"]
        rows = db.get_events(uid, event_type="view")
        assert len(rows) == 3
    finally:
        db.close()


def test_unprocessed_and_mark_processed():
    db = _mem_db()
    try:
        uid = _new_user(db)
        base = datetime(2026, 8, 1, 10, 0, 0)
        db.insert_events([_make_event(i, base + timedelta(hours=i)) for i in range(3)], uid)
        unprocessed = db.get_unprocessed_events(uid)
        assert {e.id for e in unprocessed} == {"ev-1"}
        db.mark_processed(uid, ["ev-1", "ev-2"])
        assert db.get_unprocessed_events(uid) == []
    finally:
        db.close()


def test_sync_state_upsert_accumulates():
    db = _mem_db()
    try:
        uid = _new_user(db)
        assert db.get_last_sync(uid, "bilibili") is None
        db.update_sync_state(uid, "bilibili", last_event_id="e1", count=2)
        db.update_sync_state(uid, "bilibili", last_event_id=None, count=3)
        state = db.get_last_sync(uid, "bilibili")
        assert state is not None
        with db.engine.connect() as conn:
            row = conn.execute(
                text("SELECT last_event_id, total_synced FROM sync_state WHERE user_id=:uid AND source='bilibili'"),
                {"uid": uid},
            ).mappings().one()
        assert row["last_event_id"] == "e1"
        assert row["total_synced"] == 5
    finally:
        db.close()


def test_topic_upsert_and_query():
    db = _mem_db()
    try:
        uid = _new_user(db)
        topic = Topic(
            id="t1",
            name="Python",
            category="general",
            frequency=5,
            weight=1.0,
            related_topics=["编程", "后端"],
        )
        db.insert_topic(topic, uid)
        topic.frequency = 8
        topic.weight = 2.0
        db.insert_topic(topic, uid)

        rows = db.get_topics(uid)
        assert len(rows) == 1
        assert rows[0].frequency == 8
        assert rows[0].weight == 2.0
        assert rows[0].related_topics == ["编程", "后端"]
        assert db.get_topics(uid, category="nope") == []
    finally:
        db.close()


def test_event_topic_link_upsert():
    db = _mem_db()
    try:
        uid = _new_user(db)
        db.link_event_topic("e1", "t1", uid, relevance=0.5)
        db.link_event_topic("e1", "t1", uid, relevance=0.9)
        with db.engine.connect() as conn:
            row = conn.execute(
                text("SELECT relevance FROM event_topics WHERE event_id='e1' AND topic_id='t1' AND user_id=:uid"),
                {"uid": uid},
            ).mappings().one()
        assert row["relevance"] == 0.9
    finally:
        db.close()


def test_profile_roundtrip():
    db = _mem_db()
    try:
        uid = _new_user(db)
        topic = Topic(
            id="topic-Python",
            name="Python",
            category="general",
            frequency=3,
            weight=1.2,
            first_seen=datetime(2026, 7, 1, 8, 0, 0),
        )
        profile = Profile(
            id="p1",
            timestamp=datetime(2026, 8, 4, 12, 0, 0),
            period="weekly",
            top_topics=[topic],
            topic_clusters={"cluster_0": {"keywords": ["Python"], "count": 3}},
            total_events=3,
            total_duration=120,
            active_days=2,
            source_distribution={"bilibili": 3},
            emerging_topics=["FastAPI"],
            insights=["测试"],
            event_ids=["ev-1", "ev-2", "ev-3"],
        )
        db.insert_profile(profile, uid)
        db.insert_profile(profile, uid)  # 幂等覆盖

        rows = db.get_profiles(uid, period="weekly")
        assert len(rows) == 1
        assert rows[0].id == "p1"
        assert rows[0].total_events == 3
        assert rows[0].top_topics[0].name == "Python"
        assert rows[0].top_topics[0].first_seen == datetime(2026, 7, 1, 8, 0, 0)
        assert rows[0].topic_clusters["cluster_0"]["count"] == 3
        assert rows[0].event_ids == ["ev-1", "ev-2", "ev-3"]
        assert db.get_profiles(uid, period="monthly") == []
    finally:
        db.close()


def test_stats():
    db = _mem_db()
    try:
        uid = _new_user(db)
        base = datetime(2026, 8, 1, 10, 0, 0)
        db.insert_events([_make_event(i, base + timedelta(hours=i)) for i in range(3)], uid)
        stats = db.get_stats(uid)
        assert stats["total"] == 3
        assert stats["by_source"] == {"test": 3}
        assert stats["by_type"] == {"view": 3}
    finally:
        db.close()


def test_postgres_engine_and_sql_dialect():
    db = Database("postgresql+psycopg://user:pass@localhost:5432/profile")
    try:
        assert db.engine.dialect.name == "postgresql"
    finally:
        db.close()

    pg = postgresql.dialect()
    stmt_ignore = (
        dialect_insert(events, "postgresql")
        .values(id="x", user_id="u", timestamp=datetime.now(), source="t", event_type="view", title="t")
        .on_conflict_do_nothing()
    )
    assert "ON CONFLICT" in str(stmt_ignore.compile(dialect=pg))

    stmt_upsert = (
        dialect_insert(events, "postgresql")
        .values(id="x", user_id="u", timestamp=datetime.now(), source="t", event_type="view", title="t")
        .on_conflict_do_update(index_elements=["id", "user_id"], set_={"title": "new"})
    )
    compiled = str(stmt_upsert.compile(dialect=pg))
    assert "ON CONFLICT" in compiled
    assert "DO UPDATE" in compiled


def test_live_postgres_roundtrip():
    """DATABASE_URL 指向 PostgreSQL 时跑真库用例；否则跳过。"""
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql"):
        return

    db = Database(url)
    try:
        metadata.drop_all(db.engine)
        db.init_tables()
        base = datetime(2026, 8, 1, 10, 0, 0)
        uid = db.create_user("pg-user", "x" * 60, role="user", status="active")
        event = _make_event(1, base)
        assert db.insert_event(event, uid) is True
        assert db.insert_event(event, uid) is False
        assert db.get_event_count(uid) == 1
        assert db.get_events(uid)[0].tags == ["编程"]

        db.update_sync_state(uid, "test", last_event_id="e1", count=2)
        db.update_sync_state(uid, "test", last_event_id=None, count=3)
        with db.engine.connect() as conn:
            row = conn.execute(
                text("SELECT total_synced FROM sync_state WHERE user_id=:uid AND source='test'"),
                {"uid": uid},
            ).mappings().one()
        assert row["total_synced"] == 5

        topic = Topic(id="t1", name="Python", category="general", frequency=1)
        db.insert_topic(topic, uid)
        assert db.get_topics(uid)[0].name == "Python"
        db.link_event_topic(event.id, topic.id, uid, relevance=1.0)
    finally:
        metadata.drop_all(db.engine)
        db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 数据库双后端测试通过！")
