"""Streamlit 主应用"""

import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pandas as pd
import streamlit as st
from core.utils import load_config
from frontend.data_access import get_events, get_stats
from frontend.auth import render_auth_ui
from frontend.layout import page_header, render_sidebar
from frontend.theme import apply_theme

# 页面配置
st.set_page_config(
    page_title="个人认知画像",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

config = load_config()
apply_theme()

_PREVIEW_STATS = {
    "total": 128,
    "by_type": {"view": 88, "read": 30, "create": 10},
    "by_source": {"bilibili": 88, "github": 30, "rss": 10},
}

_PREVIEW_EVENTS = [
    {"时间": "2026-08-04 22:15", "来源": "bilibili", "类型": "view", "标题": "【示例】Python 异步编程入门"},
    {"时间": "2026-08-04 20:03", "来源": "github", "类型": "create", "标题": "【示例】提交 feat: add dashboard"},
    {"时间": "2026-08-03 12:40", "来源": "rss", "类型": "read", "标题": "【示例】大模型应用架构实践"},
    {"时间": "2026-08-02 09:10", "来源": "bilibili", "类型": "view", "标题": "【示例】FastAPI 实战教程"},
    {"时间": "2026-08-01 23:30", "来源": "rss", "类型": "read", "标题": "【示例】认知科学与学习效率"},
]


def _render_preview() -> None:
    """未登录时的公开预览：示例数据 + 登录/注册入口。"""
    with st.sidebar:
        st.markdown("### 个人认知画像")
        st.caption("预览模式（示例数据）")
        st.markdown("---")
        st.metric("示例总事件数", _PREVIEW_STATS["total"])
        st.markdown("---")
        st.caption("登录后可查看自己的真实画像。")

    page_header("个人认知画像", "公开预览 · 登录后查看你自己的画像")
    st.info("当前展示的是示例数据。登录后可查看真实画像、配置自己的数据源并生成报告。")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("示例总事件数", _PREVIEW_STATS["total"])
    with col2:
        st.metric("观看记录", _PREVIEW_STATS["by_type"].get("view", 0))
    with col3:
        st.metric("阅读记录", _PREVIEW_STATS["by_type"].get("read", 0))
    with col4:
        st.metric("创作记录", _PREVIEW_STATS["by_type"].get("create", 0))

    st.subheader("最近事件（示例）")
    st.dataframe(pd.DataFrame(_PREVIEW_EVENTS), width="stretch", hide_index=True)

    st.markdown("---")
    render_auth_ui()


def _render_dashboard(user: dict) -> None:
    """登录后的真实数据看板。"""
    stats = get_stats(config, user)
    render_sidebar(config, user, stats)

    page_header("个人认知画像", "基于行为数据生成的兴趣画像与数据看板")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("总事件数", stats["total"])
    with col2:
        by_type = stats.get("by_type", {})
        st.metric("观看记录", by_type.get("view", 0))
    with col3:
        st.metric("阅读记录", by_type.get("read", 0))
    with col4:
        st.metric("创作记录", by_type.get("create", 0))

    st.subheader("最近事件")
    recent_events = get_events(config, user, limit=20)
    if recent_events:
        df = pd.DataFrame(
            [
                {
                    "时间": e.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "来源": e.source,
                    "类型": e.event_type.value,
                    "标题": e.title[:60],
                    "链接": e.url or "",
                }
                for e in recent_events
            ]
        )
        st.dataframe(df, width="stretch", hide_index=True)
    else:
        st.info("暂无数据，请先在设置页配置并同步数据源。")

    with st.container(border=True):
        st.subheader("快捷操作")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.button("同步数据", width="stretch")
            st.caption("请到设置页配置并同步你的数据源")
        with col2:
            st.button("生成报告", width="stretch")
            st.caption("请到报告视图页生成")
        with col3:
            st.button("查看画像", width="stretch")
            st.caption("请访问侧边栏的画像页面")


user = st.session_state.get("user")
if user:
    _render_dashboard(user)
else:
    _render_preview()
