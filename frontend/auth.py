"""登录 / 注册鉴权（API 优先，失败回退直连数据库）"""

import re
import sys
from pathlib import Path

import httpx
import streamlit as st

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.auth import hash_password, verify_password  # noqa: E402
from core.database import Database, database_url  # noqa: E402
from core.utils import load_config  # noqa: E402

_API_TIMEOUT = 3.0
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{3,32}$")


def _api_base(config: dict) -> str:
    return config.get("frontend", {}).get("api_base", "http://localhost:8502").rstrip("/")


def _use_api(config: dict) -> bool:
    return config.get("frontend", {}).get("use_api", True)


def _db(config: dict) -> Database:
    db = Database(database_url(config))
    db.init_tables()
    return db


def _validate(username: str, password: str) -> str:
    if not _USERNAME_RE.match(username):
        return "用户名需为 3-32 位字母/数字/下划线/中文"
    if len(password) < 8:
        return "密码至少 8 位"
    return ""


def register_user(config: dict, username: str, password: str) -> tuple:
    """注册（pending）；返回 (ok, message)。"""
    username = username.strip().lower()
    error = _validate(username, password)
    if error:
        return False, error
    if _use_api(config):
        try:
            resp = httpx.post(
                f"{_api_base(config)}/api/v1/auth/register",
                json={"username": username, "password": password},
                timeout=_API_TIMEOUT,
            )
            if resp.status_code == 200:
                return True, "注册成功，请等待管理员审核后登录"
            detail = resp.json().get("detail", "注册失败")
            return False, detail if isinstance(detail, str) else "注册失败"
        except Exception:
            logger_warning("注册 API 不可用，回退直连数据库")
    db = _db(config)
    try:
        if db.get_user_by_username(username):
            return False, "用户名已存在"
        db.create_user(username, hash_password(password), role="user", status="pending")
        return True, "注册成功，请等待管理员审核后登录"
    finally:
        db.close()


def login_user(config: dict, username: str, password: str) -> tuple:
    """登录；返回 (ok, user, token, message)。"""
    username = username.strip().lower()
    if _use_api(config):
        try:
            resp = httpx.post(
                f"{_api_base(config)}/api/v1/auth/login",
                json={"username": username, "password": password},
                timeout=_API_TIMEOUT,
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, data["user"], data["token"], None
            detail = resp.json().get("detail", "登录失败")
            return False, None, None, detail if isinstance(detail, str) else "登录失败"
        except Exception:
            logger_warning("登录 API 不可用，回退直连数据库")
    db = _db(config)
    try:
        user = db.get_user_by_username(username)
        if not user or not verify_password(password, user["password_hash"]):
            return False, None, None, "用户名或密码错误"
        if user["status"] != "active":
            return False, None, None, "账号未启用，请联系管理员"
        return (
            True,
            {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "status": user["status"],
            },
            None,
            None,
        )
    finally:
        db.close()


def render_auth_ui() -> None:
    """渲染登录/注册表单；登录成功后写入 session_state 并 rerun。"""
    config = load_config()
    st.markdown("### 🔐 登录 / 注册")
    mode = st.radio("登录方式", ["登录", "注册"], horizontal=True)
    username = st.text_input("用户名")
    password = st.text_input("密码", type="password")
    confirm = None
    if mode == "注册":
        confirm = st.text_input("确认密码", type="password")

    if st.button("登录" if mode == "登录" else "注册", width="stretch"):
        if mode == "注册":
            if password != confirm:
                st.error("两次输入的密码不一致")
            else:
                ok, message = register_user(config, username, password)
                if ok:
                    st.success(message)
                else:
                    st.error(message)
        else:
            ok, user, token, message = login_user(config, username, password)
            if ok:
                st.session_state["user"] = user
                st.session_state["token"] = token
                st.rerun()
            else:
                st.error(message)


def require_login() -> dict:
    """功能页调用；未登录时渲染登录/注册表单并停止后续脚本。"""
    user = st.session_state.get("user")
    if user:
        return user
    render_auth_ui()
    st.stop()


def logout() -> None:
    """清除登录态（token 由 API 端失效）。"""
    config = load_config()
    token = st.session_state.get("token")
    if token and _use_api(config):
        try:
            httpx.post(
                f"{_api_base(config)}/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
                timeout=_API_TIMEOUT,
            )
        except Exception:
            pass
    st.session_state.pop("user", None)
    st.session_state.pop("token", None)


def logger_warning(message: str) -> None:
    import logging

    logging.getLogger("frontend.auth").warning(message)
