"""前端登录/注册鉴权测试（AppTest + 内存假数据，全程离线）"""

import sys
import tempfile
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from streamlit.testing.v1 import AppTest  # noqa: E402

from core.database import Database  # noqa: E402
from frontend.auth import login_user, register_user  # noqa: E402

_APP_PATH = str(Path(project_root) / "frontend" / "app.py")
_PAGE1_PATH = str(Path(project_root) / "frontend" / "pages" / "1_📈_时间视图.py")


def _config_with_db(db_path: str) -> dict:
    return {
        "database": {"url": f"sqlite:///{db_path}"},
        "frontend": {"use_api": False, "api_base": "http://localhost:8502"},
        "system": {"plugins_dir": "plugins"},
    }


def test_register_pending_then_login_after_activation():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "auth.db")
        config = _config_with_db(db_path)

        ok, message = register_user(config, "alice", "alice-pass-123")
        assert ok
        assert "审核" in message

        ok, user, token, message = login_user(config, "alice", "alice-pass-123")
        assert not ok
        assert "未启用" in message

        db = Database(f"sqlite:///{db_path}")
        db.init_tables()
        alice = db.get_user_by_username("alice")
        db.update_user_status(alice["id"], "active")
        db.close()

        ok, user, token, message = login_user(config, "alice", "alice-pass-123")
        assert ok, message
        assert user["username"] == "alice"
        assert user["role"] == "user"


def test_register_duplicate_username():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "auth.db")
        config = _config_with_db(db_path)
        assert register_user(config, "bob", "bob-pass-123")[0]
        ok, message = register_user(config, "bob", "bob-pass-123")
        assert not ok
        assert "已存在" in message


def _patch_app(fake_login=None):
    import core.utils as cu
    import frontend.auth as auth
    import frontend.data_access as da
    import frontend.layout as layout

    fake_config = {
        "frontend": {"use_api": False, "api_base": "http://localhost:8502"},
        "database": {"url": "sqlite:///:memory:"},
        "system": {"plugins_dir": "plugins"},
    }
    cu.load_config = lambda *args, **kwargs: fake_config
    auth.load_config = lambda *args, **kwargs: fake_config

    def default_login(config, username, password):
        return (
            True,
            {"id": "u1", "username": "alice", "role": "user", "status": "active"},
            "token-x",
            None,
        )

    auth.login_user = fake_login or default_login

    def fake_stats(config, user):
        return {
            "total": 3,
            "by_type": {"view": 3, "read": 0, "create": 0},
            "by_source": {"test": 3},
        }

    def fake_events(config, user, limit=1000, **kwargs):
        return []

    da.get_stats = fake_stats
    da.get_events = fake_events
    layout.get_stats = fake_stats


def _login(at: AppTest, username: str, password: str) -> AppTest:
    at.text_input[0].set_value(username)
    at.text_input[1].set_value(password)
    at.button[0].click().run()
    return at


def test_dashboard_preview_without_login():
    _patch_app()
    at = AppTest.from_file(_APP_PATH, default_timeout=20)
    at.run()

    assert any("预览模式" in caption.value for caption in at.caption)
    labels = [metric.label for metric in at.metric]
    assert "示例总事件数" in labels
    assert at.session_state.filtered_state.get("user") is None


def test_feature_page_requires_login():
    _patch_app()
    at = AppTest.from_file(_PAGE1_PATH, default_timeout=20)
    at.run()

    assert any("登录 / 注册" in markdown.value for markdown in at.markdown)
    assert not at.metric


def test_dashboard_rejects_wrong_password():
    def bad_login(config, username, password):
        return False, None, None, "用户名或密码错误"

    _patch_app(fake_login=bad_login)
    at = AppTest.from_file(_APP_PATH, default_timeout=20)
    at.run()
    _login(at, "alice", "wrong-pass")

    assert any("用户名或密码错误" in error.value for error in at.error)
    labels = [metric.label for metric in at.metric]
    assert "示例总事件数" in labels
    assert at.session_state.filtered_state.get("user") is None


def test_dashboard_accepts_login_and_enters_main_page():
    _patch_app()
    at = AppTest.from_file(_APP_PATH, default_timeout=20)
    at.run()
    _login(at, "alice", "alice-pass-123")

    assert not at.error
    assert at.session_state["user"]["username"] == "alice"
    labels = [metric.label for metric in at.metric]
    assert "总事件数" in labels
    assert any(button.label == "退出登录" for button in at.button)


def test_logout_clears_login_state():
    import types

    import frontend.auth as auth

    _patch_app()
    fake_st = types.SimpleNamespace(
        session_state={
            "user": {"id": "u1", "username": "alice", "role": "user"},
            "token": "token-x",
        }
    )
    original_st = auth.st
    auth.st = fake_st
    try:
        auth.logout()
    finally:
        auth.st = original_st
    assert "user" not in fake_st.session_state
    assert "token" not in fake_st.session_state


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 前端登录鉴权测试通过！")
