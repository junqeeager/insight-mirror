"""趋势分析"""

from datetime import datetime, timedelta
from typing import List, Dict
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
    计算活跃连续天数：current_streak 为截至今天（今天无记录则从昨天）的连续天数

    Returns:
        {"current_streak": N, "longest_streak": M, "active_days": K}
    """
    if not events:
        return {"current_streak": 0, "longest_streak": 0, "active_days": 0}

    # 获取所有活跃日期
    today = datetime.now().date()
    active_dates = sorted(
        {e.timestamp.date() for e in events if e.timestamp.date() <= today}
    )
    active_days = len(active_dates)
    if not active_dates:
        return {"current_streak": 0, "longest_streak": 0, "active_days": 0}

    # 最长连续段
    longest_streak = 1
    current_run = 1
    for i in range(1, len(active_dates)):
        if (active_dates[i] - active_dates[i - 1]).days == 1:
            current_run += 1
            longest_streak = max(longest_streak, current_run)
        else:
            current_run = 1

    # 当前连续：从今天（或昨天）向前回溯
    active_set = set(active_dates)
    start = today if today in active_set else today - timedelta(days=1)
    current_streak = 0
    day = start
    while day in active_set:
        current_streak += 1
        day -= timedelta(days=1)

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "active_days": active_days,
    }
