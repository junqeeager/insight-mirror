"""时间视图页面"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from datetime import datetime, timedelta

from core.utils import load_config
from frontend.auth import require_login
from frontend.data_access import get_events
from frontend.layout import page_header, render_sidebar
from frontend.theme import apply_theme

st.set_page_config(page_title="时间视图", page_icon="📈", layout="wide")

config = load_config()
apply_theme()
user = require_login()
render_sidebar(config, user)
page_header("时间视图", "按时间范围观察事件分布与活跃时段")


@st.cache_data(ttl=60, show_spinner=False)
def build_time_view(source, event_type, since_iso, limit, data_key):
    """构建时间视图的 DataFrame 与图表（60s 缓存，数据变化后自动重建）"""
    since = datetime.fromisoformat(since_iso) if since_iso else None
    events = get_events(config, user, source=source, event_type=event_type, since=since, limit=limit)
    if not events:
        return None, None, None, None, None

    df = pd.DataFrame([
        {
            "timestamp": e.timestamp,
            "source": e.source,
            "type": e.event_type.value,
            "title": e.title,
            "depth": e.depth.value,
            "duration": e.duration or 0,
            "tags": ", ".join(e.tags) if e.tags else "",
        }
        for e in events
    ])

    # 活跃时段热力图
    df["weekday"] = df["timestamp"].dt.day_name()
    df["hour"] = df["timestamp"].dt.hour
    heatmap_data = df.groupby(["weekday", "hour"]).size().reset_index(name="count")
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    heatmap_pivot = heatmap_data.pivot(index="weekday", columns="hour", values="count").reindex(weekday_order).fillna(0)
    fig_heatmap = px.imshow(
        heatmap_pivot,
        labels=dict(x="小时", y="星期", color="事件数"),
        title="活跃时段分布",
        color_continuous_scale="Blues",
    )
    fig_heatmap.update_layout(height=300)

    fig_timeline = px.scatter(
        df,
        x="timestamp",
        y="source",
        color="type",
        hover_data=["title", "depth"],
        title="事件时间线",
        labels={"timestamp": "时间", "source": "来源", "type": "类型"},
    )
    fig_timeline.update_layout(height=400)

    source_counts = df["source"].value_counts()
    fig_source = px.pie(
        values=source_counts.values,
        names=source_counts.index,
        title="数据来源分布",
    )
    fig_source.update_layout(height=350)

    type_counts = df["type"].value_counts()
    fig_type = px.bar(
        x=type_counts.index,
        y=type_counts.values,
        title="事件类型统计",
        labels={"x": "类型", "y": "数量"},
    )
    fig_type.update_layout(height=300)
    return df, fig_heatmap, fig_timeline, fig_source, fig_type


# 时间范围选择
col1, col2, col3 = st.columns(3)
with col1:
    period = st.selectbox("时间范围", ["最近 7 天", "最近 30 天", "最近 90 天", "全部"])
with col2:
    source_filter = st.selectbox("数据来源", ["全部", "bilibili", "browser_history", "github"])
with col3:
    event_filter = st.selectbox("事件类型", ["全部", "view", "read", "create", "search"])

# 计算时间范围
now = datetime.now()
if period == "最近 7 天":
    since = now - timedelta(days=7)
elif period == "最近 30 天":
    since = now - timedelta(days=30)
elif period == "最近 90 天":
    since = now - timedelta(days=90)
else:
    since = None

# 获取数据
events = get_events(
    config,
    source=source_filter if source_filter != "全部" else None,
    event_type=event_filter if event_filter != "全部" else None,
    since=since,
    limit=5000,
)

if not events:
    st.warning("暂无数据，请先同步数据源。")
    st.stop()

data_key = (len(events), max(e.timestamp.isoformat() for e in events))
df, fig_heatmap, fig_timeline, fig_source, fig_type = build_time_view(
    source_filter if source_filter != "全部" else None,
    event_filter if event_filter != "全部" else None,
    since.isoformat() if since else None,
    5000,
    data_key,
)

st.subheader("活跃时段热力图")
st.plotly_chart(fig_heatmap, width="stretch")

# 事件时间线
st.subheader("事件时间线")
st.plotly_chart(fig_timeline, width="stretch")

# 来源分布
st.subheader("来源分布")
st.plotly_chart(fig_source, width="stretch")

# 事件类型分布
st.subheader("事件类型分布")
st.plotly_chart(fig_type, width="stretch")
