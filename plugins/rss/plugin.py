"""RSS 数据源插件"""

from datetime import datetime
from typing import List

from core.models import Event, EventType, Depth
from core.plugin_loader import DataSourcePlugin


class Plugin(DataSourcePlugin):
    """RSS 订阅源插件"""

    @property
    def name(self) -> str:
        return "rss"

    @property
    def display_name(self) -> str:
        return "RSS 订阅源"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def icon(self) -> str:
        return "📡"

    @property
    def description(self) -> str:
        return "同步 RSS 订阅源的文章"

    def __init__(self):
        self.feeds: List[dict] = []

    def setup(self, config: dict) -> None:
        self.feeds = config.get("feeds", [])

    def test_connection(self) -> bool:
        # 简单检查是否有配置 feeds
        return bool(self.feeds)

    def fetch(self, since: datetime) -> List[Event]:
        """拉取 RSS 文章"""
        # TODO: 实现 RSS 解析
        # 需要安装 feedparser: pip install feedparser
        events = []

        # for feed_config in self.feeds:
        #     feed_url = feed_config.get("url", "")
        #     category = feed_config.get("category", "")
        #     # 使用 feedparser 解析
        #     import feedparser
        #     feed = feedparser.parse(feed_url)
        #     for entry in feed.entries:
        #         pub_date = datetime(*entry.published_parsed[:6])
        #         if pub_date < since:
        #             continue
        #         events.append(Event(...))

        return events

    def get_status(self) -> dict:
        status = super().get_status()
        status["icon"] = self.icon
        status["feed_count"] = len(self.feeds)
        return status
