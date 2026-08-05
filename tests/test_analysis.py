"""分析链路测试（pytest 兼容，也可直接运行）"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

from sqlalchemy import text

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.models import Event, EventType
from core.database import Database
from analysis.keywords import extract_keywords, segment_text
from analysis.trends import (
    detect_emerging_topics,
    detect_declining_topics,
    calculate_activity_streak,
)
from analysis.profile import ProfileGenerator


def _make_event(i, dt, title="Python 编程 教程", tags=("编程",)):
    return Event(
        id=f"ev-{i}",
        timestamp=dt,
        source="test",
        event_type=EventType.VIEW,
        title=title,
        tags=list(tags),
    )


def test_keyword_extraction():
    keywords = extract_keywords(["Python 编程 入门 教程", "机器学习 实战"], top_n=10)
    assert keywords, "应提取到关键词"
    words = [w for w, _ in keywords]
    assert "编程" in words or "Python" in words or "入门" in words


def test_segment_text_filters_stopwords():
    words = segment_text("如何学习 Python 编程")
    assert "如何" not in words  # 停用词应被过滤
    assert "Python" in words


def test_activity_streak():
    base = datetime(2026, 8, 1, 10, 0, 0)
    events = [
        _make_event(1, base),
        _make_event(2, base + timedelta(days=1)),
        _make_event(3, base + timedelta(days=2)),
    ]
    streak = calculate_activity_streak(events)
    assert streak["current_streak"] == 3
    assert streak["longest_streak"] == 3
    assert streak["active_days"] == 3


def test_emerging_and_declining():
    now = datetime(2026, 8, 4, 12, 0, 0)
    events = []
    for i in range(3):
        events.append(_make_event(i, now - timedelta(hours=1), tags=("newtopic",)))
    for i in range(3, 7):
        events.append(_make_event(i, now - timedelta(days=20), tags=("oldtopic",)))

    emerging = detect_emerging_topics(events, recent_days=7, earlier_days=30)
    declining = detect_declining_topics(events, recent_days=7, earlier_days=30)
    assert "newtopic" in emerging
    assert "oldtopic" in declining


def test_profile_generation_persists():
    db = Database(":memory:")
    db.init_tables()
    uid = db.create_user("analyst", "x" * 60, role="user", status="active")
    base = datetime(2026, 8, 1, 10, 0, 0)
    titles = [
        "Python 编程入门教程",
        "FastAPI 实战开发",
        "机器学习基础课程",
        "数据分析可视化",
        "Vibe Coding 教程",
    ]
    for i, title in enumerate(titles):
        db.insert_event(
            _make_event(i, base + timedelta(hours=i), title, tags=("编程", "教程")),
            uid,
        )

    generator = ProfileGenerator(db, {"top_n": 10})
    profile = generator.generate(user_id=uid, period="weekly", persist=True)
    assert profile.total_events == 5

    topics = db.get_topics(uid, limit=100)
    assert topics, "topics 表不应为空"
    assert any(t.frequency > 0 for t in topics)

    with db.engine.connect() as conn:
        event_topics = conn.execute(text("SELECT COUNT(*) FROM event_topics")).scalar_one()
        profiles = conn.execute(text("SELECT COUNT(*) FROM profiles")).scalar_one()
        assert event_topics > 0, "event_topics 表不应为空"
        assert profiles == 1
    db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 分析链路测试通过！")
