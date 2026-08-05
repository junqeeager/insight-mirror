"""共享页面布局：一致的侧边栏与页头"""

from typing import Optional

import streamlit as st

from frontend.data_access import get_stats
from frontend.auth import logout


def render_sidebar(config: dict, user: dict, stats: Optional[dict] = None) -> dict:
    """渲染统一侧边栏；未传入 stats 时自动查询（结果带 TTL 缓存）。"""
    if stats is None:
        stats = get_stats(config, user)

    with st.sidebar:
        st.markdown("### 个人认知画像")
        role_label = "管理员" if user.get("role") == "admin" else "用户"
        st.caption(f"{user.get('username')}（{role_label}）")
        st.markdown("---")
        st.metric("总事件数", stats.get("total", 0))
        st.markdown("---")
        st.markdown("**数据源状态**")
        by_source = stats.get("by_source", {})
        if by_source:
            for source, count in by_source.items():
                st.markdown(f"- **{source}**：{count} 条")
        else:
            st.caption("暂无数据源")
        st.markdown("---")
        st.caption("数据由本地数据库提供，页面响应走 FastAPI 缓存。")
        if st.button("退出登录", width="stretch"):
            logout()
            st.rerun()
    return stats


def page_header(title: str, subtitle: Optional[str] = None) -> None:
    """统一的页头，减少每页重复的 emoji 与分隔线。"""
    st.markdown(f"# {title}")
    if subtitle:
        st.caption(subtitle)
