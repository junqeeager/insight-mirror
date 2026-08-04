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
stats = get_stats(config)
apply_theme()
render_sidebar(config, stats)

page_header("个人认知画像", "基于行为数据生成的兴趣画像与数据看板")

# 概览卡片
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

# 最近事件
st.subheader("最近事件")
recent_events = get_events(config, limit=20)
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
    st.info("暂无数据，请先同步数据源。")

# 快捷操作
with st.container(border=True):
    st.subheader("快捷操作")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("同步 B 站数据", width="stretch"):
            st.info("请运行: python scripts/sync.py --source bilibili")
    with col2:
        if st.button("生成周报", width="stretch"):
            st.info("请运行: python scripts/generate_report.py --period weekly")
    with col3:
        if st.button("查看画像", width="stretch"):
            st.info("请访问侧边栏的画像页面")
