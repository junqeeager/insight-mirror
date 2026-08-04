"""数据源插件解析测试（pytest 兼容，也可直接运行）"""

import sys
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.models import EventType, Depth
from plugins.bilibili.plugin import Plugin as BilibiliPlugin
from plugins.github.plugin import Plugin as GithubPlugin
from plugins.browser_history.plugin import Plugin as BrowserPlugin


def test_bilibili_parse_event():
    plugin = BilibiliPlugin()
    item = {
        "view_at": 1785570138,
        "title": "测试视频",
        "duration": 600,
        "progress": 200,
        "tag_name": "科技",
        "badge": "热门",
        "history": {"bvid": "BV1xx411c7mD", "oid": 12345},
        "show_title": "测试视频标题",
        "author_name": "UP主",
    }
    event = plugin._parse_event(item)
    assert event is not None
    assert event.source == "bilibili"
    assert event.event_type == EventType.VIEW
    assert event.depth == Depth.READ  # 200/600 ≈ 0.33
    assert event.metadata["author"] == "UP主"
    assert event.url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert event.id == "bilibili-12345-1785570138"


def test_bilibili_depth_boundaries():
    plugin = BilibiliPlugin()
    assert plugin._calc_depth(100, 5) == Depth.SKIM
    assert plugin._calc_depth(100, 25) == Depth.BROWSE
    assert plugin._calc_depth(100, 50) == Depth.READ
    assert plugin._calc_depth(100, 90) == Depth.DEEP
    assert plugin._calc_depth(0, 10) == Depth.BROWSE


def test_bilibili_parse_missing_view_at():
    plugin = BilibiliPlugin()
    assert plugin._parse_event({"title": "无时间戳"}) is None


def test_github_parse_push_event():
    plugin = GithubPlugin()
    item = {
        "id": "evt-1",
        "created_at": "2026-08-01T10:00:00Z",
        "type": "PushEvent",
        "repo": {"name": "junqeeager/aicode"},
        "payload": {
            "commits": [
                {"sha": "abc123", "message": "feat: add api layer\n\n说明", "author": {"name": "junqeeager"}}
            ]
        },
    }
    event = plugin._parse_push_event(item)
    assert event is not None
    assert event.source == "github"
    assert event.event_type == EventType.CREATE
    assert event.title == "feat: add api layer"
    assert event.metadata["repo"] == "junqeeager/aicode"


def test_github_parse_no_commits():
    plugin = GithubPlugin()
    item = {
        "id": "evt-2",
        "created_at": "2026-08-01T10:00:00Z",
        "type": "PushEvent",
        "repo": {"name": "x/y"},
        "payload": {"commits": []},
    }
    assert plugin._parse_push_event(item) is None


def test_browser_history_chrome_timestamp():
    chrome_epoch_offset = 11644473600
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE urls (url TEXT, title TEXT, visit_count INT, last_visit_time INT)")
    dt = datetime(2026, 8, 1, 12, 0, 0)
    ts = int((dt.timestamp() + chrome_epoch_offset) * 1000000)
    conn.execute("INSERT INTO urls VALUES (?,?,?,?)", ("https://example.com", "示例页面", 2, ts))
    conn.commit()
    conn.close()

    plugin = BrowserPlugin()
    plugin.browser = "chrome"
    events = plugin._read_history(db_path, datetime(2026, 7, 1))
    Path(db_path).unlink(missing_ok=True)

    assert len(events) == 1
    assert events[0].url == "https://example.com"
    assert events[0].title == "示例页面"
    assert events[0].timestamp == dt
    assert events[0].metadata["visit_count"] == 2


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 插件测试通过！")
