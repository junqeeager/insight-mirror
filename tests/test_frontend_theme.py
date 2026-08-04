"""Astryx 主题资产与 CSS 生成测试"""

import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from frontend.theme import build_theme_css  # noqa: E402

_ASSETS = Path(project_root) / "frontend" / "assets"


def test_astryx_assets_exist():
    for name in ("astryx/astryx.css", "astryx/theme.css", "astryx-streamlit.css"):
        path = _ASSETS / name
        assert path.is_file(), f"缺少主题资产: {path}"
        assert path.stat().st_size > 0, f"主题资产为空: {path}"


def test_build_theme_css_contains_tokens_and_selectors():
    css = build_theme_css()
    assert "@layer astryx-base" in css
    assert "--color-background-card" in css
    for selector in (
        '[data-testid="stMetric"]',
        '[data-testid="stSidebar"]',
        '[data-testid="stButton"]',
        '[data-testid="stExpander"]',
    ):
        assert selector in css, f"缺少选择器: {selector}"


def test_theme_css_contains_no_secrets():
    css = build_theme_css()
    assert "GITHUB_TOKEN" not in css
    assert "BILI_COOKIE" not in css


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 前端主题测试通过！")
