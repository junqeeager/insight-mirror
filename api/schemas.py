"""API 数据模型"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EventOut(BaseModel):
    """事件响应模型"""

    id: str
    timestamp: datetime
    source: str
    event_type: str
    title: str
    url: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    duration: Optional[int] = None
    progress: Optional[float] = None
    depth: str = "browse"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    processed: bool = False

    @classmethod
    def from_event(cls, event) -> "EventOut":
        return cls(
            id=event.id,
            timestamp=event.timestamp,
            source=event.source,
            event_type=event.event_type.value,
            title=event.title,
            url=event.url,
            description=event.description,
            tags=event.tags,
            duration=event.duration,
            progress=event.progress,
            depth=event.depth.value,
            metadata=event.metadata,
            processed=event.processed,
        )


class TopicOut(BaseModel):
    """主题响应模型"""

    id: str
    name: str
    category: str
    frequency: int = 0
    weight: float = 0.0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    related_topics: List[str] = Field(default_factory=list)

    @classmethod
    def from_topic(cls, topic) -> "TopicOut":
        return cls(
            id=topic.id,
            name=topic.name,
            category=topic.category,
            frequency=topic.frequency,
            weight=topic.weight,
            first_seen=topic.first_seen,
            last_seen=topic.last_seen,
            related_topics=topic.related_topics,
        )


class ProfileOut(BaseModel):
    """画像快照响应模型"""

    id: str
    timestamp: datetime
    period: str
    top_topics: List[TopicOut] = Field(default_factory=list)
    topic_clusters: Dict[str, Any] = Field(default_factory=dict)
    total_events: int = 0
    total_duration: int = 0
    active_days: int = 0
    source_distribution: Dict[str, int] = Field(default_factory=dict)
    emerging_topics: List[str] = Field(default_factory=list)
    declining_topics: List[str] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    event_ids: List[str] = Field(default_factory=list)

    @classmethod
    def from_profile(cls, profile) -> "ProfileOut":
        return cls(
            id=profile.id,
            timestamp=profile.timestamp,
            period=profile.period,
            top_topics=[TopicOut.from_topic(t) for t in profile.top_topics],
            topic_clusters=profile.topic_clusters,
            total_events=profile.total_events,
            total_duration=profile.total_duration,
            active_days=profile.active_days,
            source_distribution=profile.source_distribution,
            emerging_topics=profile.emerging_topics,
            declining_topics=profile.declining_topics,
            insights=profile.insights,
            event_ids=profile.event_ids,
        )


class StatsOut(BaseModel):
    """统计响应模型"""

    total: int
    by_source: Dict[str, int] = Field(default_factory=dict)
    by_type: Dict[str, int] = Field(default_factory=dict)


class RefreshTaskOut(BaseModel):
    """刷新任务创建响应"""

    task_id: str
    status: str = "started"
    message: str = ""


class TaskStatusOut(BaseModel):
    """刷新任务状态响应"""

    task_id: str
    status: str
    profile_id: Optional[str] = None
    error: Optional[str] = None
