"""报告视图页面"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
import time
from pathlib import Path

from datetime import datetime

from core.utils import load_config
from report.generator import ReportGenerator
from frontend.data_access import (
    generate_profile,
    get_latest_profile,
    get_task_status,
    start_profile_refresh,
)

st.set_page_config(page_title="报告视图", page_icon="📋", layout="wide")

config = load_config()

st.title("📋 报告视图")


def _finish_report(profile, period: str):
    """生成 HTML 报告并写入会话状态"""
    report_gen = ReportGenerator()
    report_path = report_gen.generate_html(profile)
    st.success(f"报告已生成！")
    st.session_state["latest_profile"] = profile
    st.session_state["latest_report_path"] = report_path


# 生成报告
st.subheader("📊 生成新报告")

col1, col2 = st.columns(2)
with col1:
    period = st.selectbox("报告周期", ["weekly", "monthly", "yearly"])
with col2:
    if st.button("🚀 生成报告", width="stretch"):
        task_id = start_profile_refresh(config, period=period)
        if task_id:
            # 后台任务模式：立即返回，页面轮询状态
            st.session_state["refresh_task_id"] = task_id
            st.session_state["refresh_period"] = period
            st.session_state["refresh_attempts"] = 0
        else:
            # API 不可用：回退为本地同步生成
            with st.spinner("正在生成报告..."):
                profile = generate_profile(config, period=period)
            _finish_report(profile, period)

# 后台任务轮询（非阻塞）
task_id = st.session_state.get("refresh_task_id")
if task_id:
    status = get_task_status(config, task_id)
    if status is None:
        st.warning("暂时无法连接 API，任务状态未知；请稍后刷新页面查看。")
    elif status["status"] in ("running", "started"):
        attempts = st.session_state.get("refresh_attempts", 0) + 1
        st.session_state["refresh_attempts"] = attempts
        st.info(f"画像正在后台生成中…（{attempts}/30，任务 {task_id[:8]}）")
        if attempts <= 30:
            time.sleep(1)
            st.rerun()
        else:
            st.warning("生成超时，请稍后手动刷新页面查看。")
    elif status["status"] == "done":
        period_now = st.session_state.get("refresh_period", "weekly")
        profile = get_latest_profile(config, period=period_now, fresh=True)
        st.session_state.pop("refresh_task_id", None)
        st.session_state.pop("refresh_attempts", None)
        st.session_state.pop("refresh_period", None)
        if profile:
            _finish_report(profile, period_now)
        st.rerun()
    else:
        st.error(f"生成失败：{status.get('error')}")
        st.session_state.pop("refresh_task_id", None)
        st.session_state.pop("refresh_attempts", None)
        st.session_state.pop("refresh_period", None)

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
        st.html(html_content)

# 历史报告列表
st.markdown("---")
st.subheader("📚 历史报告")

reports_dir = Path("./data/reports")
if reports_dir.exists():
    reports = sorted(reports_dir.glob("*.html"), reverse=True)
    if reports:
        for report in reports[:10]:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"📄 {report.name}")
            with col2:
                st.write(f"生成时间: {report.stat().st_mtime:.0f}")
    else:
        st.info("暂无历史报告")
else:
    st.info("暂无历史报告")
