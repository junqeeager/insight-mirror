"""报告视图页面"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
from datetime import datetime
from pathlib import Path

from core.database import Database
from core.utils import load_config
from analysis.profile import ProfileGenerator
from report.generator import ReportGenerator

st.set_page_config(page_title="报告视图", page_icon="📋", layout="wide")

@st.cache_resource
def get_database():
    config = load_config()
    db_path = config.get("database", {}).get("url", "sqlite:///./data/profile.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path[len("sqlite:///"):]
    return Database(db_path)

db = get_database()
db.init_tables()

config = load_config()

st.title("📋 报告视图")

# 生成报告
st.subheader("📊 生成新报告")

col1, col2 = st.columns(2)
with col1:
    period = st.selectbox("报告周期", ["weekly", "monthly", "yearly"])
with col2:
    if st.button("🚀 生成报告", use_container_width=True):
        with st.spinner("正在生成报告..."):
            generator = ProfileGenerator(db, config.get("analysis", {}))
            profile = generator.generate(period=period)

            report_gen = ReportGenerator()
            report_path = report_gen.generate_html(profile)

            st.success(f"报告已生成！")
            st.session_state["latest_profile"] = profile
            st.session_state["latest_report_path"] = report_path

# 显示最新报告
if "latest_profile" in st.session_state:
    profile = st.session_state["latest_profile"]
    report_path = st.session_state.get("latest_report_path", "")

    st.markdown("---")
    st.subheader(f"📄 {profile.period.upper()} 报告")

    # 概览
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总事件数", profile.total_events)
    with col2:
        from core.utils import format_duration
        st.metric("总投入时长", format_duration(profile.total_duration))
    with col3:
        st.metric("活跃天数", profile.active_days)

    # Top 主题
    if profile.top_topics:
        st.subheader("🏆 Top 兴趣领域")
        for i, topic in enumerate(profile.top_topics[:10], 1):
            st.write(f"{i}. **{topic.name}** (权重: {topic.weight:.3f})")

    # 来源分布
    if profile.source_distribution:
        st.subheader("📡 来源分布")
        for source, count in sorted(
            profile.source_distribution.items(), key=lambda x: x[1], reverse=True
        ):
            st.write(f"- {source}: {count} 条")

    # 趋势
    if profile.emerging_topics:
        st.subheader("📈 新兴兴趣")
        cols = st.columns(min(len(profile.emerging_topics), 5))
        for i, topic in enumerate(profile.emerging_topics[:5]):
            cols[i].markdown(f"🟢 {topic}")

    if profile.declining_topics:
        st.subheader("📉 衰退兴趣")
        cols = st.columns(min(len(profile.declining_topics), 5))
        for i, topic in enumerate(profile.declining_topics[:5]):
            cols[i].markdown(f"🔴 {topic}")

    # 洞察
    if profile.insights:
        st.subheader("💡 个人洞察")
        for insight in profile.insights:
            st.info(insight)

    # 查看完整报告
    if report_path and Path(report_path).exists():
        st.markdown("---")
        st.subheader("🔗 完整报告")
        with open(report_path, "r") as f:
            html_content = f.read()
        st.components.v1.html(html_content, height=800, scrolling=True)

# 历史报告列表
st.markdown("---")
st.subheader("📚 历史报告")

reports_dir = Path("./data/reports")
if reports_dir.exists():
    reports = sorted(reports_dir.glob("*.html"), reverse=True)
    if reports:
        for report in reports[:10]:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"📄 {report.name}")
            with col2:
                st.write(f"生成时间: {report.stat().st_mtime:.0f}")
            with col3:
                with open(report, "r") as f:
                    html = f.read()
                st.components.v1.html(html, height=0, width=0)
    else:
        st.info("暂无历史报告")
else:
    st.info("暂无历史报告")
