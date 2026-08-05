"""YouTube 数据源插件测试（离线，httpx MockTransport）"""

import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import httpx  # noqa: E402

from core.models import Depth, EventType  # noqa: E402
from plugins.youtube.plugin import Plugin  # noqa: E402


def _plugin(**overrides) -> Plugin:
    plugin = Plugin()
    config = {
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "refresh_token": "test-refresh-token",
        "public_url": "http://localhost:5173",
        "takeout_max_mb": 20,
    }
    config.update(overrides)
    plugin.setup(config)
    return plugin


def _liked(video_id: str, published: str, title: str) -> dict:
    return {
        "snippet": {
            "publishedAt": published,
            "title": title,
            "channelId": "UC-demo",
            "channelTitle": "示例频道",
            "resourceId": {"kind": "youtube#video", "videoId": video_id},
        },
        "contentDetails": {"videoId": video_id},
    }


def _subscription(channel_id: str, published: str, title: str) -> dict:
    return {
        "snippet": {
            "publishedAt": published,
            "title": title,
            "resourceId": {"kind": "youtube#channel", "channelId": channel_id},
        }
    }


def _mock_transport():
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://oauth2.googleapis.com/token"):
            body = parse_qs(request.content.decode("utf-8"))
            if body.get("grant_type") == ["authorization_code"]:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "at-1",
                        "expires_in": 3600,
                        "refresh_token": "rt-1",
                    },
                )
            return httpx.Response(
                200, json={"access_token": "at-1", "expires_in": 3600}
            )
        if "/playlistItems" in url:
            if request.url.params.get("pageToken") == "NEXT":
                return httpx.Response(200, json={"items": []})
            return httpx.Response(
                200,
                json={
                    "items": [
                        _liked("vid-a", "2026-08-01T10:00:00Z", "Python 异步教程"),
                        _liked("vid-b", "2026-08-02T09:00:00Z", "FastAPI 实战"),
                    ],
                    "nextPageToken": "NEXT",
                },
            )
        if "/subscriptions" in url:
            return httpx.Response(
                200,
                json={
                    "items": [
                        _subscription(
                            "UC-new", "2026-08-01T11:00:00Z", "新技术频道"
                        ),
                        _subscription(
                            "UC-old", "2026-07-01T00:00:00Z", "旧订阅"
                        ),
                    ]
                },
            )
        if "/channels" in url:
            return httpx.Response(200, json={"items": [{"id": "UC-demo"}]})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _attach_mock(plugin: Plugin) -> Plugin:
    plugin.client = _mock_transport()
    return plugin


def test_build_auth_url_includes_pkce():
    plugin = _plugin()
    url = plugin.build_auth_url("state-1", "verifier-1")
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=test-client-id" in url
    assert (
        "redirect_uri=http%3A%2F%2Flocalhost%3A5173%2Fapi%2Fv1%2Fsources%2Fyoutube%2Fcallback"
        in url
    )
    assert "code_challenge=" in url
    assert "openid" in url
    assert "youtube.readonly" in url
    assert "drive.readonly" in url
    assert "code_challenge_method=S256" in url
    assert "state=state-1" in url
    assert "access_type=offline" in url


def test_exchange_code_returns_refresh_token():
    plugin = _attach_mock(_plugin())
    tokens = plugin.exchange_code("auth-code", "verifier-1")
    assert tokens["refresh_token"] == "rt-1"
    assert tokens["access_token"] == "at-1"


def test_fetch_liked_and_subscriptions_since():
    plugin = _attach_mock(_plugin())
    events = plugin.fetch(datetime(2026, 8, 1, 0, 0, 0))

    kinds = {event.metadata["kind"] for event in events}
    assert kinds == {"liked", "subscription"}
    assert [e.timestamp for e in events] == sorted(e.timestamp for e in events)
    assert events[0].source == "youtube"

    liked = [e for e in events if e.metadata["kind"] == "liked"]
    assert len(liked) == 2
    assert liked[0].id == "youtube-liked-vid-a"
    assert liked[0].event_type == EventType.BOOKMARK
    assert liked[0].depth == Depth.READ
    assert liked[0].url == "https://www.youtube.com/watch?v=vid-a"

    subs = [e for e in events if e.metadata["kind"] == "subscription"]
    assert len(subs) == 1
    assert subs[0].id == "youtube-sub-UC-new"
    assert subs[0].event_type == EventType.CREATE
    assert subs[0].title == "订阅了 新技术频道"


def test_fetch_requires_refresh_token():
    plugin = _attach_mock(_plugin(refresh_token=""))
    try:
        plugin.fetch(datetime(2026, 8, 1))
        raise AssertionError("缺少 refresh_token 时应抛出错误")
    except RuntimeError:
        pass


def test_test_connection():
    assert _attach_mock(_plugin()).test_connection() is True
    plugin = _plugin(refresh_token="")
    assert _attach_mock(plugin).test_connection() is False
    assert "refresh_token" in plugin.last_error


def test_takeout_parse_and_stable_ids():
    plugin = _plugin()
    payload = [
        {
            "header": "YouTube",
            "title": "Watched 大模型应用实践",
            "titleUrl": "https://www.youtube.com/watch?v=vid-1",
            "subtitles": [{"name": "科技频道", "url": "https://www.youtube.com/channel/UC-1"}],
            "time": "2026-08-01T12:30:45.000Z",
            "products": ["YouTube"],
        },
        {
            "header": "YouTube",
            "title": "Watched 短视频",
            "titleUrl": "https://www.youtube.com/shorts/short-1",
            "time": "2026-08-02T08:00:00Z",
        },
        {"title": "无时间记录"},
        "not-a-dict",
    ]
    events = plugin.parse_takeout(payload)
    assert len(events) == 2
    assert events[0].event_type == EventType.VIEW
    assert events[0].title == "大模型应用实践"
    assert events[0].metadata["channel"] == "科技频道"
    assert events[0].id == "youtube-takeout-vid-1-20260801123045"
    assert events[1].url == "https://www.youtube.com/shorts/short-1"
    assert events[1].id.startswith("youtube-takeout-short-1-")

    again = plugin.parse_takeout(payload[:1])
    assert again[0].id == events[0].id


def test_takeout_skip_non_list():
    plugin = _plugin()
    assert plugin.parse_takeout({"not": "list"}) == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 YouTube 插件测试通过！")
