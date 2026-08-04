"""数据源插件解析测试（pytest 兼容，也可直接运行）"""

import sys
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import feedparser
from core.models import EventType, Depth
from plugins.bilibili.plugin import Plugin as BilibiliPlugin
from plugins.github.plugin import Plugin as GithubPlugin
from plugins.browser_history.plugin import Plugin as BrowserPlugin
from plugins.rss import plugin as rss_plugin
from plugins.rss.plugin import Plugin as RssPlugin


RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>示例 RSS 源</title>
    <item>
      <title>RSS 文章 <b>标题</b></title>
      <link>https://example.com/rss/post/1</link>
      <guid isPermaLink="false">rss-guid-001</guid>
      <pubDate>Sat, 01 Aug 2026 12:00:00 GMT</pubDate>
      <description>&lt;p&gt;第一段 &lt;b&gt;简介&lt;/b&gt;&lt;/p&gt;&lt;p&gt;第二段&lt;/p&gt;</description>
      <category>科技</category>
      <author>author@example.com</author>
    </item>
    <item>
      <title>无时间文章</title>
      <link>https://example.com/rss/post/no-time</link>
      <description>没有时间戳</description>
    </item>
  </channel>
</rss>
"""

ATOM_XML = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>示例 Atom 源</title>
  <entry>
    <title>Atom 文章</title>
    <id>urn:uuid:atom-001</id>
    <link href="https://example.com/atom/post/2"/>
    <published>2026-08-02T03:00:00Z</published>
    <author><name>测试作者</name></author>
    <category term="编程"/>
    <category term="Python"/>
    <summary type="html">&lt;p&gt;Atom &lt;em&gt;摘要&lt;/em&gt;&lt;/p&gt;</summary>
  </entry>
</feed>
"""

FALLBACK_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>回退源</title>
    <item>
      <title>无链接文章</title>
      <pubDate>Sat, 01 Aug 2026 12:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


def _utc_to_local(dt: datetime) -> datetime:
    """把带 UTC 时区的时间转成系统本地时区后的 naive datetime"""
    return dt.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


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


def test_rss_parse_rss2_event():
    plugin = RssPlugin()
    feed = feedparser.parse(RSS_XML)
    entry = feed.entries[0]
    event = plugin._parse_event(
        entry,
        "https://example.com/rss.xml",
        str(feed.feed.get("title", "")),
        "科技",
    )

    assert event is not None
    assert event.source == "rss"
    assert event.event_type == EventType.READ
    assert event.depth == Depth.BROWSE
    assert event.id == "rss-rss-guid-001"
    assert event.title == "RSS 文章 标题"
    assert event.url == "https://example.com/rss/post/1"
    assert event.description == "第一段 简介 第二段"
    assert "科技" in event.tags
    assert event.metadata["feed_url"] == "https://example.com/rss.xml"
    assert event.metadata["feed_title"] == "示例 RSS 源"
    assert event.metadata["author"] == "author@example.com"
    assert event.timestamp == _utc_to_local(datetime(2026, 8, 1, 12, 0, 0))


def test_rss_parse_atom_event_and_tags_dedupe():
    plugin = RssPlugin()
    feed = feedparser.parse(ATOM_XML)
    entry = feed.entries[0]
    event = plugin._parse_event(entry, "https://example.com/atom.xml", "示例 Atom 源", "Python")

    assert event is not None
    assert event.id == "rss-urn:uuid:atom-001"
    assert event.url == "https://example.com/atom/post/2"
    assert event.description == "Atom 摘要"
    assert event.tags == ["编程", "Python"]
    assert event.metadata["entry_id"] == "urn:uuid:atom-001"
    assert event.metadata["author"] == "测试作者"
    assert event.timestamp == _utc_to_local(datetime(2026, 8, 2, 3, 0, 0))


def test_rss_parse_missing_timestamp_skipped():
    plugin = RssPlugin()
    feed = feedparser.parse(RSS_XML)
    event = plugin._parse_event(feed.entries[1], "https://example.com/rss.xml", "示例 RSS 源", "科技")
    assert event is None


def test_rss_id_stable_and_fallback():
    plugin = RssPlugin()
    feed = feedparser.parse(RSS_XML)
    entry = feed.entries[0]
    assert plugin._parse_event(entry, "https://example.com/rss.xml", "源", "科技").id == (
        plugin._parse_event(entry, "https://example.com/rss.xml", "源", "科技").id
    )

    fallback_feed = feedparser.parse(FALLBACK_XML)
    fallback_entry = fallback_feed.entries[0]
    event = plugin._parse_event(fallback_entry, "https://example.com/fallback.xml", "回退源", "")
    assert event is not None
    assert event.id.startswith("rss-")
    assert len(event.id) == 4 + 16


def test_rss_fetch_filters_aggregates_and_tolerates_bad_feed():
    plugin = RssPlugin()
    plugin.feeds = [
        {"url": "https://feed.test/old", "category": "旧"},
        {"url": "https://feed.test/new", "category": "新"},
        {"url": "https://feed.test/bad", "category": "坏"},
        {"url": "", "category": "空"},
        "not-a-dict",
    ]

    old_feed = feedparser.parse(FALLBACK_XML)
    new_feed = feedparser.parse(ATOM_XML)

    def fake_parse(url):
        if url == "https://feed.test/old":
            return old_feed
        if url == "https://feed.test/new":
            return new_feed
        raise RuntimeError("网络错误")

    original_parse = rss_plugin.feedparser.parse
    rss_plugin.feedparser.parse = fake_parse
    try:
        events = plugin.fetch(datetime(2026, 8, 2, 0, 0, 0))
    finally:
        rss_plugin.feedparser.parse = original_parse

    assert len(events) == 1
    assert events[0].url == "https://example.com/atom/post/2"
    assert events[0].tags == ["编程", "Python", "新"]
    assert events[0].metadata["feed_url"] == "https://feed.test/new"


def test_rss_fetch_no_feeds():
    plugin = RssPlugin()
    plugin.setup({"feeds": []})
    assert plugin.fetch(datetime(2026, 8, 1)) == []


def test_rss_test_connection():
    plugin = RssPlugin()

    plugin.setup({"feeds": []})
    assert plugin.test_connection() is False

    plugin.setup({"feeds": [{"category": "科技"}]})
    assert plugin.test_connection() is False

    plugin.setup({"feeds": [{"url": "https://example.com/rss.xml", "category": "科技"}]})
    assert plugin.test_connection() is True


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 插件测试通过！")
