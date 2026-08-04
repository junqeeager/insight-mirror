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

from core.database import Database
from core.utils import load_config

st.set_page_config(page_title="时间视图", page_icon="📈", layout="wide")

@st.cache_resource
def get_database():
    config = load_config()
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]
    return Database(db_path)

db = get_database()
db.init_tables()

st.title("📈 时间视图")

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
events = db.get_events(
    source=source_filter if source_filter != "全部" else None,
    event_type=event_filter if event_filter != "全部" else None,
    since=since,
    limit=5000,
)

if not events:
    st.warning("暂无数据，请先同步数据源。")
    st.stop()

# 转换为 DataFrame
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
st.subheader("🔥 活跃时段热力图")
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
st.plotly_chart(fig_heatmap, use_container_width=True)

# 事件时间线
st.subheader("📅 事件时间线")
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
st.plotly_chart(fig_timeline, use_container_width=True)

# 来源分布
st.subheader("📊 来源分布")
source_counts = df["source"].value_counts()
fig_source = px.pie(
    values=source_counts.values,
    names=source_counts.index,
    title="数据来源分布",
)
fig_source.update_layout(height=350)
st.plotly_chart(fig_source, use_container_width=True)

# 事件类型分布
st.subheader("📈 事件类型分布")
type_counts = df["type"].value_counts()
fig_type = px.bar(
    x=type_counts.index,
    y=type_counts.values,
    title="事件类型统计",
    labels={"x": "类型", "y": "数量"},
)
fig_type.update_layout(height=300)
st.plotly_chart(fig_type, use_container_width=True)
