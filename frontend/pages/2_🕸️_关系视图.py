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
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import tempfile
import os

from core.utils import load_config
from analysis.keywords import segment_text
from frontend.data_access import get_events

st.set_page_config(page_title="关系视图", page_icon="🕸️", layout="wide")

config = load_config()

st.title("🕸️ 关系视图")

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

# 构建兴趣共现图
st.subheader("🔗 兴趣关联网络")

# 提取每个事件的关键词
event_keywords = []
for event in events:
    text = event.title or ""
    if event.description:
        text += " " + event.description
    keywords = set(segment_text(text))
    if keywords:
        event_keywords.append(keywords)

# 构建共现矩阵
co_occurrence = Counter()
keyword_freq = Counter()

for keywords in event_keywords:
    for kw in keywords:
        keyword_freq[kw] += 1
    # 取该事件内权重最高的 5 个关键词（按全局频率排序）
    top_kw = sorted(keywords, key=lambda x: keyword_freq[x], reverse=True)[:5]
    for i, kw1 in enumerate(top_kw):
        for kw2 in top_kw[i+1:]:
            if kw1 != kw2:
                co_occurrence[(kw1, kw2)] += 1

# 过滤低频词
min_freq = st.slider("最小出现次数", 1, 20, 3)
min_co = st.slider("最小共现次数", 1, 10, 2)

filtered_keywords = {kw for kw, freq in keyword_freq.items() if freq >= min_freq}

# 构建 NetworkX 图
G = nx.Graph()

for kw in filtered_keywords:
    G.add_node(kw, size=keyword_freq[kw])

for (kw1, kw2), count in co_occurrence.items():
    if kw1 in filtered_keywords and kw2 in filtered_keywords and count >= min_co:
        G.add_edge(kw1, kw2, weight=count)

# 使用 pyvis 可视化
if G.nodes():
    net = Network(height="600px", width="100%", bgcolor="#ffffff", font_color="#333")
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
    with open(temp_path, "r") as f:
        html_content = f.read()
    st.html(html_content)
    os.unlink(temp_path)
else:
    st.info("数据不足以生成关联网络，请增加数据量或调整筛选条件。")

# 平台分布雷达图
st.subheader("📡 平台分布雷达图")

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
st.subheader("☁️ 标签云")

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
