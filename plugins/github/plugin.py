"""GitHub 数据源插件"""

from datetime import datetime
from typing import List

import httpx

from core.models import Event, EventType, Depth
from core.plugin_loader import DataSourcePlugin


class Plugin(DataSourcePlugin):
    """GitHub 活动记录插件"""

    @property
    def name(self) -> str:
        return "github"

    @property
    def display_name(self) -> str:
        return "GitHub 活动记录"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def icon(self) -> str:
        return "💻"

    @property
    def description(self) -> str:
        return "同步 GitHub 代码提交和项目活动"

    def __init__(self):
        self.token = ""
        self.username = ""
        self.include_repos: List[str] = []
        self.client: httpx.Client = None

    def setup(self, config: dict) -> None:
        self.token = config.get("token", "")
        self.username = config.get("username", "")
        self.include_repos = config.get("include_repos", [])

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "personal-profile-tool",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        self.client = httpx.Client(
            headers=headers,
            timeout=15.0,
        )

    def test_connection(self) -> bool:
        if not self.client:
            return False
        try:
            resp = self.client.get("https://api.github.com/user")
            return resp.status_code == 200
        except Exception:
            return False

    def fetch(self, since: datetime) -> List[Event]:
        """拉取 GitHub 事件"""
        events = []

        # 获取 push 事件（代码提交）
        events.extend(self._fetch_push_events(since))

        return events

    def _fetch_push_events(self, since: datetime) -> List[Event]:
        """拉取 push 事件"""
        events = []
        page = 1

        while page <= 5:  # 最多 5 页
            try:
                resp = self.client.get(
                    f"https://api.github.com/users/{self.username}/events",
                    params={"page": page, "per_page": 30},
                )
                if resp.status_code != 200:
                    break

                items = resp.json()
                if not items:
                    break

                for item in items:
                    event_time = datetime.fromisoformat(
                        item["created_at"].replace("Z", "+00:00")
                    )
                    if event_time.replace(tzinfo=None) < since:
                        return events

                    if item["type"] == "PushEvent":
                        event = self._parse_push_event(item)
                        if event:
                            events.append(event)

                page += 1
            except Exception:
                break

        return events

    def _parse_push_event(self, item: dict) -> Event:
        """解析 push 事件"""
        repo_name = item.get("repo", {}).get("name", "")
        payload = item.get("payload", {})
        commits = payload.get("commits", [])

        if not commits:
            return None

        # 取最新的 commit 信息
        latest_commit = commits[0]
        message = latest_commit.get("message", "")
        # 取 commit message 的第一行作为标题
        title = message.split("\n")[0] if message else "代码提交"

        # 计算总代码变更
        total_additions = 0
        total_deletions = 0
        for commit in commits:
            # GitHub events API 不直接返回增删行数
            # 这里简化处理
            pass

        timestamp = datetime.fromisoformat(
            item["created_at"].replace("Z", "+00:00")
        ).replace(tzinfo=None)

        return Event(
            id=f"github-{item['id']}",
            timestamp=timestamp,
            source="github",
            event_type=EventType.CREATE,
            title=title,
            url=f"https://github.com/{repo_name}/commit/{latest_commit.get('sha', '')}",
            description=message,
            tags=[],
            metadata={
                "repo": repo_name,
                "sha": latest_commit.get("sha", ""),
                "commit_count": len(commits),
                "author": latest_commit.get("author", {}).get("name", ""),
            },
        )

    def get_status(self) -> dict:
        status = super().get_status()
        status["icon"] = self.icon
        status["username"] = self.username
        return status

    def cleanup(self):
        if self.client:
            self.client.close()
