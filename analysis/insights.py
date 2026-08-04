"""洞察生成"""

from datetime import datetime
from typing import List, Dict
from collections import defaultdict

from core.models import Event


def generate_insights(events: List[Event], stats: Dict) -> List[str]:
    """
    基于事件数据生成洞察

    Args:
        events: 事件列表
        stats: 统计数据

    Returns:
        洞察列表
    """
    insights = []

    if not events:
        insights.append("暂无数据，开始同步数据源以生成洞察。")
        return insights

    # 活跃度洞察
    active_days = len(set(e.timestamp.date() for e in events))
    total_days = (events[0].timestamp - events[-1].timestamp).days + 1
    if total_days > 0:
        activity_rate = active_days / total_days
        if activity_rate > 0.8:
            insights.append(f"🎯 你非常活跃，在 {total_days} 天中有 {active_days} 天有活动记录。")
        elif activity_rate > 0.5:
            insights.append(f"📊 你比较活跃，在 {total_days} 天中有 {active_days} 天有活动记录。")
        else:
            insights.append(f"💡 你在 {total_days} 天中有 {active_days} 天有活动记录，可以尝试保持更规律的活动。")

    # 兴趣集中度洞察
    source_dist = defaultdict(int)
    for event in events:
        source_dist[event.source] += 1

    if source_dist:
        top_source = max(source_dist, key=source_dist.get)
        top_ratio = source_dist[top_source] / len(events)
        if top_ratio > 0.8:
            insights.append(f"🔍 你的活动主要集中在 {top_source}（占 {top_ratio:.0%}），可以尝试拓展其他平台。")
        else:
            insights.append(f"🌐 你的活动分布在多个平台，主要来源是 {top_source}。")

    # 时间模式洞察
    hour_dist = defaultdict(int)
    for event in events:
        hour_dist[event.timestamp.hour] += 1

    if hour_dist:
        peak_hour = max(hour_dist, key=hour_dist.get)
        if 6 <= peak_hour < 12:
            insights.append("🌅 你是早起型，上午是你的活跃高峰。")
        elif 12 <= peak_hour < 18:
            insights.append("☀️ 你倾向于在下午活动。")
        elif 18 <= peak_hour < 24:
            insights.append("🌙 你是夜猫子，晚上是你的活跃高峰。")
        else:
            insights.append("🌃 你有深夜活动的习惯。")

    # 深度洞察
    depth_counts = defaultdict(int)
    for event in events:
        depth_counts[event.depth.value] += 1

    deep_count = depth_counts.get("deep", 0)
    total_view = sum(1 for e in events if e.event_type.value == "view")
    if total_view > 0:
        deep_ratio = deep_count / total_view
        if deep_ratio > 0.3:
            insights.append(f"📖 你有深度消费的习惯，{deep_ratio:.0%} 的内容你完整观看/阅读。")
        elif deep_ratio < 0.1:
            insights.append(f"⚡ 你倾向于快速浏览，只有 {deep_ratio:.0%} 的内容被完整消费。")

    # 内容产出洞察
    create_count = sum(1 for e in events if e.event_type.value == "create")
    view_count = sum(1 for e in events if e.event_type.value in ["view", "read"])
    if view_count > 0:
        output_ratio = create_count / view_count
        if output_ratio > 0.1:
            insights.append(f"✍️ 你有良好的输出习惯，创作/消费比为 {output_ratio:.2f}。")
        elif create_count == 0:
            insights.append("💡 你还没有创作记录，尝试将学到的知识输出为文章或代码。")

    return insights


def generate_weekly_summary(events: List[Event]) -> Dict:
    """生成周度摘要"""
    if not events:
        return {}

    # 按天统计
    daily_counts = defaultdict(int)
    for event in events:
        daily_counts[event.timestamp.strftime("%Y-%m-%d")] += 1

    # Top 标签
    tag_counts = defaultdict(int)
    for event in events:
        for tag in event.tags:
            tag_counts[tag] += 1

    top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "total_events": len(events),
        "active_days": len(daily_counts),
        "top_tags": top_tags,
        "daily_counts": dict(daily_counts),
    }
