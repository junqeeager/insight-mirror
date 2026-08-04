"""FastAPI 接口测试（TestClient + 临时数据库）"""

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

# 必须在导入 app 前设置；deps.get_db_path 每次请求读取该环境变量
_tmp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["PROFILE_DB_PATH"] = _tmp_file.name
_tmp_file.close()


def _cleanup():
    Path(os.environ["PROFILE_DB_PATH"]).unlink(missing_ok=True)


atexit.register(_cleanup)

from fastapi.testclient import TestClient  # noqa: E402

from core.database import Database  # noqa: E402
from core.models import Event, EventType  # noqa: E402
from analysis.profile import ProfileGenerator  # noqa: E402
from api.main import app  # noqa: E402

client = TestClient(app)


def _seed():
    db = Database(os.environ["PROFILE_DB_PATH"])
    db.init_tables()
    titles = ["Python 编程入门教程", "FastAPI 实战开发", "机器学习基础课程"]
    for i, title in enumerate(titles):
        db.insert_event(
            Event(
                id=f"api-ev-{i}",
                timestamp=datetime(2026, 8, 1, 10, 0, i),
                source="test",
                event_type=EventType.VIEW,
                title=title,
                tags=["编程", "教程"],
            )
        )
    db.close()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_events():
    _seed()
    r = client.get("/api/v1/events", params={"limit": 100})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    assert data[0]["source"] == "test"
    assert data[0]["event_type"] == "view"

    r2 = client.get("/api/v1/events", params={"source": "nope"})
    assert r2.status_code == 200
    assert r2.json() == []


def test_stats():
    _seed()
    r = client.get("/api/v1/stats")
    assert r.status_code == 200
    assert r.json()["total"] == 3


def test_topics_and_latest_profile():
    _seed()
    db = Database(os.environ["PROFILE_DB_PATH"])
    db.init_tables()
    ProfileGenerator(db, {}).generate(period="weekly", persist=True)
    db.close()

    r = client.get("/api/v1/topics")
    assert r.status_code == 200
    assert r.json(), "topics 不应为空"

    r = client.get("/api/v1/profile/latest", params={"period": "weekly"})
    assert r.status_code == 200
    assert r.json()["total_events"] == 3

    r = client.get("/api/v1/profile/latest", params={"period": "monthly"})
    assert r.status_code == 404


def test_refresh_task():
    _seed()
    r = client.post("/api/v1/profile/refresh", params={"period": "weekly"})
    assert r.status_code == 202
    task_id = r.json()["task_id"]

    body = {}
    for _ in range(60):
        s = client.get(f"/api/v1/profile/refresh/{task_id}")
        assert s.status_code == 200
        body = s.json()
        if body["status"] in ("done", "error"):
            break
        time.sleep(0.5)
    assert body["status"] == "done", body
    assert body["profile_id"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 API 测试通过！")
