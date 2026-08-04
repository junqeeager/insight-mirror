"""数据模型测试"""

import sys
from pathlib import Path
from datetime import datetime

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.models import Event, EventType, Depth, Topic, Profile


def test_event_creation():
    """测试 Event 创建"""
    event = Event(
        id="test-1",
        timestamp=datetime.now(),
        source="test",
        event_type=EventType.VIEW,
        title="测试视频",
        url="https://example.com",
        description="测试描述",
        tags=["tag1", "tag2"],
        duration=120,
        progress=0.8,
        depth=Depth.DEEP,
    )

    assert event.id == "test-1"
    assert event.source == "test"
    assert event.event_type == EventType.VIEW
    assert event.title == "测试视频"
    assert event.tags == ["tag1", "tag2"]
    assert event.duration == 120
    assert event.depth == Depth.DEEP


def test_event_to_dict():
    """测试 Event 序列化"""
    event = Event(
        id="test-1",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        source="test",
        event_type=EventType.VIEW,
        title="测试视频",
    )

    data = event.to_dict()
    assert data["id"] == "test-1"
    assert data["source"] == "test"
    assert data["event_type"] == "view"
    assert data["title"] == "测试视频"


def test_topic_creation():
    """测试 Topic 创建"""
    topic = Topic(
        id="topic-1",
        name="Python",
        category="programming",
        frequency=10,
        weight=0.8,
    )

    assert topic.name == "Python"
    assert topic.category == "programming"
    assert topic.frequency == 10


def test_profile_creation():
    """测试 Profile 创建"""
    profile = Profile(
        id="profile-1",
        timestamp=datetime.now(),
        period="weekly",
        total_events=100,
        active_days=5,
    )

    assert profile.id == "profile-1"
    assert profile.period == "weekly"
    assert profile.total_events == 100


if __name__ == "__main__":
    test_event_creation()
    test_event_to_dict()
    test_topic_creation()
    test_profile_creation()
    print("✅ 所有测试通过！")
