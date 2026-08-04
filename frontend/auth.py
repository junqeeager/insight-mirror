"""公开看板访问密码门"""

import os
import secrets
from pathlib import Path

import streamlit as st

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - 项目依赖中始终安装 python-dotenv
    load_dotenv = None


def _load_env() -> None:
    """从项目根目录加载 .env（不覆盖已存在的环境变量）。"""
    env_path = Path(".env")
    if load_dotenv is not None and env_path.exists():
        load_dotenv(env_path)


def _password_configured() -> bool:
    """检查是否配置了 APP_PASSWORD。"""
    return bool(os.environ.get("APP_PASSWORD"))


def _verify_password(password: str) -> bool:
    """使用常量时间比较校验密码，避免时序侧信道。"""
    expected = os.environ.get("APP_PASSWORD", "")
    return secrets.compare_digest(password, expected)


def require_auth() -> None:
    """在数据渲染前调用；未登录时展示登录页并停止后续脚本执行。"""
    _load_env()

    if st.session_state.get("authenticated"):
        return

    st.markdown("### 🔒 需要访问密码")

    if not _password_configured():
        st.error(
            "服务器未配置 APP_PASSWORD 环境变量，无法提供登录访问。"
            "请管理员在 .env 中设置 APP_PASSWORD 后重启 Streamlit。"
        )
        st.stop()

    password = st.text_input("请输入访问密码", type="password", key="auth_password")
    if st.button("登录", width="stretch"):
        if _verify_password(password):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("密码错误，请重试。")

    st.stop()
