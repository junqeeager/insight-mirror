"""设置页面"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
from core.database import Database
from core.utils import load_config
from frontend.auth import require_auth
from frontend.data_access import get_events, get_stats
from frontend.layout import page_header, render_sidebar
from frontend.theme import apply_theme

st.set_page_config(page_title="设置", page_icon="⚙️", layout="wide")

config = load_config()
apply_theme()
require_auth()


@st.cache_resource
def get_database():
    config = load_config()
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]
    return Database(db_path)

db = get_database()
db.init_tables()

render_sidebar(config)
page_header("设置", "管理数据源、数据库统计与配置文件")

# 数据源管理
st.subheader("数据源管理")

sources = config.get("sources", {})
for source_name, source_config in sources.items():
    with st.expander(f"{source_config.get('plugin', source_name)} - {source_name}"):
        col1, col2 = st.columns(2)
        with col1:
            enabled = st.toggle(
                "启用",
                value=source_config.get("enabled", False),
                key=f"toggle_{source_name}",
            )
        with col2:
            st.text(f"插件: {source_config.get('plugin', 'N/A')}")

        # 显示配置（隐藏敏感信息）
        plugin_config = source_config.get("config", {})
        st.json({k: "***" if "token" in k.lower() or "cookie" in k.lower() else v
                 for k, v in plugin_config.items()})

# 数据库统计
st.subheader("数据库统计")

stats = get_stats(config)
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("总事件数", stats["total"])
with col2:
    st.metric("数据源数", len(stats.get("by_source", {})))
with col3:
    st.metric("事件类型数", len(stats.get("by_type", {})))

# 详细统计
if stats.get("by_source"):
    st.subheader("按来源统计")
    for source, count in stats["by_source"].items():
        st.write(f"- {source}: {count} 条")

if stats.get("by_type"):
    st.subheader("按类型统计")
    for event_type, count in stats["by_type"].items():
        st.write(f"- {event_type}: {count} 条")

# 数据管理
st.subheader("数据管理")

col1, col2 = st.columns(2)
with col1:
    if st.button("重新初始化数据库", type="secondary"):
        st.warning("这将删除所有数据！")
        if st.button("确认删除", type="primary"):
            db.init_tables()
            st.success("数据库已重新初始化")
            st.rerun()

with col2:
    if st.button("导出数据", type="secondary"):
        events = get_events(config, limit=10000)
        import pandas as pd
        df = pd.DataFrame([
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "source": e.source,
                "type": e.event_type.value,
                "title": e.title,
                "url": e.url,
                "tags": ", ".join(e.tags),
            }
            for e in events
        ])
        csv = df.to_csv(index=False)
        st.download_button(
            label="下载 CSV",
            data=csv,
            file_name="events_export.csv",
            mime="text/csv",
        )

# 配置文件
st.subheader("配置文件")
with st.expander("查看完整配置"):
    # 隐藏敏感信息
    safe_config = {
        k: "***" if any(s in str(v).lower() for s in ["token", "cookie", "secret"])
        else v
        for k, v in config.items()
    }
    st.json(safe_config)
