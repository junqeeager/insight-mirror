"""Astryx neutral 主题注入（纯 CSS，不引入 React）"""

import functools
from pathlib import Path

import streamlit as st

_ASSET_DIR = Path(__file__).parent / "assets" / "astryx"
_CSS_FILES = (
    _ASSET_DIR / "astryx.css",
    _ASSET_DIR / "theme.css",
    _ASSET_DIR.parent / "astryx-streamlit.css",
)
_THEME_SCRIPT = (
    '<script>document.documentElement.setAttribute("data-astryx-theme", "neutral");'
    'document.documentElement.setAttribute("data-theme", "light");</script>'
)


@functools.lru_cache(maxsize=1)
def build_theme_css() -> str:
    """合并 Astryx 核心、neutral 主题与 Streamlit 映射为单个 <style> 内容。"""
    parts = []
    for path in _CSS_FILES:
        if not path.exists():
            raise FileNotFoundError(f"缺少 Astryx 样式文件: {path}")
        parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def apply_theme() -> None:
    """在每个页面 set_page_config 之后调用，注入主题样式并设置主题标记。"""
    st.html(f"<style>{build_theme_css()}</style>")
    st.html(_THEME_SCRIPT, unsafe_allow_javascript=True)
