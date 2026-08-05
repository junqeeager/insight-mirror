"""设置页面：我的数据源 / 数据导出 / 管理员用户管理"""

import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import streamlit as st
from core.utils import load_config
from frontend.auth import require_login
from frontend.data_access import (
    admin_list_users,
    admin_update_user,
    get_events,
    get_my_sources,
    get_stats,
    run_sync_direct,
    save_source_config,
    start_sync,
    test_source_connection,
)
from frontend.layout import page_header, render_sidebar
from frontend.theme import apply_theme

st.set_page_config(page_title="设置", page_icon="⚙️", layout="wide")

config = load_config()
apply_theme()
user = require_login()
render_sidebar(config, user)
page_header("设置", "管理你的数据源、导出数据；管理员可管理用户")


def _fields_for(source: str) -> list:
    return {
        "bilibili": [
            ("cookie", "B站 Cookie（SESSDATA=...; bili_jct=...）", True),
            ("csrf", "B站 CSRF（bili_jct）", True),
        ],
        "github": [
            ("token", "GitHub Token", True),
            ("username", "GitHub 用户名", False),
            ("include_repos", "包含仓库（逗号分隔）", False),
        ],
        "rss": [
            ("feeds", "RSS 订阅源（每行：url|分类，如 https://x.com/rss|科技）", False),
        ],
        "browser_history": [
            ("browser", "浏览器（chrome/firefox/edge）", False),
            ("history_path", "历史记录路径（auto 自动）", False),
        ],
    }.get(source, [])


def _feeds_to_text(feeds: list) -> str:
    if not isinstance(feeds, list):
        return ""
    lines = []
    for feed in feeds:
        if isinstance(feed, dict):
            lines.append(f"{feed.get('url', '')}|{feed.get('category', '')}")
    return "\n".join(lines)


def _text_to_feeds(text: str) -> list:
    feeds = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("|", 1)
        feeds.append({"url": parts[0].strip(), "category": parts[1].strip() if len(parts) > 1 else "rss"})
    return feeds


def _collect_fields(source: str, values: dict) -> dict:
    fields = {}
    for key, _, is_secret in _fields_for(source):
        raw = values.get(key, "")
        if source == "rss" and key == "feeds":
            fields[key] = _text_to_feeds(raw)
        elif source == "github" and key == "include_repos":
            fields[key] = [x.strip() for x in raw.split(",") if x.strip()]
        elif is_secret:
            fields[key] = raw
        else:
            fields[key] = raw
    return fields


st.subheader("我的数据源")
st.caption("数据源凭据加密保存在本地数据库中，只对你自己可见。")

sources = get_my_sources(config, user)
for item in sources:
    source = item["source"]
    with st.expander(f"{item.get('display_name') or item.get('plugin', source)} - {source}", expanded=False):
        values = {}
        for key, label, is_secret in _fields_for(source):
            current = item.get("config", {}).get(key, "")
            if source == "rss" and key == "feeds":
                default_text = _feeds_to_text(item.get("config", {}).get(key, [])) if not is_secret else ""
                values[key] = st.text_area(label, value=default_text, key=f"cfg_{source}_{key}")
            elif is_secret:
                has = item.get("has_secrets", {}).get(key, False)
                values[key] = st.text_input(label, value="***" if has else "", type="password", key=f"cfg_{source}_{key}")
            else:
                values[key] = st.text_input(label, value=str(current or ""), key=f"cfg_{source}_{key}")

        enabled = st.toggle("启用此数据源", value=item.get("enabled", False), key=f"enabled_{source}")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("保存", key=f"save_{source}"):
                fields = _collect_fields(source, values)
                save_source_config(config, user, source, fields, enabled)
                st.success("已保存")
                st.rerun()
        with col2:
            if st.button("测试连接", key=f"test_{source}"):
                result = test_source_connection(config, user, source)
                if result.get("ok"):
                    st.success(result.get("message", "连接成功"))
                else:
                    st.error(result.get("message", "连接失败"))
        with col3:
            if st.button("同步此源", key=f"sync_{source}"):
                task_id = start_sync(config, user, source=source)
                if task_id:
                    st.info(f"同步任务已启动：{task_id[:8]}")
                else:
                    results = run_sync_direct(config, user, source=source)
                    info = results.get(source, {})
                    if "error" in info:
                        st.error(f"同步失败：{info['error']}")
                    else:
                        st.success(f"同步完成，新增 {info.get('count', 0)} 条")


st.subheader("我的数据统计")
stats = get_stats(config, user)
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("总事件数", stats["total"])
with col2:
    st.metric("数据源数", len(stats.get("by_source", {})))
with col3:
    st.metric("事件类型数", len(stats.get("by_type", {})))

if stats.get("by_source"):
    st.subheader("按来源统计")
    for source, count in stats["by_source"].items():
        st.write(f"- {source}: {count} 条")


st.subheader("数据导出")
if st.button("导出我的数据", type="secondary"):
    events = get_events(config, user, limit=10000)
    import pandas as pd

    df = pd.DataFrame(
        [
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
        ]
    )
    csv = df.to_csv(index=False)
    st.download_button(
        label="下载 CSV",
        data=csv,
        file_name=f"events_{user['username']}.csv",
        mime="text/csv",
    )


st.subheader("配置文件")
with st.expander("查看完整配置"):
    safe_config = {
        k: "***" if any(s in str(v).lower() for s in ["token", "cookie", "secret"])
        else v
        for k, v in config.items()
    }
    st.json(safe_config)


if user.get("role") == "admin":
    st.subheader("用户管理（管理员）")
    users = admin_list_users(config, user)
    for u in users:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            with c1:
                st.markdown(f"**{u['username']}**（{u['role']}）")
                st.caption(f"状态：{u['status']}")
            with c2:
                if u["status"] == "pending":
                    if st.button("批准", key=f"approve_{u['id']}"):
                        admin_update_user(config, user, u["id"], status="active")
                        st.success("已批准")
                        st.rerun()
            with c3:
                if u["status"] == "active":
                    if st.button("禁用", key=f"disable_{u['id']}"):
                        try:
                            admin_update_user(config, user, u["id"], status="disabled")
                            st.success("已禁用")
                            st.rerun()
                        except RuntimeError as exc:
                            st.error(str(exc))
                elif u["status"] == "disabled":
                    if st.button("启用", key=f"enable_{u['id']}"):
                        admin_update_user(config, user, u["id"], status="active")
                        st.success("已启用")
                        st.rerun()
            with c4:
                new_password = st.text_input(
                    "重置密码", type="password", key=f"reset_{u['id']}", placeholder="留空不修改"
                )
                if st.button("重置", key=f"reset_btn_{u['id']}") and new_password:
                    if len(new_password) < 8:
                        st.error("密码至少 8 位")
                    else:
                        admin_update_user(config, user, u["id"], password=new_password)
                        st.success("密码已重置")
