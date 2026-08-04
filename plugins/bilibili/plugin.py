"""哔哩哔哩数据源插件"""

from datetime import datetime
from typing import List

from core.models import Event, EventType, Depth
from core.plugin_loader import DataSourcePlugin
from plugins.bilibili.api import BilibiliAPI


class Plugin(DataSourcePlugin):
    """哔哩哔哩观看记录插件"""

    @property
    def name(self) -> str:
        return "bilibili"

    @property
    def display_name(self) -> str:
        return "哔哩哔哩观看记录"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def icon(self) -> str:
        return "📺"

    @property
    def description(self) -> str:
        return "同步 B站 视频观看历史记录"

    def __init__(self):
        self.api: BilibiliAPI = None

    def setup(self, config: dict) -> None:
        cookie = config.get("cookie", "")
        csrf = config.get("csrf", "")
        self.api = BilibiliAPI(cookie=cookie, csrf=csrf)

    def test_connection(self) -> bool:
        if not self.api:
            return False
        return self.api.test_connection()

    def fetch(self, since: datetime) -> List[Event]:
        """增量拉取 B站历史记录"""
        since_timestamp = int(since.timestamp()) if since else 0
        raw_items = self.api.fetch_all_history(since_timestamp=since_timestamp)

        events = []
        for item in raw_items:
            event = self._parse_event(item)
            if event:
                events.append(event)
        return events

    def _parse_event(self, item: dict) -> Event:
        """将 B站 API 返回转为统一 Event"""
        try:
            view_at = item.get("view_at", 0)
            if not view_at:
                return None

            timestamp = datetime.fromtimestamp(view_at)

            # 从 history 字段提取 bvid
            history = item.get("history", {})
            bvid = history.get("bvid", "")
            oid = history.get("oid", "")

            # 构建 URL
            if bvid:
                url = f"https://www.bilibili.com/video/{bvid}"
            elif item.get("uri"):
                url = item.get("uri")
            else:
                url = f"https://www.bilibili.com/video/{oid}"

            # 计算观看深度
            duration = item.get("duration", 0)
            progress = item.get("progress", 0)
            depth = self._calc_depth(duration, progress)

            # 计算完成度
            progress_ratio = progress / duration if duration > 0 else 0.0

            # 提取标签
            tags = []
            tag_name = item.get("tag_name", "")
            badge = item.get("badge", "")
            if tag_name:
                tags.append(tag_name)
            if badge:
                tags.append(badge)

            # 构建描述
            description = item.get("show_title", "") or item.get("new_desc", "")

            # 提取作者信息
            author_name = item.get("author_name", "")

            return Event(
                id=f"bilibili-{oid or bvid}-{view_at}",
                timestamp=timestamp,
                source="bilibili",
                event_type=EventType.VIEW,
                title=item.get("title", "未知标题"),
                url=url,
                description=description,
                tags=tags,
                duration=duration,
                progress=progress_ratio,
                depth=depth,
                metadata={
                    "bvid": bvid,
                    "oid": oid,
                    "author": author_name,
                    "cover": item.get("cover", ""),
                    "badge": badge,
                    "tag_name": tag_name,
                },
            )
        except Exception as e:
            print(f"[Bilibili] 解析事件失败: {e}")
            return None

    def _calc_depth(self, duration: int, progress: int) -> Depth:
        """计算观看深度"""
        if duration <= 0:
            return Depth.BROWSE

        ratio = progress / duration
        if ratio < 0.1:
            return Depth.SKIM
        elif ratio < 0.3:
            return Depth.BROWSE
        elif ratio < 0.7:
            return Depth.READ
        else:
            return Depth.DEEP

    def get_status(self) -> dict:
        status = super().get_status()
        status["icon"] = self.icon
        return status

    def cleanup(self):
        if self.api:
            self.api.close()
