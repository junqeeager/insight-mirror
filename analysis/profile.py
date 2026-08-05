"""画像生成器"""

import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from core.models import Event, Profile, Topic
from core.database import Database
from analysis.keywords import extract_keywords_from_events
from analysis.topics import cluster_topics, get_cluster_keywords
from analysis.trends import (
    analyze_source_distribution,
    analyze_type_distribution,
    detect_emerging_topics,
    detect_declining_topics,
    calculate_activity_streak,
)
from analysis.insights import generate_insights


class ProfileGenerator:
    """画像生成器"""

    def __init__(self, db: Database, config: dict = None):
        self.db = db
        self.config = config or {}

    def generate(
        self,
        user_id: str,
        period: str = "weekly",
        since: Optional[datetime] = None,
        persist: bool = True,
    ) -> Profile:
        """
        生成画像

        Args:
            period: weekly / monthly / yearly
            since: 起始时间（None 则自动计算）

        Returns:
            Profile 对象
        """
        # 确定时间范围
        if since is None:
            since = self._get_period_start(period)

        # 获取时间范围内的事件
        events = self.db.get_events(user_id=user_id, since=since, limit=10000)

        # 提取关键词
        keywords = extract_keywords_from_events(events, top_n=20)
        top_topics = [
            Topic(
                id=f"topic-general-{word}",
                name=word,
                category="general",
                weight=weight,
            )
            for word, weight in keywords
        ]

        # 主题聚类
        if len(events) >= 5:
            clusters = cluster_topics(events, n_clusters=min(5, len(events)))
            topic_clusters = {}
            for cluster_id, cluster_events in clusters.items():
                cluster_kw = get_cluster_keywords(cluster_events, top_n=5)
                topic_clusters[f"cluster_{cluster_id}"] = {
                    "keywords": [kw for kw, _ in cluster_kw],
                    "count": len(cluster_events),
                }
        else:
            topic_clusters = {}

        # 来源分布
        source_distribution = analyze_source_distribution(events)

        # 行为类型分布
        type_distribution = analyze_type_distribution(events)

        # 活跃天数
        active_days = len(set(e.timestamp.date() for e in events))

        # 总时长
        total_duration = sum(e.duration for e in events if e.duration)

        # 新兴和衰退话题
        emerging = detect_emerging_topics(events)
        declining = detect_declining_topics(events)

        # 活跃度统计
        streak_info = calculate_activity_streak(events)

        # 生成洞察
        stats = {
            "source_distribution": source_distribution,
            "type_distribution": type_distribution,
            "streak": streak_info,
        }
        insights = generate_insights(events, stats)

        # 构建画像
        profile = Profile(
            id=f"profile-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(),
            period=period,
            top_topics=top_topics,
            topic_clusters=topic_clusters,
            total_events=len(events),
            total_duration=total_duration,
            active_days=active_days,
            source_distribution=source_distribution,
            emerging_topics=emerging,
            declining_topics=declining,
            insights=insights,
            event_ids=[e.id for e in events],
        )

        if persist:
            self._persist(profile, events, user_id)

        return profile

    def _persist(self, profile: Profile, events: List[Event], user_id: str) -> None:
        """将画像结果写入 topics / event_topics / profiles 表（批量单事务）"""
        if not events:
            self.db.insert_profile(profile, user_id)
            return

        total = max(len(events), 1)

        def contains(event: Event, word: str) -> bool:
            text = " ".join(filter(None, [event.title, event.description]))
            text += " " + " ".join(event.tags)
            return word.lower() in text.lower()

        topic_rows: List[Topic] = []
        links: List[Tuple[str, str, float]] = []

        # 1. Top 关键词主题
        for topic in profile.top_topics:
            matched = [e for e in events if contains(e, topic.name)]
            if matched:
                topic.frequency = len(matched)
                topic.first_seen = min(e.timestamp for e in matched)
                topic.last_seen = max(e.timestamp for e in matched)
            topic_rows.append(topic)
            for e in matched:
                links.append((e.id, topic.id, round(topic.weight, 4)))

        # 2. 聚类主题（写入对应 cluster 分类）
        for cluster_id, info in profile.topic_clusters.items():
            keywords = info.get("keywords", [])
            if not keywords:
                continue
            base_weight = info.get("count", 0) / total
            for kw in keywords:
                topic = Topic(
                    id=f"topic-cluster-{cluster_id}-{kw}",
                    name=kw,
                    category=cluster_id,
                    weight=base_weight,
                )
                matched = [e for e in events if contains(e, kw)]
                if matched:
                    topic.frequency = len(matched)
                    topic.first_seen = min(e.timestamp for e in matched)
                    topic.last_seen = max(e.timestamp for e in matched)
                topic_rows.append(topic)
                for e in matched:
                    links.append((e.id, topic.id, round(base_weight, 4)))

        # 3. 批量写入主题与关联，再保存画像快照
        self.db.upsert_topics(topic_rows, user_id)
        self.db.link_event_topics(links, user_id)
        self.db.insert_profile(profile, user_id)

    def _get_period_start(self, period: str) -> datetime:
        """获取周期起始时间"""
        now = datetime.now()
        if period == "weekly":
            return now - timedelta(days=7)
        elif period == "monthly":
            return now - timedelta(days=30)
        elif period == "yearly":
            return now - timedelta(days=365)
        else:
            return now - timedelta(days=7)
