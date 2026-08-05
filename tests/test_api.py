"""FastAPI 接口测试（TestClient + 临时数据库，覆盖登录鉴权与用户隔离）"""

import atexit
import os
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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 API 测试通过！")
