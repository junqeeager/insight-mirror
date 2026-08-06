"""FastAPI 接口测试（TestClient + 临时数据库，覆盖登录鉴权与用户隔离）"""

import atexit
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 必须在导入 app 前设置；deps.get_db_url 每次请求读取该环境变量
_tmp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["PROFILE_DB_PATH"] = _tmp_file.name
os.environ["YOUTUBE_CLIENT_ID"] = "test-client-id"
os.environ["YOUTUBE_CLIENT_SECRET"] = "test-client-secret"
_tmp_file.close()


def _cleanup():
    Path(os.environ["PROFILE_DB_PATH"]).unlink(missing_ok=True)


atexit.register(_cleanup)

from fastapi.testclient import TestClient  # noqa: E402

from api.main import app  # noqa: E402
import api.routers.youtube as youtube_router  # noqa: E402
import api.routers.sources as sources_router  # noqa: E402
from core.auth import hash_password  # noqa: E402
from core.database import Database  # noqa: E402
from core.models import Event, EventType  # noqa: E402
from analysis.profile import ProfileGenerator  # noqa: E402

client = TestClient(app)

_ALICE_ID = ""
_ADMIN_ID = ""


def _seed():
    global _ALICE_ID, _ADMIN_ID
    db = Database(os.environ["PROFILE_DB_PATH"])
    db.init_tables()
    _ADMIN_ID = db.create_user(
        "admin", hash_password("admin-pass-123"), role="admin", status="active"
    )
    _ALICE_ID = db.create_user(
        "alice", hash_password("alice-pass-123"), role="user", status="active"
    )
    titles = ["Python 编程入门教程", "FastAPI 实战开发", "机器学习基础课程"]
    db.insert_events(
        [
            Event(
                id=f"api-ev-{i}",
                timestamp=datetime(2026, 8, 1, 10, 0, i),
                source="test",
                event_type=EventType.VIEW,
                title=title,
                tags=["编程", "教程"],
            )
            for i, title in enumerate(titles)
        ],
        _ALICE_ID,
    )
    db.close()


def _login(username: str, password: str) -> str:
    r = client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_seed()
_ADMIN_TOKEN = _login("admin", "admin-pass-123")
_ALICE_TOKEN = _login("alice", "alice-pass-123")


def test_health():
    r = client.get("/health")
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "ok"}


def test_report_endpoint_formats():
    db = Database(os.environ["PROFILE_DB_PATH"])
    db.init_tables()
    ProfileGenerator(db, {}).generate(user_id=_ALICE_ID, period="weekly", persist=True)
    db.close()

    for fmt, media in (
        ("html", "text/html"),
        ("txt", "text/plain"),
        ("json", "application/json"),
    ):
        r = client.get(
            "/api/v1/report",
            params={"period": "weekly", "format": fmt},
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 200, r.text
        assert media in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]

    r = client.get(
        "/api/v1/report",
        params={"period": "monthly", "format": "html"},
        headers=_auth(_ALICE_TOKEN),
    )
    assert r.status_code == 404


