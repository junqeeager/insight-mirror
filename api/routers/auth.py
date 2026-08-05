"""注册 / 登录 / 登出"""

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException

from api.deps import get_current_user, get_db
from api.schemas import LoginIn, LoginOut, RegisterIn, UserOut
from core.auth import generate_session_token, hash_password, hash_token, verify_password
from core.database import Database

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{3,32}$")


@router.post("/register", response_model=UserOut, status_code=200)
def register(body: RegisterIn, db: Database = Depends(get_db)):
    """注册账号（默认 pending，需管理员批准）。"""
    username = body.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="用户名需为 3-32 位字母/数字/下划线/中文")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="密码至少 8 位")
    if db.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    user_id = db.create_user(
        username, hash_password(body.password), role="user", status="pending"
    )
    user = db.get_user_by_id(user_id)
    return UserOut(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        status=user["status"],
        created_at=user.get("created_at"),
        last_login_at=user.get("last_login_at"),
    )


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Database = Depends(get_db)):
    """登录并签发 30 天有效的会话 token。"""
    user = db.get_user_by_username(body.username.strip())
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if user["status"] != "active":
        raise HTTPException(status_code=403, detail="账号未启用，请联系管理员")
    raw_token, token_hash = generate_session_token()
    db.create_session(token_hash, user["id"], datetime.now() + timedelta(days=30))
    db.touch_last_login(user["id"])
    user = db.get_user_by_id(user["id"])
    return LoginOut(
        token=raw_token,
        user=UserOut(
            id=user["id"],
            username=user["username"],
            role=user["role"],
            status=user["status"],
            created_at=user.get("created_at"),
            last_login_at=user.get("last_login_at"),
        ),
    )


@router.post("/logout", status_code=200)
def logout(
    authorization: str = Header(default=""),
    _user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """登出并删除当前会话。"""
    if authorization.startswith("Bearer "):
        db.delete_session(hash_token(authorization[len("Bearer "):].strip()))
    return {"ok": True}
