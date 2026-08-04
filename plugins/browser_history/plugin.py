"""浏览器历史数据源插件"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

from core.models import Event, EventType, Depth
from core.plugin_loader import DataSourcePlugin


class Plugin(DataSourcePlugin):
    """浏览器历史记录插件（Chrome/Firefox）"""

    @property
    def name(self) -> str:
        return "browser_history"

    @property
    def display_name(self) -> str:
        return "浏览器历史记录"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def icon(self) -> str:
        return "🌐"

    @property
    def description(self) -> str:
        return "同步 Chrome/Firefox 浏览器历史记录"

    def __init__(self):
        self.browser = "chrome"
        self.history_path = ""

    def setup(self, config: dict) -> None:
        self.browser = config.get("browser", "chrome")
        self.history_path = config.get("history_path", "auto")
        if self.history_path == "auto":
            self.history_path = self._detect_history_path()

    def _detect_history_path(self) -> str:
        """自动检测浏览器历史文件路径"""
        home = Path.home()

        if self.browser == "chrome":
            candidates = [
                home / ".config/google-chrome/Default/History",
                home / ".config/chromium/Default/History",
                home / "Library/Application Support/Google/Chrome/Default/History",
            ]
        elif self.browser == "firefox":
            # Firefox 需要查找 profiles 目录
            profiles_dir = home / ".mozilla/firefox"
            if profiles_dir.exists():
                for profile in profiles_dir.iterdir():
                    if profile.is_dir() and profile.name.endswith(".default-release"):
                        return str(profile / "places.sqlite")
            return ""
        else:
            return ""

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return ""

    def test_connection(self) -> bool:
        if not self.history_path:
            return False
        return Path(self.history_path).exists()

    def fetch(self, since: datetime) -> List[Event]:
        """读取浏览器历史数据库"""
        if not self.history_path:
            return []

        # 复制一份，避免锁定问题
        temp_path = self.history_path + ".temp"
        shutil.copy2(self.history_path, temp_path)

        try:
            return self._read_history(temp_path, since)
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def _read_history(self, db_path: str, since: datetime) -> List[Event]:
        """读取 SQLite 格式的浏览器历史"""
        events = []
        since_ts = since.timestamp() if since else 0

        # Chrome 时间戳从 1601 年开始，需要转换
        chrome_epoch_offset = 11644473600

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.execute(
                """SELECT url, title, visit_count, last_visit_time
                   FROM urls
                   WHERE last_visit_time > ?
                   ORDER BY last_visit_time DESC
                   LIMIT 500""",
                (int((since_ts + chrome_epoch_offset) * 1000000),),
            )

            for row in cursor:
                url, title, visit_count, last_visit_time = row
                # 转换 Chrome 时间戳
                ts = (last_visit_time / 1000000) - chrome_epoch_offset
                timestamp = datetime.fromtimestamp(ts)

                events.append(
                    Event(
                        id=f"browser-{hash(url)}-{int(ts)}",
                        timestamp=timestamp,
                        source="browser_history",
                        event_type=EventType.READ,
                        title=title or url,
                        url=url,
                        tags=[],
                        metadata={
                            "visit_count": visit_count,
                            "browser": self.browser,
                        },
                    )
                )
        finally:
            conn.close()

        return events

    def get_status(self) -> dict:
        status = super().get_status()
        status["icon"] = self.icon
        status["history_path"] = self.history_path
        status["available"] = bool(self.history_path)
        return status
