"""管理员：用户管理"""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_db, require_admin
from api.schemas import AdminUserPatch, UserOut
from core.auth import hash_password
from core.database import Database

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def list_users(
    _admin: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """列出全部用户（不含密码哈希）。"""
    users = db.list_users()
    return [
        UserOut(
            id=u["id"],
            username=u["username"],
            role=u["role"],
            status=u["status"],
            created_at=u.get("created_at"),
            last_login_at=u.get("last_login_at"),
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    body: AdminUserPatch,
    admin: dict = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """批准/禁用用户或重置密码。"""
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.status is not None:
        if body.status not in {"pending", "active", "disabled"}:
            raise HTTPException(status_code=400, detail="状态不合法")
        if user_id == admin["id"] and body.status == "disabled":
            raise HTTPException(status_code=400, detail="不能禁用自己")
        db.update_user_status(user_id, body.status)
    if body.password is not None:
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="密码至少 8 位")
        db.update_user_password(user_id, hash_password(body.password))
    updated = db.get_user_by_id(user_id)
    return UserOut(
        id=updated["id"],
        username=updated["username"],
        role=updated["role"],
        status=updated["status"],
        created_at=updated.get("created_at"),
        last_login_at=updated.get("last_login_at"),
    )
