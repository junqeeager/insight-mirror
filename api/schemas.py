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


class GraphNode(BaseModel):
    """图谱节点"""

    id: str
    label: str
    freq: int


class GraphEdge(BaseModel):
    """图谱边"""

    source: str
    target: str
    weight: int


class GraphOut(BaseModel):
    """兴趣共现图响应"""

    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)


# ---------- 账号体系 ----------


class RegisterIn(BaseModel):
    """注册请求"""

    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(BaseModel):
    """登录请求"""

    username: str
    password: str


class UserOut(BaseModel):
    """用户信息响应（不含密码哈希）"""

    id: str
    username: str
    role: str
    status: str
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


class LoginOut(BaseModel):
    """登录响应"""

    token: str
    user: UserOut


class SourceConfigIn(BaseModel):
    """保存数据源配置请求"""

    source: str
    config: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class SourceConfigOut(BaseModel):
    """数据源配置响应（敏感字段脱敏）"""

    source: str
    enabled: bool
    config: Dict[str, Any] = Field(default_factory=dict)
    has_secrets: Dict[str, bool] = Field(default_factory=dict)


class SyncIn(BaseModel):
    """触发同步请求"""

    source: Optional[str] = None


class AdminUserPatch(BaseModel):
    """管理员更新用户请求"""

    status: Optional[str] = None
    password: Optional[str] = None
