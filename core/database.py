"""数据库管理"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from core.models import Event, EventType, Depth, Profile, Topic


class Database:
    """SQLite 数据库管理"""

    def __init__(self, db_path: str = "./data/profile.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")

    def init_tables(self):
        """初始化数据库表"""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                source TEXT NOT NULL,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                description TEXT,
                tags TEXT,
                duration INTEGER,
                progress REAL,
                depth TEXT,
                metadata TEXT,
                processed BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS topics (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                frequency INTEGER DEFAULT 0,
                weight REAL DEFAULT 0.0,
                first_seen DATETIME,
                last_seen DATETIME,
                related_topics TEXT
            );

            CREATE TABLE IF NOT EXISTS event_topics (
                event_id TEXT REFERENCES events(id),
                topic_id TEXT REFERENCES topics(id),
                relevance REAL DEFAULT 1.0,
                PRIMARY KEY (event_id, topic_id)
            );

            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                timestamp DATETIME NOT NULL,
                period TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                source TEXT PRIMARY KEY,
                last_sync DATETIME,
                last_event_id TEXT,
                total_synced INTEGER DEFAULT 0,
                config TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_events_source ON events(source);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed);
            CREATE INDEX IF NOT EXISTS idx_topics_category ON topics(category);
        """)
        self.conn.commit()

    def insert_event(self, event: Event) -> bool:
        """插入单条事件"""
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, timestamp, source, event_type, title, url,
                    description, tags, duration, progress, depth, metadata, processed)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.id,
                    event.timestamp.isoformat(),
                    event.source,
                    event.event_type.value,
                    event.title,
                    event.url,
                    event.description,
                    json.dumps(event.tags, ensure_ascii=False),
                    event.duration,
                    event.progress,
                    event.depth.value,
                    json.dumps(event.metadata, ensure_ascii=False),
                    event.processed,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def insert_events(self, events: List[Event]) -> int:
        """批量插入事件，返回实际插入数量"""
        count = 0
        for event in events:
            if self.insert_event(event):
                count += 1
        return count

    def get_events(
        self,
        source: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Event]:
        """查询事件"""
        query = "SELECT * FROM events WHERE 1=1"
        params = []

        if source:
            query += " AND source = ?"
            params.append(source)
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_unprocessed_events(self, limit: int = 500) -> List[Event]:
        """获取未处理的事件"""
        rows = self.conn.execute(
            "SELECT * FROM events WHERE processed = 0 ORDER BY timestamp LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def mark_processed(self, event_ids: List[str]):
        """标记事件为已处理"""
        placeholders = ",".join("?" for _ in event_ids)
        self.conn.execute(
            f"UPDATE events SET processed = 1 WHERE id IN ({placeholders})",
            event_ids,
        )
        self.conn.commit()

    def get_last_sync(self, source: str) -> Optional[datetime]:
        """获取数据源最后同步时间"""
        row = self.conn.execute(
            "SELECT last_sync FROM sync_state WHERE source = ?", (source,)
        ).fetchone()
        if row and row["last_sync"]:
            return datetime.fromisoformat(row["last_sync"])
        return None

    def update_sync_state(
        self, source: str, last_event_id: Optional[str] = None, count: int = 0
    ):
        """更新同步状态"""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT INTO sync_state (source, last_sync, last_event_id, total_synced)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(source) DO UPDATE SET
                 last_sync = excluded.last_sync,
                 last_event_id = COALESCE(excluded.last_event_id, sync_state.last_event_id),
                 total_synced = sync_state.total_synced + excluded.total_synced""",
            (source, now, last_event_id, count),
        )
        self.conn.commit()

    def insert_topic(self, topic: Topic):
        """插入主题"""
        self.conn.execute(
            """INSERT OR REPLACE INTO topics
               (id, name, category, frequency, weight, first_seen, last_seen, related_topics)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                topic.id,
                topic.name,
                topic.category,
                topic.frequency,
                topic.weight,
                topic.first_seen.isoformat() if topic.first_seen else None,
                topic.last_seen.isoformat() if topic.last_seen else None,
                json.dumps(topic.related_topics),
            ),
        )
        self.conn.commit()

    def link_event_topic(self, event_id: str, topic_id: str, relevance: float = 1.0):
        """建立事件与主题的关联"""
        self.conn.execute(
            """INSERT OR REPLACE INTO event_topics (event_id, topic_id, relevance)
               VALUES (?, ?, ?)""",
            (event_id, topic_id, relevance),
        )
        self.conn.commit()

    def insert_profile(self, profile: Profile):
        """保存画像快照"""
        from dataclasses import asdict
        self.conn.execute(
            """INSERT OR REPLACE INTO profiles
               (id, timestamp, period, data, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                profile.id,
                profile.timestamp.isoformat(),
                profile.period,
                json.dumps(asdict(profile), default=str, ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def get_profiles(self, period: Optional[str] = None, limit: int = 10) -> List[Profile]:
        """查询画像快照"""
        query = "SELECT * FROM profiles WHERE 1=1"
        params = []
        if period:
            query += " AND period = ?"
            params.append(period)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        profiles = []
        for row in rows:
            data = json.loads(row["data"])
            from core.models import Topic
            topics = [
                Topic(
                    id=t.get("id", ""),
                    name=t.get("name", ""),
                    category=t.get("category", ""),
                    frequency=t.get("frequency", 0),
                    weight=t.get("weight", 0.0),
                    first_seen=datetime.fromisoformat(t["first_seen"]) if t.get("first_seen") else None,
                    last_seen=datetime.fromisoformat(t["last_seen"]) if t.get("last_seen") else None,
                    related_topics=t.get("related_topics", []),
                    events=t.get("events", []),
                )
                for t in data.get("top_topics", [])
            ]
            profiles.append(Profile(
                id=row["id"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                period=row["period"],
                top_topics=topics,
                topic_clusters=data.get("topic_clusters", {}),
                total_events=data.get("total_events", 0),
                total_duration=data.get("total_duration", 0),
                active_days=data.get("active_days", 0),
                source_distribution=data.get("source_distribution", {}),
                emerging_topics=data.get("emerging_topics", []),
                declining_topics=data.get("declining_topics", []),
                insights=data.get("insights", []),
                event_ids=data.get("event_ids", []),
            ))
        return profiles

    def get_topics(self, category: Optional[str] = None, limit: int = 50) -> List[Topic]:
        """查询主题"""
        query = "SELECT * FROM topics WHERE 1=1"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY frequency DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_topic(row) for row in rows]

    def get_event_count(self, source: Optional[str] = None) -> int:
        """获取事件总数"""
        if source:
            row = self.conn.execute(
                "SELECT COUNT(*) as cnt FROM events WHERE source = ?", (source,)
            ).fetchone()
        else:
            row = self.conn.execute("SELECT COUNT(*) as cnt FROM events").fetchone()
        return row["cnt"]

    def get_stats(self) -> dict:
        """获取整体统计"""
        total = self.get_event_count()
        by_source = {}
        for row in self.conn.execute(
            "SELECT source, COUNT(*) as cnt FROM events GROUP BY source"
        ):
            by_source[row["source"]] = row["cnt"]

        by_type = {}
        for row in self.conn.execute(
            "SELECT event_type, COUNT(*) as cnt FROM events GROUP BY event_type"
        ):
            by_type[row["event_type"]] = row["cnt"]

        return {"total": total, "by_source": by_source, "by_type": by_type}

    def _row_to_event(self, row) -> Event:
        """将数据库行转为 Event 对象"""
        return Event(
            id=row["id"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            source=row["source"],
            event_type=EventType(row["event_type"]),
            title=row["title"],
            url=row["url"],
            description=row["description"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            duration=row["duration"],
            progress=row["progress"],
            depth=Depth(row["depth"]) if row["depth"] else Depth.BROWSE,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            processed=bool(row["processed"]),
        )

    def _row_to_topic(self, row) -> Topic:
        """将数据库行转为 Topic 对象"""
        return Topic(
            id=row["id"],
            name=row["name"],
            category=row["category"],
            frequency=row["frequency"],
            weight=row["weight"],
            first_seen=datetime.fromisoformat(row["first_seen"]) if row["first_seen"] else None,
            last_seen=datetime.fromisoformat(row["last_seen"]) if row["last_seen"] else None,
            related_topics=json.loads(row["related_topics"]) if row["related_topics"] else [],
        )

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
