"""多用户体系测试：账号、会话、数据隔离、凭据加密与旧库迁移（离线）"""

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from sqlalchemy import text  # noqa: E402

from core.auth import (  # noqa: E402
    decrypt_config,
    encrypt_config,
    generate_session_token,
    hash_password,
    verify_password,
)
from core.database import Database  # noqa: E402
from core.models import Event, EventType  # noqa: E402
from core.sync_service import build_user_sources  # noqa: E402
from scripts.migrate_multiuser import migrate  # noqa: E402


def _mem_db() -> Database:
    db = Database(":memory:")
    db.init_tables()
    return db


def _make_user(db: Database, username: str = "alice", status: str = "active") -> str:
    return db.create_user(
        username, hash_password("test-pass-123"), role="user", status=status
    )


def _event(i: int) -> Event:
    return Event(
        id=f"ev-{i}",
        timestamp=datetime(2026, 8, 1, 10, 0, 0),
        source="test",
        event_type=EventType.VIEW,
        title="测试事件",
    )


def test_password_hash_roundtrip():
    encoded = hash_password("my-pass-123")
    assert verify_password("my-pass-123", encoded)
    assert not verify_password("wrong-pass", encoded)
    assert not verify_password("my-pass-123", "garbage")


def test_user_crud():
    db = _mem_db()
    try:
        uid = _make_user(db)
        user = db.get_user_by_username("alice")
        assert user["id"] == uid
        assert user["status"] == "active"
        assert db.get_user_by_id(uid)["username"] == "alice"

        assert db.update_user_status(uid, "disabled")
        assert db.get_user_by_id(uid)["status"] == "disabled"

        new_hash = hash_password("new-pass-123")
        assert db.update_user_password(uid, new_hash)
        assert db.get_user_by_id(uid)["password_hash"] == new_hash

        assert any(u["username"] == "alice" for u in db.list_users())
    finally:
        db.close()


def test_session_valid_expired_disabled():
    db = _mem_db()
    try:
        uid = _make_user(db)
        raw, token_hash = generate_session_token()
        db.create_session(token_hash, uid, datetime.now() + timedelta(days=30))
        user = db.get_session_user(token_hash)
        assert user["id"] == uid

        # 过期会话失效
        raw2, token_hash2 = generate_session_token()
        db.create_session(token_hash2, uid, datetime.now() - timedelta(days=1))
        assert db.get_session_user(token_hash2) is None

        # 禁用用户会话失效
        raw3, token_hash3 = generate_session_token()
        db.create_session(token_hash3, uid, datetime.now() + timedelta(days=30))
        db.update_user_status(uid, "disabled")
        assert db.get_session_user(token_hash3) is None

        db.delete_session(token_hash)
        assert db.get_session_user(token_hash) is None
    finally:
        db.close()


def test_event_id_collision_across_users():
    db = _mem_db()
    try:
        uid_a = _make_user(db, "alice")
        uid_b = _make_user(db, "bob")
        event = _event(1)
        assert db.insert_event(event, uid_a)
        assert db.insert_event(event, uid_b)

        assert db.get_event_count(uid_a) == 1
        assert db.get_event_count(uid_b) == 1
        assert db.get_events(uid_a)[0].id == "ev-1"
        assert db.get_events(uid_b)[0].id == "ev-1"

        # 隔离：A 的事件不影响 B 的统计
        db.insert_event(_event(2), uid_a)
        assert db.get_event_count(uid_a) == 2
        assert db.get_event_count(uid_b) == 1
        assert db.get_stats(uid_b)["total"] == 1
    finally:
        db.close()


def test_source_config_encryption_roundtrip():
    db = _mem_db()
    try:
        uid = _make_user(db)
        encrypted = encrypt_config({"cookie": "SESSDATA=secret", "username": "alice"})
        db.set_source_config(uid, "bilibili", encrypted, enabled=True)

        row = db.get_source_config(uid, "bilibili")
        assert row["enabled"] is True
        stored = row["config"]
        assert stored["cookie"].startswith("enc:")
        assert stored["username"] == "alice"

        decrypted = decrypt_config(stored)
        assert decrypted["cookie"] == "SESSDATA=secret"

        sources = build_user_sources(db.list_source_configs(uid))
        assert sources["bilibili"]["config"]["cookie"] == "SESSDATA=secret"
        assert sources["bilibili"]["enabled"] is True
    finally:
        db.close()


