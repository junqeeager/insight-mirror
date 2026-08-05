"""趋势分析"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from collections import defaultdict

from analysis.keywords import segment_text
from core.models import Event


def analyze_time_distribution(events: List[Event]) -> Dict[str, int]:
    """
    分析事件的时间分布

    Returns:
        {"weekday_0": count, "weekday_1": count, ..., "hour_0": count, ...}
    """
    distribution = defaultdict(int)
    for event in events:
        distribution[f"weekday_{event.timestamp.weekday()}"] += 1
        distribution[f"hour_{event.timestamp.hour}"] += 1
    return dict(distribution)


def analyze_source_distribution(events: List[Event]) -> Dict[str, int]:
    """分析来源分布"""
    distribution = defaultdict(int)
    for event in events:
        distribution[event.source] += 1
    return dict(distribution)


def analyze_type_distribution(events: List[Event]) -> Dict[str, int]:
    """分析行为类型分布"""
    distribution = defaultdict(int)
    for event in events:
        distribution[event.event_type.value] += 1
    return dict(distribution)


def _event_terms(event: Event) -> List[str]:
    """取事件参与趋势统计的词：优先 tags，缺失时用标题分词 top3 兜底。"""
    if event.tags:
        return event.tags
    return segment_text(event.title or "")[:3]


def analyze_topic_trends(
    events: List[Event],
    window_days: int = 7,
) -> Dict[str, List[Tuple[str, int]]]:
    """
    分析话题随时间的趋势

    Args:
        events: 事件列表
        window_days: 滑动窗口大小（天）

    Returns:
        {topic: [(date_str, count), ...]}
    """
    # 按时间排序
    sorted_events = sorted(events, key=lambda e: e.timestamp)

    if not sorted_events:
        return {}

    # 确定时间范围
    start_date = sorted_events[0].timestamp.date()
    end_date = sorted_events[-1].timestamp.date()

    # 按标签聚合
    topic_by_date = defaultdict(lambda: defaultdict(int))
    for event in sorted_events:
        date_str = event.timestamp.strftime("%Y-%m-%d")
        for tag in event.tags:
            topic_by_date[tag][date_str] += 1

    # 生成日期序列
    current_date = start_date
    all_dates = []
    while current_date <= end_date:
        all_dates.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)

    # 转换为时间序列
    trends = {}
    for topic, date_counts in topic_by_date.items():
        trends[topic] = [
            (date_str, date_counts.get(date_str, 0))
            for date_str in all_dates
        ]

    return trends


def detect_emerging_topics(
    events: List[Event],
    recent_days: int = 7,
    earlier_days: int = 30,
    threshold: float = 1.5,
) -> List[str]:
    """
    检测新兴话题

    Args:
        events: 事件列表
        recent_days: 最近 N 天
        earlier_days: 之前 N 天
        threshold: 增长阈值（倍数）

    Returns:
        新兴话题列表
    """
    now = datetime.now()
    recent_cutoff = now - timedelta(days=recent_days)
    earlier_cutoff = recent_cutoff - timedelta(days=earlier_days)

    recent_tags = defaultdict(int)
    earlier_tags = defaultdict(int)

    for event in events:
        for tag in _event_terms(event):
            if event.timestamp >= recent_cutoff:
                recent_tags[tag] += 1
            elif event.timestamp >= earlier_cutoff:
                earlier_tags[tag] += 1

    emerging = []
    for tag, recent_count in recent_tags.items():
        earlier_count = earlier_tags.get(tag, 0)
        if earlier_count == 0 and recent_count >= 3:
            emerging.append(tag)
        elif earlier_count > 0:
            growth = recent_count / earlier_count
            if growth >= threshold and recent_count >= 3:
                emerging.append(tag)

    return emerging


def detect_declining_topics(
    events: List[Event],
    recent_days: int = 7,
    earlier_days: int = 30,
    threshold: float = 0.5,
) -> List[str]:
    """
    检测衰退话题

    Args:
        events: 事件列表
        recent_days: 最近 N 天
        earlier_days: 之前 N 天
        threshold: 衰退阈值（倍数）

    Returns:
        衰退话题列表
    """
    now = datetime.now()
    recent_cutoff = now - timedelta(days=recent_days)
    earlier_cutoff = recent_cutoff - timedelta(days=earlier_days)

    recent_tags = defaultdict(int)
    earlier_tags = defaultdict(int)

    for event in events:
        for tag in _event_terms(event):
            if event.timestamp >= recent_cutoff:
                recent_tags[tag] += 1
            elif event.timestamp >= earlier_cutoff:
                earlier_tags[tag] += 1

    declining = []
    for tag, earlier_count in earlier_tags.items():
        recent_count = recent_tags.get(tag, 0)
        if earlier_count >= 3:
            if recent_count == 0:
                declining.append(tag)
            elif recent_count / earlier_count <= threshold:
                declining.append(tag)

    return declining


def calculate_activity_streak(events: List[Event]) -> Dict[str, int]:
    """
    计算活跃连续天数

    Returns:
        {"current_streak": N, "longest_streak": M, "active_days": K}
    """
    if not events:
        return {"current_streak": 0, "longest_streak": 0, "active_days": 0}

    # 获取所有活跃日期
    active_dates = sorted(set(e.timestamp.date() for e in events))
    active_days = len(active_dates)

    # 计算连续天数
    if not active_dates:
        return {"current_streak": 0, "longest_streak": 0, "active_days": 0}

    longest_streak = 1
    current_streak = 1

    for i in range(1, len(active_dates)):
        if (active_dates[i] - active_dates[i - 1]).days == 1:
            current_streak += 1
            longest_streak = max(longest_streak, current_streak)
        else:
            current_streak = 1

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "active_days": active_days,
    }
