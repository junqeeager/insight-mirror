"""YouTube 数据源插件

- OAuth2（youtube.readonly + drive.readonly + 基础身份）自动同步“喜欢的视频”
  与“订阅频道”；
- Google Takeout 导出的 watch-history.json 手动导入真实观看历史
  （YouTube Data API v3 不开放第三方读取观看历史）；
- 自动向 Google Takeout 请求只含观看历史的导出并导入（见 takeout.py）。
"""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from core.models import Depth, Event, EventType
from core.plugin_loader import DataSourcePlugin

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_BASE = "https://www.googleapis.com/youtube/v3"
SCOPE = (
    "https://www.googleapis.com/auth/youtube.readonly "
    "https://www.googleapis.com/auth/drive.readonly "
    "openid profile email"
)
OAUTH_TTL = timedelta(minutes=10)


class Plugin(DataSourcePlugin):
    """YouTube 观看行为插件：喜欢视频 + 订阅频道 + Takeout 观看历史。"""

    @property
    def name(self) -> str:
        return "youtube"

    @property
    def display_name(self) -> str:
        return "YouTube 观看行为"

    @property
    def version(self) -> str:
        return "1.2.0"

    @property
    def icon(self) -> str:
        return "▶️"

    @property
    def description(self) -> str:
        return "同步 YouTube 喜欢/订阅，并支持导入 Takeout 观看历史"

    def __init__(self):
        self.client_id = ""
        self.client_secret = ""
        self.refresh_token = ""
        self.public_url = ""
        self.takeout_max_mb = 20
        self.takeout_max_archive_mb = 200
        self.takeout_max_total_mb = 1024
        self.last_error = ""
        self.client: Optional[httpx.Client] = None

    def setup(self, config: dict) -> None:
        """配置插件；config 由全局配置与用户保存的凭据合并而成。"""
        self.client_id = str(config.get("client_id", "") or "")
        self.client_secret = str(config.get("client_secret", "") or "")
        self.refresh_token = str(config.get("refresh_token", "") or "")
        self.public_url = str(config.get("public_url", "") or "")
        try:
            self.takeout_max_mb = int(config.get("takeout_max_mb", 20) or 20)
        except (TypeError, ValueError):
            self.takeout_max_mb = 20
        try:
            self.takeout_max_archive_mb = int(
                config.get("takeout_max_archive_mb", 200) or 200
            )
        except (TypeError, ValueError):
            self.takeout_max_archive_mb = 200
        try:
            self.takeout_max_total_mb = int(
                config.get("takeout_max_total_mb", 1024) or 1024
            )
        except (TypeError, ValueError):
            self.takeout_max_total_mb = 1024
        if self.client is None:
            self.client = httpx.Client(timeout=20.0)

    def cleanup(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    # ---------- OAuth 2.0 PKCE ----------

    @staticmethod
    def _b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    def redirect_uri(self) -> str:
        """Google 回调地址：后端 /callback，由服务端直接换取 refresh_token。"""
        return f"{self.public_url.rstrip('/')}/api/v1/sources/youtube/callback"

    def build_auth_url(self, state: str, code_verifier: str) -> str:
        """构造带 PKCE 的 Google 授权 URL。"""
        code_challenge = self._b64url(
            hashlib.sha256(code_verifier.encode("utf-8")).digest()
        )
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri(),
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        return f"{AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str, code_verifier: str) -> dict:
        """用授权码换取令牌；Google 首次授权必须返回 refresh_token。"""
        if not self.client_id or not self.client_secret:
            raise RuntimeError("未配置 YouTube OAuth 凭据")
        resp = self.client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri(),
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("refresh_token"):
            raise RuntimeError("Google 未返回 refresh_token，请撤销本应用授权后重试")
        return data

    def _refresh_access_token(self) -> str:
        """用已保存的 refresh_token 换取新的 access_token。"""
        if not self.refresh_token:
            raise RuntimeError("未连接 YouTube（缺少 refresh_token）")
        if not self.client_id or not self.client_secret:
            raise RuntimeError("未配置 YouTube OAuth 凭据")
        resp = self.client.post(
            TOKEN_URL,
            data={
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    # ---------- DataSourcePlugin 接口 ----------

    def test_connection(self) -> bool:
        """有 refresh_token 且能刷新并访问本人频道信息时视为连接成功。"""
        self.last_error = ""
        if not self.refresh_token:
            self.last_error = "未连接 YouTube（缺少 refresh_token）"
            return False
        try:
            token = self._refresh_access_token()
            resp = self.client.get(
                f"{API_BASE}/channels",
                params={"part": "id", "mine": "true", "maxResults": 1},
                headers=self._headers(token),
            )
            if resp.status_code == 200:
                return True
            self.last_error = self._api_error(resp) or (
                f"YouTube API 返回 {resp.status_code}"
            )
            return False
        except Exception as exc:
            self.last_error = f"连接失败: {exc}"
            return False

    @staticmethod
    def _api_error(resp: httpx.Response) -> str:
        """从 YouTube API 错误响应里提取简短可读原因。"""
        try:
            message = (resp.json().get("error") or {}).get("message", "")
        except Exception:
            return ""
        if not message:
            return ""
        return message if len(message) <= 300 else message[:297] + "..."

    def fetch(self, since: datetime) -> List[Event]:
        """全量拉取喜欢的视频与订阅（自动刷新 access token，幂等去重）。"""
        token = self._refresh_access_token()
        headers = self._headers(token)
        # 喜欢/订阅列表整体较小，每次全量拉取并通过稳定主键幂等写入，
        # 避免增量时间窗把连接前的历史喜欢/订阅漏掉。
        events = self._fetch_liked(None, headers)
        events.extend(self._fetch_subscriptions(None, headers))
        events.sort(key=lambda event: event.timestamp)
        return events

    def get_status(self) -> dict:
        status = super().get_status()
        status["connected"] = bool(self.refresh_token)
        status["last_error"] = self.last_error
        return status

    # ---------- YouTube Data API 拉取 ----------

    @staticmethod
    def _headers(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def _fetch_liked(
        self, since: Optional[datetime], headers: dict
    ) -> List[Event]:
        """分页拉取喜欢视频播放列表（playlistId=LL）。"""
        events = []
        page_token = ""
        while True:
            params = {
                "part": "snippet,contentDetails",
                "playlistId": "LL",
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            resp = self.client.get(
                f"{API_BASE}/playlistItems", params=params, headers=headers
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            for item in data.get("items", []):
                event = self._parse_liked_item(item, since)
                if event:
                    events.append(event)
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break
        return events

    def _parse_liked_item(
        self, item: dict, since: Optional[datetime]
    ) -> Optional[Event]:
        """把 playlistItem 转为“喜欢视频”事件。"""
        snippet = item.get("snippet", {}) or {}
        content = item.get("contentDetails", {}) or {}
        resource = snippet.get("resourceId", {}) or {}
        video_id = content.get("videoId") or resource.get("videoId", "")
        published = self._parse_time(snippet.get("publishedAt", ""))
        if not video_id or published is None or (
            since is not None and published < since
        ):
            return None
        title = str(snippet.get("title") or "未命名视频").strip()
        return Event(
            id=f"youtube-liked-{video_id}",
            timestamp=published,
            source="youtube",
            event_type=EventType.BOOKMARK,
            title=title,
            url=f"https://www.youtube.com/watch?v={video_id}",
            description=str(snippet.get("description") or "").strip() or None,
            tags=[],
            depth=Depth.READ,
            metadata={
                "video_id": video_id,
                "channel": str(snippet.get("channelTitle") or ""),
                "channel_id": str(snippet.get("channelId") or ""),
                "kind": "liked",
            },
        )

    def _fetch_subscriptions(
        self, since: Optional[datetime], headers: dict
    ) -> List[Event]:
        """分页拉取本人订阅的频道。"""
        events = []
        page_token = ""
        while True:
            params = {"part": "snippet", "mine": "true", "maxResults": 50}
            if page_token:
                params["pageToken"] = page_token
            resp = self.client.get(
                f"{API_BASE}/subscriptions", params=params, headers=headers
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            for item in data.get("items", []):
                event = self._parse_subscription_item(item, since)
                if event:
                    events.append(event)
            page_token = data.get("nextPageToken", "")
            if not page_token:
                break
        return events

    def _parse_subscription_item(
        self, item: dict, since: Optional[datetime]
    ) -> Optional[Event]:
        """把 subscription 转为“订阅频道”事件。"""
        snippet = item.get("snippet", {}) or {}
        resource = snippet.get("resourceId", {}) or {}
        channel_id = resource.get("channelId", "")
        published = self._parse_time(snippet.get("publishedAt", ""))
        if not channel_id or published is None or (
            since is not None and published < since
        ):
            return None
        channel = str(snippet.get("title") or "未知频道").strip()
        return Event(
            id=f"youtube-sub-{channel_id}",
            timestamp=published,
            source="youtube",
            event_type=EventType.CREATE,
            title=f"订阅了 {channel}",
            url=f"https://www.youtube.com/channel/{channel_id}",
            description=None,
            tags=[],
            depth=Depth.BROWSE,
            metadata={"channel_id": channel_id, "channel": channel, "kind": "subscription"},
        )

    # ---------- Takeout 观看历史导入 ----------

    def parse_takeout(self, payload: object) -> List[Event]:
        """解析 Google Takeout watch-history.json（JSON 数组）。"""
        if not isinstance(payload, list):
            return []
        events = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            event = self._parse_takeout_entry(entry)
            if event:
                events.append(event)
        return events

    def _parse_takeout_entry(self, entry: dict) -> Optional[Event]:
        """把单条 Takeout 记录转为“观看”事件。"""
        raw_title = str(entry.get("title") or "").strip()
        if not raw_title:
            return None
        title = raw_title[7:].strip() if raw_title.startswith("Watched ") else raw_title
        title_url = str(entry.get("titleUrl") or "")
        utc_dt = self._parse_utc(entry.get("time", ""))
        if utc_dt is None:
            return None
        watched_at = utc_dt.astimezone().replace(tzinfo=None)

        video_id = self._extract_video_id(title_url)
        if not video_id:
            digest = hashlib.sha256(f"{title_url}|{raw_title}".encode("utf-8")).hexdigest()
            video_id = f"v{digest[:12]}"
        time_key = utc_dt.strftime("%Y%m%d%H%M%S")
        event_id = f"youtube-takeout-{video_id}-{time_key}"

        subtitles = entry.get("subtitles") or []
        channel = ""
        if isinstance(subtitles, list) and subtitles and isinstance(subtitles[0], dict):
            channel = str(subtitles[0].get("name") or "").strip()

        url = title_url
        if not url and not video_id.startswith("v"):
            url = f"https://www.youtube.com/watch?v={video_id}"

        return Event(
            id=event_id,
            timestamp=watched_at,
            source="youtube",
            event_type=EventType.VIEW,
            title=title or "未知视频",
            url=url or None,
            description=None,
            tags=[],
            depth=Depth.BROWSE,
            metadata={"channel": channel, "kind": "takeout"},
        )

    @staticmethod
    def _extract_video_id(url: str) -> str:
        """从 watch/shorts/youtu.be 链接中提取视频 ID。"""
        if not url:
            return ""
        parsed = urlparse(url)
        query_id = parse_qs(parsed.query).get("v")
        if query_id:
            return query_id[0]
        path = parsed.path.strip("/")
        if parsed.hostname and "youtu.be" in parsed.hostname:
            return path.split("/")[0]
        for prefix in ("shorts/", "embed/", "live/"):
            if path.startswith(prefix):
                return path[len(prefix):].split("/")[0]
        return ""

    @staticmethod
    def _parse_time(value) -> Optional[datetime]:
        """解析 ISO 时间并转为本地 naive datetime（与现有插件一致）。"""
        utc_dt = Plugin._parse_utc(value)
        if utc_dt is None:
            return None
        return utc_dt.astimezone().replace(tzinfo=None)

    @staticmethod
    def _parse_utc(value) -> Optional[datetime]:
        """解析 ISO 时间并归一化为 UTC aware datetime。"""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