def _create_legacy_sqlite(db: Database) -> str:
    """用旧版（无 user_id）结构建库，返回测试用户名。"""
    legacy = """
    CREATE TABLE events (
        id VARCHAR PRIMARY KEY, timestamp DATETIME, source VARCHAR, event_type VARCHAR,
        title TEXT, url TEXT, description TEXT, tags JSON, duration INTEGER,
        progress FLOAT, depth VARCHAR, metadata JSON, processed BOOLEAN, created_at DATETIME
    );
    CREATE TABLE topics (
        id VARCHAR PRIMARY KEY, name VARCHAR, category VARCHAR, frequency INTEGER,
        weight FLOAT, first_seen DATETIME, last_seen DATETIME, related_topics JSON
    );
    CREATE TABLE event_topics (
        event_id VARCHAR, topic_id VARCHAR, relevance FLOAT,
        PRIMARY KEY (event_id, topic_id)
    );
    CREATE TABLE profiles (
        id VARCHAR PRIMARY KEY, timestamp DATETIME, period VARCHAR,
        data JSON, created_at DATETIME
    );
    CREATE TABLE sync_state (
        source VARCHAR PRIMARY KEY, last_sync DATETIME, last_event_id VARCHAR,
        total_synced INTEGER, config JSON
    );
    CREATE INDEX idx_events_timestamp ON events (timestamp);
    CREATE INDEX idx_events_source ON events (source);
    CREATE INDEX idx_events_type ON events (event_type);
    CREATE INDEX idx_events_processed ON events (processed);
    CREATE INDEX idx_topics_category ON topics (category);
    CREATE INDEX idx_event_topics_topic ON event_topics (topic_id);
    CREATE INDEX idx_profiles_period ON profiles (period, timestamp);
    """
    with db.engine.begin() as conn:
        for statement in legacy.strip().split(";"):
            if statement.strip():
                conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            """INSERT INTO events (id, timestamp, source, event_type, title)
               VALUES ('legacy-1', '2026-08-01 10:00:00', 'bilibili', 'view', '旧数据')"""
        )
        conn.exec_driver_sql(
            """INSERT INTO topics (id, name, category, frequency, weight)
               VALUES ('topic-Python', 'Python', 'general', 3, 1.0)"""
        )
        conn.exec_driver_sql(
            """INSERT INTO event_topics (event_id, topic_id, relevance)
               VALUES ('legacy-1', 'topic-Python', 0.8)"""
        )
        conn.exec_driver_sql(
            """INSERT INTO profiles (id, timestamp, period, data)
               VALUES ('profile-1', '2026-08-04 12:00:00', 'weekly',
                       '{"total_events": 1}')"""
        )
        conn.exec_driver_sql(
            """INSERT INTO sync_state (source, last_sync, last_event_id, total_synced)
               VALUES ('bilibili', '2026-08-04 12:00:00', 'legacy-1', 1)"""
        )


def test_migrate_legacy_sqlite_backfills_admin():
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(f"sqlite:///{Path(tmp) / 'legacy.db'}")
        db.init_tables()
        # init_tables 会创建新表，先删掉再建旧表
        with db.engine.begin() as conn:
            conn.exec_driver_sql("DROP TABLE IF EXISTS sync_state")
            conn.exec_driver_sql("DROP TABLE IF EXISTS profiles")
            conn.exec_driver_sql("DROP TABLE IF EXISTS event_topics")
            conn.exec_driver_sql("DROP TABLE IF EXISTS topics")
            conn.exec_driver_sql("DROP TABLE IF EXISTS events")
        _create_legacy_sqlite(db)

        config = {
            "sources": {
                "bilibili": {
                    "enabled": True,
                    "config": {"cookie": "SESSDATA=old", "csrf": "old-csrf"},
                }
            }
        }
        result = migrate(db, "admin", "admin-pass-123", config=config)
        assert result["migrated"] is True

        admin = db.get_user_by_username("admin")
        assert admin["role"] == "admin"
        assert admin["status"] == "active"

        events = db.get_events(admin["id"])
        assert len(events) == 1
        assert events[0].id == "legacy-1"
        assert db.get_event_count(admin["id"]) == 1
        assert db.get_topics(admin["id"])
        assert db.get_profiles(admin["id"], period="weekly")
        assert db.get_last_sync(admin["id"], "bilibili") is not None

        # 管理员数据源配置从 config.yaml 播种（凭据加密）
        row = db.get_source_config(admin["id"], "bilibili")
        assert row["enabled"] is True
        assert decrypt_config(row["config"])["cookie"] == "SESSDATA=old"

        # 幂等：再次迁移直接跳过
        result2 = migrate(db, "admin", "admin-pass-123", config=config)
        assert result2["migrated"] is False
        db.close()


def test_migrate_on_fresh_db_noop():
    db = _mem_db()
    try:
        result = migrate(db, "admin", "admin-pass-123", config={})
        assert result["migrated"] is False
    finally:
        db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 多用户体系测试通过！")
