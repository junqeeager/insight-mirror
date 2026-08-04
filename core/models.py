"""核心数据模型"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
from enum import Enum


class EventType(Enum):
    """行为类型"""
    VIEW = "view"
    READ = "read"
    SEARCH = "search"
    BOOKMARK = "bookmark"
    CREATE = "create"
    NOTE = "note"


class Depth(Enum):
    """行为深度"""
    SKIM = "skim"       # <10%
    BROWSE = "browse"   # 10-30%
    READ = "read"       # 30-70%
    DEEP = "deep"       # >70%


@dataclass
class Event:
    """统一行为事件"""
    id: str
    timestamp: datetime
    source: str
    event_type: EventType
    title: str
    url: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    duration: Optional[int] = None
    progress: Optional[float] = None
    depth: Depth = Depth.BROWSE
    metadata: dict = field(default_factory=dict)
    processed: bool = False
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """转为可序列化的字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "event_type": self.event_type.value,
            "title": self.title,
            "url": self.url,
            "description": self.description,
            "tags": self.tags,
            "duration": self.duration,
            "progress": self.progress,
            "depth": self.depth.value,
            "metadata": self.metadata,
            "processed": self.processed,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class Topic:
    """主题/关键词"""
    id: str
    name: str
    category: str
    frequency: int = 0
    weight: float = 0.0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    related_topics: List[str] = field(default_factory=list)
    events: List[str] = field(default_factory=list)


@dataclass
class Profile:
    """用户画像快照"""
    id: str
    timestamp: datetime
    period: str  # weekly / monthly / yearly
    top_topics: List[Topic] = field(default_factory=list)
    topic_clusters: dict = field(default_factory=dict)
    total_events: int = 0
    total_duration: int = 0
    active_days: int = 0
    source_distribution: dict = field(default_factory=dict)
    emerging_topics: List[str] = field(default_factory=list)
    declining_topics: List[str] = field(default_factory=list)
    insights: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
