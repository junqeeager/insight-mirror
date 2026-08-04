"""数据库管理：SQLAlchemy Core 双后端（SQLite / PostgreSQL）"""

import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    event,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import make_url
from sqlalchemy.pool import StaticPool

from core.models import Depth, Event, EventType, Profile, Topic

metadata = MetaData()

events = Table(
    "events",
    metadata,
    Column("id", String, primary_key=True),
    Column("timestamp", DateTime, nullable=False),
    Column("source", String, nullable=False),
    Column("event_type", String, nullable=False),
    Column("title", Text, nullable=False),
    Column("url", Text),
    Column("description", Text),
    Column("tags", JSON),
    Column("duration", Integer),
    Column("progress", Float),
    Column("depth", String),
    Column("metadata", JSON),
    Column("processed", Boolean, default=False),
    Column("created_at", DateTime, default=datetime.now),
    Index("idx_events_timestamp", "timestamp"),
    Index("idx_events_source", "source"),
    Index("idx_events_type", "event_type"),
    Index("idx_events_processed", "processed"),
)

topics = Table(
    "topics",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("category", String, nullable=False),
    Column("frequency", Integer, default=0),
    Column("weight", Float, default=0.0),
    Column("first_seen", DateTime),
    Column("last_seen", DateTime),
    Column("related_topics", JSON),
    Index("idx_topics_category", "category"),
)

event_topics = Table(
    "event_topics",
    metadata,
    Column("event_id", String, ForeignKey("events.id"), primary_key=True),
    Column("topic_id", String, ForeignKey("topics.id"), primary_key=True),
    Column("relevance", Float, default=1.0),
    Index("idx_event_topics_topic", "topic_id"),
)

profiles = Table(
    "profiles",
    metadata,
    Column("id", String, primary_key=True),
    Column("timestamp", DateTime, nullable=False),
    Column("period", String, nullable=False),
    Column("data", JSON, nullable=False),
    Column("created_at", DateTime, default=datetime.now),
    Index("idx_profiles_period", "period", "timestamp"),
)

sync_state = Table(
    "sync_state",
    metadata,
    Column("source", String, primary_key=True),
    Column("last_sync", DateTime),
    Column("last_event_id", String),
    Column("total_synced", Integer, default=0),
    Column("config", JSON),
)


def normalize_database_url(value: str) -> str:
    """把裸路径 / :memory: / SQLAlchemy URL 统一为可用的数据库 URL。"""
    if "://" in value:
        return value
    if value == ":memory:":
        return "sqlite:///:memory:"
    return f"sqlite:///{value}"


def dialect_insert(table: Table, dialect_name: str):
    """返回支持 ON CONFLICT 的方言化 insert 构造。"""
    if dialect_name == "sqlite":
        return sqlite_insert(table)
    return postgresql_insert(table)


def database_url(config: dict) -> str:
    """解析数据库 URL：优先 DATABASE_URL 环境变量，其次 config.database.url。"""
    return (
        os.environ.get("DATABASE_URL")
        or config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    )


def _json_compatible(value):
    """把 dataclass 递归转为 JSON 可序列化结构（datetime 转 ISO 字符串）。"""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    return value


