"""关系视图页面"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
import plotly.graph_objects as go
import networkx as nx
from pyvis.network import Network
from collections import Counter
from datetime import datetime, timedelta
import tempfile
import os

from core.utils import load_config
from frontend.auth import require_auth
from frontend.data_access import get_events, get_graph
from frontend.layout import page_header, render_sidebar
from frontend.theme import apply_theme

st.set_page_config(page_title="关系视图", page_icon="🕸️", layout="wide")

config = load_config()
apply_theme()
require_auth()
render_sidebar(config)
page_header("关系视图", "查看兴趣关键词之间的关联与平台分布")

# 时间范围选择
period = st.selectbox("时间范围", ["最近 7 天", "最近 30 天", "最近 90 天"])

now = datetime.now()
if period == "最近 7 天":
    since = now - timedelta(days=7)
elif period == "最近 30 天":
    since = now - timedelta(days=30)
else:
    since = now - timedelta(days=90)

events = get_events(config, since=since, limit=5000)

if not events:
    st.warning("暂无数据，请先同步数据源。")
    st.stop()

# 兴趣关联网络（图谱由后端预计算，前端只做阈值过滤）
st.subheader("兴趣关联网络")

window_days = {"最近 7 天": 7, "最近 30 天": 30, "最近 90 天": 90}[period]
graph_data = get_graph(config, window_days=window_days)
keyword_freq = {n["label"]: n["freq"] for n in graph_data["nodes"]}
graph_edges = graph_data["edges"]

# 过滤低频词
min_freq = st.slider("最小出现次数", 1, 20, 3)
min_co = st.slider("最小共现次数", 1, 10, 2)

filtered_keywords = {kw for kw, freq in keyword_freq.items() if freq >= min_freq}

# 构建 NetworkX 图
G = nx.Graph()

for kw in filtered_keywords:
    G.add_node(kw, size=keyword_freq[kw])

for edge in graph_edges:
    if (
        edge["source"] in filtered_keywords
        and edge["target"] in filtered_keywords
        and edge["weight"] >= min_co
    ):
        G.add_edge(edge["source"], edge["target"], weight=edge["weight"])

# 使用 pyvis 可视化
if G.nodes():
    net = Network(height="600px", width="100%", bgcolor="#f1f1f1", font_color="#171717")
    net.from_nx(G)

    # 设置节点大小
    for node in net.nodes:
        node["size"] = keyword_freq.get(node["label"], 1) * 5

    # 设置边宽度
    for edge in net.edges:
        edge["width"] = edge.get("value", 1) * 2

    # 生成 HTML
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        net.save_graph(f.name)
        temp_path = f.name

    # 嵌入 Streamlit
    with st.container(border=True):
        with open(temp_path, "r") as f:
            html_content = f.read()
        st.html(html_content)
    os.unlink(temp_path)
else:
    st.info("数据不足以生成关联网络，请增加数据量或调整筛选条件。")

# 平台分布雷达图
st.subheader("平台分布雷达图")

source_counts = Counter(e.source for e in events)
if source_counts:
    sources = list(source_counts.keys())
    counts = list(source_counts.values())

    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=counts,
        theta=sources,
        fill="toself",
        name="事件数",
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True)),
        showlegend=True,
        height=400,
    )
    st.plotly_chart(fig, width="stretch")

# 标签云
st.subheader("标签云")

all_tags = []
for event in events:
    all_tags.extend(event.tags)

if all_tags:
    tag_counts = Counter(all_tags)
    top_tags = tag_counts.most_common(30)

    # 使用 Streamlit 的原生方式展示
    cols = st.columns(4)
    for i, (tag, count) in enumerate(top_tags):
        col = cols[i % 4]
        with col:
            st.markdown(f"**{tag}** ({count})")
else:
    st.info("暂无标签数据")