def test_account_password_export_and_delete():
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "carol", "password": "carol-pass-123"},
    )
    assert r.status_code == 200
    carol_id = r.json()["id"]
    client.patch(
        f"/api/v1/admin/users/{carol_id}",
        json={"status": "active"},
        headers=_auth(_ADMIN_TOKEN),
    )
    token = _login("carol", "carol-pass-123")

    # 错误旧密码被拒绝
    r = client.post(
        "/api/v1/account/password",
        json={"old_password": "wrong", "new_password": "carol-new-pass"},
        headers=_auth(token),
    )
    assert r.status_code == 400

    r = client.post(
        "/api/v1/account/password",
        json={"old_password": "carol-pass-123", "new_password": "carol-new-pass"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    # 改密后旧会话失效，新密码可登录
    r = client.get("/api/v1/stats", headers=_auth(token))
    assert r.status_code == 401
    token = _login("carol", "carol-new-pass")

    # 服务端导出 CSV / JSON
    r = client.post(
        "/api/v1/account/export",
        params={"format": "csv"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert "id,timestamp,source" in r.text
    r = client.post(
        "/api/v1/account/export",
        params={"format": "json"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)

    # 注销账号并物理删除数据
    r = client.request(
        "DELETE",
        "/api/v1/account",
        json={"password": "wrong"},
        headers=_auth(token),
    )
    assert r.status_code == 400
    r = client.request(
        "DELETE",
        "/api/v1/account",
        json={"password": "carol-new-pass"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "carol", "password": "carol-new-pass"},
    )
    assert r.status_code == 401


def test_spa_served_and_fallback_when_dist_exists():
    """React 构建产物存在时，同源托管 SPA 并提供浏览器路由回退。"""
    from api.main import WEB_DIST

    if not WEB_DIST.is_dir():
        return
    r = client.get("/")
    assert r.status_code == 200
    assert 'id="root"' in r.text
    r = client.get("/time")
    assert r.status_code == 200, r.text
    assert 'id="root"' in r.text
    # 带扩展名的旧静态资源路径不应回退到 index.html，避免旧前端缓存混跑
    r = client.get("/static/js/content_main.js")
    assert r.status_code == 404
    assert r.headers.get("clear-site-data") == '"cache"'
    r = client.get("/api/v1/definitely-not-found")
    assert r.status_code == 404


def test_unauthorized_returns_401():
    r = client.get("/api/v1/events")
    assert r.status_code == 401


def test_register_pending_and_admin_approve():
    r = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "password": "bob-pass-123"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"
    bob_id = r.json()["id"]

    r = client.post(
        "/api/v1/auth/login", json={"username": "bob", "password": "bob-pass-123"}
    )
    assert r.status_code == 403

    # 普通用户不能访问管理员接口
    r = client.get("/api/v1/admin/users", headers=_auth(_ALICE_TOKEN))
    assert r.status_code == 403

    # 管理员批准后可以登录
    r = client.patch(
        f"/api/v1/admin/users/{bob_id}",
        json={"status": "active"},
        headers=_auth(_ADMIN_TOKEN),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "active"

    r = client.post(
        "/api/v1/auth/login", json={"username": "bob", "password": "bob-pass-123"}
    )
    assert r.status_code == 200, r.text


def test_events_scoped_by_user():
    r = client.get("/api/v1/events", params={"limit": 100}, headers=_auth(_ALICE_TOKEN))
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert data[0]["source"] == "test"

    # 管理员看不到 alice 的数据
    r = client.get("/api/v1/events", params={"limit": 100}, headers=_auth(_ADMIN_TOKEN))
    assert r.status_code == 200
    assert r.json() == []


def test_stats_scoped_by_user():
    r = client.get("/api/v1/stats", headers=_auth(_ALICE_TOKEN))
    assert r.status_code == 200
    assert r.json()["total"] == 3

    r = client.get("/api/v1/stats", headers=_auth(_ADMIN_TOKEN))
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_topics_and_latest_profile_scoped():
    db = Database(os.environ["PROFILE_DB_PATH"])
    db.init_tables()
    ProfileGenerator(db, {}).generate(user_id=_ALICE_ID, period="weekly", persist=True)
    db.close()

    r = client.get("/api/v1/topics", headers=_auth(_ALICE_TOKEN))
    assert r.status_code == 200
    assert r.json(), "topics 不应为空"

    r = client.get(
        "/api/v1/profile/latest", params={"period": "weekly"}, headers=_auth(_ALICE_TOKEN)
    )
    assert r.status_code == 200
    assert r.json()["total_events"] == 3

    r = client.get(
        "/api/v1/profile/latest", params={"period": "weekly"}, headers=_auth(_ADMIN_TOKEN)
    )
    assert r.status_code == 404


def test_refresh_task():
    r = client.post(
        "/api/v1/profile/refresh",
        params={"period": "weekly"},
        headers=_auth(_ALICE_TOKEN),
    )
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    body = {}
    for _ in range(60):
        s = client.get(f"/api/v1/profile/refresh/{task_id}", headers=_auth(_ALICE_TOKEN))
        assert s.status_code == 200
        body = s.json()
        if body["status"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert body["status"] == "done", body
    assert body["profile_id"]


def test_graph_endpoint_and_cache():
    r = client.get(
        "/api/v1/graph", params={"window_days": 90}, headers=_auth(_ALICE_TOKEN)
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"nodes", "edges"}
    assert body["nodes"], "图谱节点不应为空"
    assert body["edges"], "图谱边不应为空"

    r2 = client.get(
        "/api/v1/graph", params={"window_days": 90}, headers=_auth(_ALICE_TOKEN)
    )
    assert r2.status_code == 200
    assert r2.json() == body


def test_graph_invalid_window():
    r = client.get(
        "/api/v1/graph", params={"window_days": 0}, headers=_auth(_ALICE_TOKEN)
    )
    assert r.status_code == 422


def test_logout_invalidates_token():
    token = _login("alice", "alice-pass-123")
    r = client.post("/api/v1/auth/logout", headers=_auth(token))
    assert r.status_code == 200
    r = client.get("/api/v1/stats", headers=_auth(token))
    assert r.status_code == 401


def test_login_rate_limit_returns_429():
    for _ in range(5):
        r = client.post(
            "/api/v1/auth/login",
            json={"username": "ratelimit-user", "password": "wrong-pass-123"},
        )
        assert r.status_code == 401
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "ratelimit-user", "password": "wrong-pass-123"},
    )
    assert r.status_code == 429
    assert "过于频繁" in r.json()["detail"]


def test_security_headers_and_no_wildcard_cors():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"
    assert r.headers.get("content-security-policy")
    assert "access-control-allow-origin" not in r.headers


def test_youtube_auth_url_requires_login():
    r = client.get("/api/v1/sources/youtube/auth-url")
    assert r.status_code == 401


def test_youtube_auth_url_and_token_exchange():
    import json
    from urllib.parse import parse_qs, urlparse

    r = client.get(
        "/api/v1/sources/youtube/auth-url", headers=_auth(_ALICE_TOKEN)
    )
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "client_id=test-client-id" in url
    assert "code_challenge=" in url
    state = parse_qs(urlparse(url).query)["state"][0]

    class FakePlugin:
        def exchange_code(self, code, verifier):
            assert code == "the-code"
            assert verifier
            return {"refresh_token": "rt-secret", "access_token": "at-1"}

    original = youtube_router._plugin_for
    youtube_router._plugin_for = lambda db, user_id, config: FakePlugin()
    try:
        r = client.post(
            "/api/v1/sources/youtube/token",
            json={"code": "the-code", "state": state},
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        db = Database(os.environ["PROFILE_DB_PATH"])
        saved = db.get_source_config(_ALICE_ID, "youtube")
        db.close()
        assert saved is not None
        assert saved["enabled"] is True
        assert saved["config"]["refresh_token"].startswith("enc:")
        assert "rt-secret" not in json.dumps(saved["config"])

        # 同一 state 只能消费一次
        r = client.post(
            "/api/v1/sources/youtube/token",
            json={"code": "the-code", "state": state},
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 400
    finally:
        youtube_router._plugin_for = original


def test_youtube_callback_exchanges_and_redirects():
    from urllib.parse import parse_qs, urlparse

    r = client.get(
        "/api/v1/sources/youtube/auth-url", headers=_auth(_ALICE_TOKEN)
    )
    assert r.status_code == 200
    state = parse_qs(urlparse(r.json()["url"]).query)["state"][0]

    class FakePlugin:
        def exchange_code(self, code, verifier):
            assert code == "callback-code"
            assert verifier
            return {"refresh_token": "rt-callback"}

    original = youtube_router._plugin_for
    youtube_router._plugin_for = lambda db, user_id, config: FakePlugin()
    try:
        r = client.get(
            "/api/v1/sources/youtube/callback",
            params={"code": "callback-code", "state": state},
            follow_redirects=False,
        )
        assert r.status_code in (302, 307)
        assert "youtube=ok" in r.headers["location"]

        db = Database(os.environ["PROFILE_DB_PATH"])
        saved = db.get_source_config(_ALICE_ID, "youtube")
        db.close()
        assert saved is not None
        assert saved["enabled"] is True
        assert saved["config"]["refresh_token"].startswith("enc:")

        # 无效 state / 用户拒绝都回到错误提示
        r = client.get(
            "/api/v1/sources/youtube/callback",
            params={"code": "x", "state": "bad-state"},
            follow_redirects=False,
        )
        assert "youtube=error" in r.headers["location"]

        r = client.get(
            "/api/v1/sources/youtube/callback",
            params={"error": "access_denied", "error_description": "用户拒绝"},
            follow_redirects=False,
        )
        assert "youtube=error" in r.headers["location"]
        message = parse_qs(urlparse(r.headers["location"]).query).get("message")
        assert message == ["用户拒绝"]
    finally:
        youtube_router._plugin_for = original


def test_youtube_test_connection_reports_detail():
    class FakePlugin:
        last_error = "YouTube Data API 未启用"

        def test_connection(self):
            return False

    class FakeManager:
        def __init__(self, plugins_dir, config):
            self.plugins_dir = plugins_dir
            self.config = config

        def discover(self):
            return []

        def load(self, source):
            return FakePlugin()

    original = sources_router.PluginManager
    sources_router.PluginManager = FakeManager
    try:
        r = client.post(
            "/api/v1/sources/youtube/test", headers=_auth(_ALICE_TOKEN)
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert body["message"] == "YouTube Data API 未启用"
    finally:
        sources_router.PluginManager = original


def test_youtube_takeout_import_and_validation():
    import json

    class FakePlugin:
        takeout_max_mb = 20

        def parse_takeout(self, payload):
            return [
                Event(
                    id="youtube-api-ev-1",
                    timestamp=datetime(2026, 8, 1, 10, 0),
                    source="youtube",
                    event_type=EventType.VIEW,
                    title="API 测试观看记录",
                ),
                Event(
                    id="youtube-api-ev-2",
                    timestamp=datetime(2026, 8, 2, 10, 0),
                    source="youtube",
                    event_type=EventType.BOOKMARK,
                    title="API 测试喜欢视频",
                ),
            ]

    original = youtube_router._plugin_for
    youtube_router._plugin_for = lambda db, user_id, config: FakePlugin()
    try:
        payload = json.dumps(
            [{"title": "Watched 测试", "time": "2026-08-01T10:00:00Z"}]
        ).encode("utf-8")
        r = client.post(
            "/api/v1/sources/youtube/takeout",
            files={"file": ("watch-history.json", payload, "application/json")},
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"received": 1, "parsed": 2, "imported": 2}

        db = Database(os.environ["PROFILE_DB_PATH"])
        events = db.get_events(_ALICE_ID, source="youtube")
        db.close()
        assert {e.id for e in events} == {"youtube-api-ev-1", "youtube-api-ev-2"}

        # 非法 JSON 拒绝
        r = client.post(
            "/api/v1/sources/youtube/takeout",
            files={"file": ("bad.json", b"not-json", "application/json")},
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 400

        # 超过大小限制拒绝
        class TinyPlugin:
            takeout_max_mb = 0

            def parse_takeout(self, payload):
                return []

        youtube_router._plugin_for = lambda db, user_id, config: TinyPlugin()
        r = client.post(
            "/api/v1/sources/youtube/takeout",
            files={"file": ("big.json", b"[]", "application/json")},
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 400
    finally:
        youtube_router._plugin_for = original


def test_youtube_takeout_export_task_lifecycle():
    """自动导出：一键启动 → 后台任务完成 → 状态可查询且用户隔离。"""

    class FakeTakeoutPlugin:
        refresh_token = "test-refresh"
        takeout_max_archive_mb = 200
        takeout_max_total_mb = 1024

        def _refresh_access_token(self):
            return "test-access"

        def parse_takeout(self, payload):
            return [
                Event(
                    id=f"youtube-takeout-api-{i}",
                    timestamp=datetime(2026, 8, 1, 10, 0),
                    source="youtube",
                    event_type=EventType.VIEW,
                    title=entry.get("title", "Watched 测试"),
                )
                for i, entry in enumerate(payload)
            ]

        def cleanup(self):
            pass

    class FakeTakeoutExporter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.closed = False

        def create_export(self):
            return "batch-api-test"

        def poll_until_ready(self, export_id, progress=None):
            if progress:
                progress("Google 打包完成")
            return {
                "status": "COMPLETED",
                "files": [
                    {"downloadUrl": "https://takeout.example.com/test.zip"}
                ],
            }

        def download_archives(self, data, target_dir=None, progress=None):
            return []

        def extract_watch_history(self, archive_paths):
            return [
                {
                    "title": "Watched 自动导出测试",
                    "time": "2026-08-01T10:00:00Z",
                }
            ]

        def close(self):
            self.closed = True

    original_plugin = youtube_router._plugin_for
    original_exporter = youtube_router.TakeoutExporter
    youtube_router._plugin_for = (
        lambda db, user_id, config: FakeTakeoutPlugin()
    )
    youtube_router.TakeoutExporter = FakeTakeoutExporter
    try:
        r = client.post(
            "/api/v1/sources/youtube/takeout/export",
            headers=_auth(_ADMIN_TOKEN),
        )
        assert r.status_code == 202, r.text
        task_id = r.json()["task_id"]

        body = {}
        for _ in range(50):
            r = client.get(
                f"/api/v1/sources/youtube/takeout/export/{task_id}",
                headers=_auth(_ADMIN_TOKEN),
            )
            assert r.status_code == 200, r.text
            body = r.json()
            if body["status"] != "running":
                break
            time.sleep(0.1)
        assert body["status"] == "done", body
        assert body["imported"] == 1
        assert "已导入 1 条" in body["message"]
        assert body["batch_id"] == "batch-api-test"
        assert "画像已重新生成" in body["message"]

        # 自动获取的观看历史已持久化到用户目录
        store = youtube_router._user_takeout_dir(
            youtube_router.get_config(), _ADMIN_ID
        )
        batch_dir = store / "batch-api-test"
        assert (batch_dir / "watch-history.json").is_file()
        meta = youtube_router._read_takeout_meta(batch_dir)
        assert meta["record_count"] == 1
        assert meta["imported"] == 1

        # 用户隔离：其他用户不能读该任务
        r = client.get(
            f"/api/v1/sources/youtube/takeout/export/{task_id}",
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 404
    finally:
        youtube_router._plugin_for = original_plugin
        youtube_router.TakeoutExporter = original_exporter
        store = youtube_router._user_takeout_dir(
            youtube_router.get_config(), _ADMIN_ID
        )
        shutil.rmtree(store, ignore_errors=True)


def test_youtube_takeout_history_list_import_download():
    """保存的自动获取历史：列表、重新导入（幂等）、下载、用户隔离。"""

    class FakePlugin:
        takeout_max_mb = 20

        def parse_takeout(self, payload):
            return [
                Event(
                    id=f"youtube-saved-{i}",
                    timestamp=datetime(2026, 8, 1, 10, 0),
                    source="youtube",
                    event_type=EventType.VIEW,
                    title=entry.get("title", "Watched 保存记录"),
                )
                for i, entry in enumerate(payload)
            ]

    original = youtube_router._plugin_for
    youtube_router._plugin_for = lambda db, user_id, config: FakePlugin()
    config = youtube_router.get_config()
    payload = [
        {
            "title": "Watched 已保存记录",
            "titleUrl": "https://www.youtube.com/watch?v=saved123",
            "time": "2026-08-01T10:00:00Z",
        }
    ]
    youtube_router._save_takeout_payload(
        config, _ADMIN_ID, "batch-saved-1", payload
    )
    try:
        # 列表
        r = client.get(
            "/api/v1/sources/youtube/takeout/history",
            headers=_auth(_ADMIN_TOKEN),
        )
        assert r.status_code == 200
        items = r.json()
        assert any(item["batch_id"] == "batch-saved-1" for item in items)

        # 重新导入
        r = client.post(
            "/api/v1/sources/youtube/takeout/history/batch-saved-1/import",
            headers=_auth(_ADMIN_TOKEN),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body == {"received": 1, "parsed": 1, "imported": 1}
        db = Database(os.environ["PROFILE_DB_PATH"])
        events = db.get_events(_ADMIN_ID, source="youtube")
        db.close()
        assert any(e.id == "youtube-saved-0" for e in events)

        # 幂等：重复导入返回 0
        r = client.post(
            "/api/v1/sources/youtube/takeout/history/batch-saved-1/import",
            headers=_auth(_ADMIN_TOKEN),
        )
        assert r.status_code == 200
        assert r.json()["imported"] == 0

        # 下载
        r = client.get(
            "/api/v1/sources/youtube/takeout/history/batch-saved-1/download",
            headers=_auth(_ADMIN_TOKEN),
        )
        assert r.status_code == 200
        assert "watch-history" in r.headers["content-disposition"]
        assert r.json() == payload

        # 用户隔离：其他用户看不到也不能导入
        r = client.get(
            "/api/v1/sources/youtube/takeout/history",
            headers=_auth(_ALICE_TOKEN),
        )
        assert all(
            item["batch_id"] != "batch-saved-1" for item in r.json()
        )
        r = client.post(
            "/api/v1/sources/youtube/takeout/history/batch-saved-1/import",
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 404
        r = client.get(
            "/api/v1/sources/youtube/takeout/history/batch-saved-1/download",
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 404
    finally:
        youtube_router._plugin_for = original
        shutil.rmtree(
            youtube_router._user_takeout_dir(config, _ADMIN_ID),
            ignore_errors=True,
        )


def test_youtube_takeout_export_requires_connection():
    class NoTokenPlugin:
        refresh_token = ""

    original = youtube_router._plugin_for
    youtube_router._plugin_for = lambda db, user_id, config: NoTokenPlugin()
    try:
        r = client.post(
            "/api/v1/sources/youtube/takeout/export",
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 400, r.text
        assert "未连接 YouTube" in r.json()["detail"]
    finally:
        youtube_router._plugin_for = original


def test_youtube_takeout_export_empty_archive_errors_and_keeps_file():
    """导出成功但归档为空时任务报错，且保留文件供手动处理。"""
    db = Database(os.environ["PROFILE_DB_PATH"])
    erin_id = db.create_user(
        "erin", hash_password("erin-pass-123"), role="user", status="active"
    )
    db.close()
    erin_token = _login("erin", "erin-pass-123")

    class EmptyTakeoutPlugin:
        refresh_token = "test-refresh"
        takeout_max_archive_mb = 200
        takeout_max_total_mb = 1024

        def _refresh_access_token(self):
            return "test-access"

        def parse_takeout(self, payload):
            return []

        def cleanup(self):
            pass

    class EmptyTakeoutExporter:
        def __init__(self, **kwargs):
            pass

        def create_export(self):
            return "batch-empty"

        def poll_until_ready(self, export_id, progress=None):
            return {"status": "COMPLETED", "archives": []}

        def download_archives(self, data, target_dir=None, progress=None):
            return []

        def extract_watch_history(self, archive_paths):
            return []

        def close(self):
            pass

    original_plugin = youtube_router._plugin_for
    original_exporter = youtube_router.TakeoutExporter
    youtube_router._plugin_for = (
        lambda db, user_id, config: EmptyTakeoutPlugin()
    )
    youtube_router.TakeoutExporter = EmptyTakeoutExporter
    try:
        r = client.post(
            "/api/v1/sources/youtube/takeout/export",
            headers=_auth(erin_token),
        )
        assert r.status_code == 202, r.text
        task_id = r.json()["task_id"]

        body = {}
        for _ in range(50):
            r = client.get(
                f"/api/v1/sources/youtube/takeout/export/{task_id}",
                headers=_auth(erin_token),
            )
            assert r.status_code == 200, r.text
            body = r.json()
            if body["status"] != "running":
                break
            time.sleep(0.1)
        assert body["status"] == "error", body
        assert "未找到 watch-history.json" in (body.get("error") or "")

        # 空文件仍保留，方便手动排查
        batch_dir = youtube_router._batch_takeout_dir(
            youtube_router.get_config(), erin_id, "batch-empty"
        )
        assert (batch_dir / "watch-history.json").is_file()
        assert youtube_router._read_takeout_payload(
            youtube_router.get_config(), erin_id, "batch-empty"
        ) == []
    finally:
        youtube_router._plugin_for = original_plugin
        youtube_router.TakeoutExporter = original_exporter
        shutil.rmtree(
            youtube_router._user_takeout_dir(
                youtube_router.get_config(), erin_id
            ),
            ignore_errors=True,
        )


def test_youtube_takeout_export_cooldown():
    """30 分钟冷却：刚结束过的自动导出再次触发返回 409。"""
    db = Database(os.environ["PROFILE_DB_PATH"])
    db.create_task("cooldown-task", _ALICE_ID, "takeout_export", {})
    db.update_task(
        "cooldown-task",
        status="done",
        result={"message": "已导入 0 条观看记录"},
    )
    db.close()

    class FakePlugin:
        refresh_token = "test-refresh"

    original = youtube_router._plugin_for
    youtube_router._plugin_for = lambda db, user_id, config: FakePlugin()
    try:
        r = client.post(
            "/api/v1/sources/youtube/takeout/export",
            headers=_auth(_ALICE_TOKEN),
        )
        assert r.status_code == 409, r.text
        assert "分钟内已执行过" in r.json()["detail"]
    finally:
        youtube_router._plugin_for = original


def test_youtube_takeout_export_error_task_allows_retry():
    """上次自动导出失败时不触发 5 分钟冷却，可立即重试。"""
    db = Database(os.environ["PROFILE_DB_PATH"])
    fiona_id = db.create_user(
        "fiona", hash_password("fiona-pass-123"), role="user", status="active"
    )
    db.create_task("failed-export-task", fiona_id, "takeout_export", {})
    db.update_task(
        "failed-export-task",
        status="error",
        error="上次自动导出失败",
    )
    db.close()
    fiona_token = _login("fiona", "fiona-pass-123")

    class FailingPlugin:
        refresh_token = "test-refresh"

        def _refresh_access_token(self):
            raise RuntimeError("测试中断，不发起真实导出")

        def cleanup(self):
            pass

    original = youtube_router._plugin_for
    youtube_router._plugin_for = (
        lambda db, user_id, config: FailingPlugin()
    )
    try:
        r = client.post(
            "/api/v1/sources/youtube/takeout/export",
            headers=_auth(fiona_token),
        )
        assert r.status_code == 202, r.text
    finally:
        youtube_router._plugin_for = original


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 API 测试通过！")
