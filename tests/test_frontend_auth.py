"""前端密码门测试（AppTest + 内存假数据，全程离线）"""

import os
import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from streamlit.testing.v1 import AppTest  # noqa: E402

from frontend.auth import _password_configured, _verify_password  # noqa: E402

_APP_PATH = str(Path(project_root) / "frontend" / "app.py")
_PASSWORD = "test-pass-123"


def _patch_data_access():
    """替换数据访问层，避免测试触达真实数据库或网络。"""
    import frontend.data_access as da

    def fake_stats(config):
        return {
            "total": 3,
            "by_type": {"view": 3, "read": 0, "create": 0},
            "by_source": {"test": 3},
        }

    def fake_events(config, limit=1000, **kwargs):
        return []

    da.get_stats = fake_stats
    da.get_events = fake_events


def _login(at: AppTest, password: str) -> AppTest:
    at.text_input[0].set_value(password)
    at.button[0].click().run()
    return at


def test_verify_password_match_and_configured():
    os.environ["APP_PASSWORD"] = _PASSWORD
    try:
        assert _password_configured()
        assert _verify_password(_PASSWORD)
        assert not _verify_password("wrong-password")
        assert not _verify_password("")
    finally:
        os.environ.pop("APP_PASSWORD", None)
    assert not _password_configured()


def test_dashboard_blocks_without_configured_password():
    os.environ.pop("APP_PASSWORD", None)
    _patch_data_access()

    at = AppTest.from_file(_APP_PATH, default_timeout=20)
    at.run()

    assert any("APP_PASSWORD" in error.value for error in at.error)
    assert [markdown.value for markdown in at.markdown] == ["### 🔒 需要访问密码"]
    assert not at.metric


def test_dashboard_rejects_wrong_password():
    os.environ["APP_PASSWORD"] = _PASSWORD
    _patch_data_access()

    at = AppTest.from_file(_APP_PATH, default_timeout=20)
    at.run()
    _login(at, "wrong-password")

    assert any("密码错误" in error.value for error in at.error)
    assert not at.metric
    assert at.session_state.filtered_state.get("authenticated") is None


def test_dashboard_accepts_correct_password_and_enters_main_page():
    os.environ["APP_PASSWORD"] = _PASSWORD
    _patch_data_access()

    at = AppTest.from_file(_APP_PATH, default_timeout=20)
    at.run()
    _login(at, _PASSWORD)

    assert not at.error
    assert at.session_state["authenticated"] is True
    labels = [metric.label for metric in at.metric]
    assert "总事件数" in labels
    assert any(button.label == "退出登录" for button in at.button)


def test_logout_clears_auth_and_returns_to_login():
    os.environ["APP_PASSWORD"] = _PASSWORD
    _patch_data_access()

    at = AppTest.from_file(_APP_PATH, default_timeout=20)
    at.run()
    _login(at, _PASSWORD)
    assert at.session_state["authenticated"] is True

    logout = next(button for button in at.button if button.label == "退出登录")
    logout.click().run()
    at.run()  # 完成 st.rerun() 触发的下一次脚本执行

    assert at.session_state.filtered_state.get("authenticated") is None
    assert [markdown.value for markdown in at.markdown] == ["### 🔒 需要访问密码"]
    assert not at.metric


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 前端密码门测试通过！")
