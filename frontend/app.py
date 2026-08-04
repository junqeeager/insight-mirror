"""Streamlit 主应用"""

import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
from core.database import Database
from core.utils import load_config

# 页面配置
st.set_page_config(
    page_title="个人认知画像",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 初始化数据库
@st.cache_resource
def get_database():
    config = load_config()
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    # 从 URL 中提取路径
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]
    return Database(db_path)

db = get_database()
db.init_tables()

# 侧边栏
with st.sidebar:
    st.title("🧠 个人认知画像")
    st.markdown("---")

    # 数据库统计
    stats = db.get_stats()
    st.metric("总事件数", stats["total"])
    st.markdown("---")

    # 数据源状态
    st.subheader("数据源状态")
    for source, count in stats.get("by_source", {}).items():
        st.text(f"📦 {source}: {count} 条")

# 主页面
st.title("🏠 个人认知画像 Dashboard")

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

st.markdown("---")

# 最近事件
st.subheader("📋 最近事件")
recent_events = db.get_events(limit=20)
if recent_events:
    for event in recent_events:
        with st.expander(f"{event.source} | {event.title[:50]}..."):
            st.write(f"**时间:** {event.timestamp.strftime('%Y-%m-%d %H:%M')}")
            st.write(f"**类型:** {event.event_type.value}")
            st.write(f"**深度:** {event.depth.value}")
            if event.url:
                st.write(f"**链接:** [{event.url}]({event.url})")
            if event.tags:
                st.write(f"**标签:** {', '.join(event.tags)}")
else:
    st.info("暂无数据，请先同步数据源。")

# 快捷操作
st.markdown("---")
st.subheader("⚡ 快捷操作")

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🔄 同步 B站数据", use_container_width=True):
        st.info("请运行: python scripts/sync.py --source bilibili")
with col2:
    if st.button("📊 生成周报", use_container_width=True):
        st.info("请运行: python scripts/generate_report.py --period weekly")
with col3:
    if st.button("📈 查看画像", use_container_width=True):
        st.info("请访问侧边栏的画像页面")
