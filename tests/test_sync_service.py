"""同步服务测试：多源并行、失败隔离、增量回调（离线）。"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import core.sync_service as svc  # noqa: E402
from core.auth import hash_password  # noqa: E402
from core.database import Database  # noqa: E402


class _FakeManager:
    """替代 PluginManager：不做真实插件发现。"""

    def __init__(self, plugins_dir: str, config: dict):
        self.plugins_dir = plugins_dir
        self.config = config

    def discover(self):
        return []

    def load(self, name: str):
        return object()


def _db_with_sources(names: list) -> tuple:
    db = Database(":memory:")
    db.init_tables()
    uid = db.create_user(
        "sync-user", hash_password("sync-pass-123"), role="user", status="active"
    )
    for name in names:
        db.set_source_config(uid, name, {}, enabled=True)
    return db, uid


def _config() -> dict:
    return {
        "system": {"plugins_dir": "plugins"},
        "sources": {"a": {"config": {}}, "b": {"config": {}}},
    }


def test_sync_user_parallel_collects_all_and_callback():
    db, uid = _db_with_sources(["a", "b"])
    original_manager = svc.PluginManager
    original_sync = svc.sync_source
    svc.PluginManager = _FakeManager
    seen = []

    def fake_sync_source(db_, plugin_manager, name, user_id):
        return {"source": name, "count": 1}

    svc.sync_source = fake_sync_source
    try:
        results = svc.sync_user(
            db,
            _config(),
            uid,
            on_source_done=lambda name, result: seen.append((name, result)),
        )
        assert set(results) == {"a", "b"}
        assert all(result["count"] == 1 for result in results.values())
        assert sorted(name for name, _ in seen) == ["a", "b"]
    finally:
        svc.PluginManager = original_manager
        svc.sync_source = original_sync
        db.close()


def test_sync_user_single_source_and_disabled_skipped():
    db, uid = _db_with_sources(["a", "b"])
    db.set_source_config(uid, "b", {}, enabled=False)
    original_manager = svc.PluginManager
    original_sync = svc.sync_source
    svc.PluginManager = _FakeManager
    svc.sync_source = lambda db_, pm, name, user_id: {"source": name, "count": 1}
    try:
        all_results = svc.sync_user(db, _config(), uid)
        assert set(all_results) == {"a"}

        only_b = svc.sync_user(db, _config(), uid, source="b")
        assert only_b == {}
    finally:
        svc.PluginManager = original_manager
        svc.sync_source = original_sync
        db.close()


def test_sync_user_failure_does_not_block_other_sources():
    db, uid = _db_with_sources(["a", "b"])
    original_manager = svc.PluginManager
    original_sync = svc.sync_source
    svc.PluginManager = _FakeManager

    def fake_sync_source(db_, plugin_manager, name, user_id):
        if name == "b":
            raise RuntimeError("模拟拉取失败")
        return {"source": name, "count": 2}

    svc.sync_source = fake_sync_source
    try:
        results = svc.sync_user(db, _config(), uid)
        assert results["a"]["count"] == 2
        assert "error" in results["b"]
        assert "模拟拉取失败" in results["b"]["error"]
    finally:
        svc.PluginManager = original_manager
        svc.sync_source = original_sync
        db.close()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 同步服务测试通过！")