class Database:
    """数据库管理：SQLite 与 PostgreSQL 双后端，方法签名保持向后兼容。"""

    def __init__(self, db_url: str = "sqlite:///./data/profile.db"):
        self.db_url = normalize_database_url(db_url)
        self.dialect = make_url(self.db_url).get_backend_name()

        if self.dialect == "sqlite":
            db_path = make_url(self.db_url).database
            if db_path not in (None, "", ":memory:"):
                Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            if self.db_url == "sqlite:///:memory:":
                self.engine = create_engine(
                    self.db_url,
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False},
                )
            else:
                self.engine = create_engine(
                    self.db_url,
                    connect_args={"timeout": 30},
                )
                self._enable_sqlite_pragmas()
        else:
            self.engine = create_engine(self.db_url, pool_pre_ping=True)

    def _enable_sqlite_pragmas(self) -> None:
        """SQLite 文件库启用 WAL 与 busy_timeout，提升并发与响应。"""

        @event.listens_for(self.engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    def init_tables(self):
        """初始化数据库表与索引（幂等）。"""
        metadata.create_all(self.engine)

    @staticmethod
    def _event_row(event: Event) -> dict:
        return {
            "id": event.id,
            "timestamp": event.timestamp,
            "source": event.source,
            "event_type": event.event_type.value,
            "title": event.title,
            "url": event.url,
            "description": event.description,
            "tags": event.tags,
            "duration": event.duration,
            "progress": event.progress,
            "depth": event.depth.value,
            "metadata": event.metadata,
            "processed": bool(event.processed),
        }

    def insert_event(self, event: Event) -> bool:
        """插入单条事件；主键冲突时忽略并返回 False。"""
        stmt = (
            dialect_insert(events, self.dialect)
            .on_conflict_do_nothing()
            .returning(events.c.id)
        )
        with self.engine.begin() as conn:
            row = conn.execute(stmt, self._event_row(event)).first()
        return row is not None

    def insert_events(self, events_: List[Event]) -> int:
        """批量插入事件，返回实际插入数量（单事务）。"""
        if not events_:
            return 0
        stmt = dialect_insert(events, self.dialect).on_conflict_do_nothing()
        rows = [self._event_row(event) for event in events_]
        with self.engine.begin() as conn:
            before = conn.execute(select(func.count()).select_from(events)).scalar_one()
            conn.execute(stmt, rows)
            after = conn.execute(select(func.count()).select_from(events)).scalar_one()
        return after - before

    def get_events(
        self,
        source: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Event]:
        """查询事件，按时间倒序。"""
        stmt = select(events).order_by(events.c.timestamp.desc()).limit(limit)
        if source:
            stmt = stmt.where(events.c.source == source)
        if event_type:
            stmt = stmt.where(events.c.event_type == event_type)
        if since:
            stmt = stmt.where(events.c.timestamp >= since)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._row_to_event(row) for row in rows]

    def get_unprocessed_events(self, limit: int = 500) -> List[Event]:
        """获取未处理的事件。"""
        stmt = (
            select(events)
            .where(events.c.processed.is_(False))
            .order_by(events.c.timestamp)
            .limit(limit)
        )
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._row_to_event(row) for row in rows]

    def mark_processed(self, event_ids: List[str]):
        """标记事件为已处理。"""
        if not event_ids:
            return
        stmt = (
            update(events)
            .where(events.c.id.in_(event_ids))
            .values(processed=True)
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_last_sync(self, source: str) -> Optional[datetime]:
        """获取数据源最后同步时间。"""
        stmt = select(sync_state.c.last_sync).where(sync_state.c.source == source)
        with self.engine.connect() as conn:
            row = conn.execute(stmt).mappings().first()
        if row and row["last_sync"]:
            return row["last_sync"]
        return None

    def update_sync_state(
        self, source: str, last_event_id: Optional[str] = None, count: int = 0
    ):
        """更新同步状态（upsert，保留 last_event_id 并累加 total_synced）。"""
        stmt = dialect_insert(sync_state, self.dialect).values(
            source=source,
            last_sync=datetime.now(),
            last_event_id=last_event_id,
            total_synced=count,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[sync_state.c.source],
            set_={
                "last_sync": stmt.excluded.last_sync,
                "last_event_id": func.coalesce(
                    stmt.excluded.last_event_id, sync_state.c.last_event_id
                ),
                "total_synced": sync_state.c.total_synced + stmt.excluded.total_synced,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def insert_topic(self, topic: Topic):
        """插入或整体更新主题。"""
        stmt = dialect_insert(topics, self.dialect).values(
            id=topic.id,
            name=topic.name,
            category=topic.category,
            frequency=topic.frequency,
            weight=topic.weight,
            first_seen=topic.first_seen,
            last_seen=topic.last_seen,
            related_topics=topic.related_topics,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[topics.c.id],
            set_={
                "name": stmt.excluded.name,
                "category": stmt.excluded.category,
                "frequency": stmt.excluded.frequency,
                "weight": stmt.excluded.weight,
                "first_seen": stmt.excluded.first_seen,
                "last_seen": stmt.excluded.last_seen,
                "related_topics": stmt.excluded.related_topics,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def link_event_topic(self, event_id: str, topic_id: str, relevance: float = 1.0):
        """建立事件与主题的关联（存在则更新 relevance）。"""
        stmt = dialect_insert(event_topics, self.dialect).values(
            event_id=event_id,
            topic_id=topic_id,
            relevance=relevance,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[event_topics.c.event_id, event_topics.c.topic_id],
            set_={"relevance": stmt.excluded.relevance},
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def insert_profile(self, profile: Profile):
        """保存画像快照（存在则整体覆盖）。"""
        stmt = dialect_insert(profiles, self.dialect).values(
            id=profile.id,
            timestamp=profile.timestamp,
            period=profile.period,
            data=_json_compatible(asdict(profile)),
            created_at=datetime.now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[profiles.c.id],
            set_={
                "timestamp": stmt.excluded.timestamp,
                "period": stmt.excluded.period,
                "data": stmt.excluded.data,
                "created_at": stmt.excluded.created_at,
            },
        )
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get_profiles(self, period: Optional[str] = None, limit: int = 10) -> List[Profile]:
        """查询画像快照。"""
        stmt = select(profiles).order_by(profiles.c.timestamp.desc()).limit(limit)
        if period:
            stmt = stmt.where(profiles.c.period == period)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()

        profiles_out = []
        for row in rows:
            data = row["data"]
            topics_out = [
                Topic(
                    id=t.get("id", ""),
                    name=t.get("name", ""),
                    category=t.get("category", ""),
                    frequency=t.get("frequency", 0),
                    weight=t.get("weight", 0.0),
                    first_seen=datetime.fromisoformat(t["first_seen"])
                    if t.get("first_seen")
                    else None,
                    last_seen=datetime.fromisoformat(t["last_seen"])
                    if t.get("last_seen")
                    else None,
                    related_topics=t.get("related_topics", []),
                    events=t.get("events", []),
                )
                for t in data.get("top_topics", [])
            ]
            profiles_out.append(
                Profile(
                    id=row["id"],
                    timestamp=row["timestamp"],
                    period=row["period"],
                    top_topics=topics_out,
                    topic_clusters=data.get("topic_clusters", {}),
                    total_events=data.get("total_events", 0),
                    total_duration=data.get("total_duration", 0),
                    active_days=data.get("active_days", 0),
                    source_distribution=data.get("source_distribution", {}),
                    emerging_topics=data.get("emerging_topics", []),
                    declining_topics=data.get("declining_topics", []),
                    insights=data.get("insights", []),
                    event_ids=data.get("event_ids", []),
                )
            )
        return profiles_out

    def get_topics(self, category: Optional[str] = None, limit: int = 50) -> List[Topic]:
        """查询主题，按频率倒序。"""
        stmt = select(topics).order_by(topics.c.frequency.desc()).limit(limit)
        if category:
            stmt = stmt.where(topics.c.category == category)
        with self.engine.connect() as conn:
            rows = conn.execute(stmt).mappings().all()
        return [self._row_to_topic(row) for row in rows]

    def get_event_count(self, source: Optional[str] = None) -> int:
        """获取事件总数。"""
        stmt = select(func.count()).select_from(events)
        if source:
            stmt = stmt.where(events.c.source == source)
        with self.engine.connect() as conn:
            return conn.execute(stmt).scalar_one()

    def get_stats(self) -> dict:
        """获取整体统计。"""
        with self.engine.connect() as conn:
            total = conn.execute(select(func.count()).select_from(events)).scalar_one()
            by_source = dict(
                conn.execute(
                    select(events.c.source, func.count()).group_by(events.c.source)
                ).all()
            )
            by_type = dict(
                conn.execute(
                    select(events.c.event_type, func.count()).group_by(events.c.event_type)
                ).all()
            )
        return {"total": total, "by_source": by_source, "by_type": by_type}

    @staticmethod
    def _row_to_event(row) -> Event:
        """将数据库行转为 Event 对象。"""
        return Event(
            id=row["id"],
            timestamp=row["timestamp"],
            source=row["source"],
            event_type=EventType(row["event_type"]),
            title=row["title"],
            url=row["url"],
            description=row["description"],
            tags=list(row["tags"]) if row["tags"] else [],
            duration=row["duration"],
            progress=row["progress"],
            depth=Depth(row["depth"]) if row["depth"] else Depth.BROWSE,
            metadata=dict(row["metadata"]) if row["metadata"] else {},
            processed=bool(row["processed"]),
        )

    @staticmethod
    def _row_to_topic(row) -> Topic:
        """将数据库行转为 Topic 对象。"""
        return Topic(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            frequency=row["frequency"],
            weight=row["weight"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            related_topics=list(row["related_topics"])
            if row["related_topics"]
            else [],
        )

    def close(self):
        """释放连接池。"""
        self.engine.dispose()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
