"""RSS 数据源插件"""

import calendar
import hashlib
import logging
import re
from datetime import datetime
from typing import List, Optional

import feedparser

from core.models import Event, EventType, Depth
from core.plugin_loader import DataSourcePlugin

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


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
        self.feeds = list(config.get("feeds", []) or [])

    def test_connection(self) -> bool:
        # 仅做配置级检查，不发起网络请求，保证测试可离线运行
        if not self.feeds:
            return False
        return all(
            isinstance(feed, dict) and bool(str(feed.get("url", "")).strip())
            for feed in self.feeds
        )

    def fetch(self, since: datetime) -> List[Event]:
        """拉取 RSS 文章并转换为统一事件"""
        events = []

        for feed_config in self.feeds:
            if not isinstance(feed_config, dict):
                continue
            feed_url = str(feed_config.get("url", "")).strip()
            if not feed_url:
                continue
            category = str(feed_config.get("category", "") or "rss").strip()

            try:
                feed = feedparser.parse(feed_url)
            except Exception as e:
                logger.warning("解析 RSS feed 失败: %s: %s", feed_url, e)
                continue

            if not feed:
                continue

            feed_title = ""
            if feed and hasattr(feed, "feed"):
                feed_title = str(feed.feed.get("title", "") or "")

            for entry in feed.entries:
                event = self._parse_event(entry, feed_url, feed_title, category)
                if event is not None and event.timestamp >= since:
                    events.append(event)

        return events

    @staticmethod
    def _clean_html(text: str) -> str:
        """去除 HTML 标签并折叠空白"""
        text = _HTML_TAG_RE.sub(" ", text or "")
        return _WHITESPACE_RE.sub(" ", text).strip()

    @staticmethod
    def _parse_timestamp(entry) -> Optional[datetime]:
        """将 feedparser 的时间结构转为系统本地时区的 naive datetime"""
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed:
            return None
        return datetime.fromtimestamp(calendar.timegm(parsed))

    def _parse_event(
        self,
        entry,
        feed_url: str,
        feed_title: str,
        category: str,
    ) -> Optional[Event]:
        """把 feedparser 条目转换为统一事件"""
        timestamp = self._parse_timestamp(entry)
        if timestamp is None:
            return None

        entry_id = str(entry.get("id", "") or entry.get("link", "") or "").strip()
        title = self._clean_html(str(entry.get("title", "") or "")).strip() or "未命名文章"
        link = str(entry.get("link", "") or "").strip() or None

        if entry_id:
            event_id = f"rss-{entry_id}"
        else:
            digest = hashlib.sha1(
                f"{feed_url}|{title}|{timestamp.isoformat()}".encode("utf-8")
            ).hexdigest()[:16]
            event_id = f"rss-{digest}"

        tags = []
        for tag in entry.get("tags", []) or []:
            term = str(tag.get("term", "") or "").strip()
            if term and term not in tags:
                tags.append(term)
        if category and category not in tags:
            tags.append(category)

        description = self._clean_html(
            str(entry.get("summary", "") or entry.get("description", "") or "")
        )

        return Event(
            id=event_id,
            timestamp=timestamp,
            source=self.name,
            event_type=EventType.READ,
            title=title,
            url=link,
            description=description or None,
            tags=tags,
            depth=Depth.BROWSE,
            metadata={
                "feed_url": feed_url,
                "feed_title": feed_title,
                "author": str(entry.get("author", "") or "").strip(),
                "entry_id": entry_id,
            },
        )

    def get_status(self) -> dict:
        status = super().get_status()
        status["icon"] = self.icon
        status["feed_count"] = len(self.feeds)
        return status
