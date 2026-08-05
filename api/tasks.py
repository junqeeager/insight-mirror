"""画像刷新与同步后台任务管理（数据库持久化 + 线程池）。"""

import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.exc import IntegrityError

from core.database import Database
from core.sync_service import sync_user
from analysis.profile import ProfileGenerator
from api.deps import ensure_initialized, get_config, get_db_url

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="profile-task")


class TaskConflictError(Exception):
    """同类任务正在运行。"""


def _open_db() -> Database:
    db = Database(get_db_url(get_config()))
    ensure_initialized(db)
    return db


def _new_task_id() -> str:
    return uuid.uuid4().hex[:12]


def start_task(user_id: str, kind: str, params: dict, run) -> str:
    """登记任务并提交线程池；同类 running 任务存在时抛 TaskConflictError。"""
    db = _open_db()
    try:
        existing = db.get_running_task(user_id, kind)
        if existing:
            raise TaskConflictError(f"同类任务正在运行: {existing['id']}")
        task_id = _new_task_id()
        try:
            db.create_task(task_id, user_id, kind, params)
        except IntegrityError:
            # 并发请求同时通过检查时，由唯一索引兜底拒绝后写入者
            raise TaskConflictError("同类任务正在运行")
        db.cleanup_tasks(keep_days=7)
    finally:
        db.close()

    def _runner():
        task_db = _open_db()
        try:
            result = run()
            task_db.update_task(task_id, status="done", result=result)
        except Exception as exc:
            task_db.update_task(task_id, status="error", error=str(exc))
        finally:
            task_db.close()

    _EXECUTOR.submit(_runner)
    return task_id


def refresh_profile(period: str = "weekly", user_id: str = "") -> str:
    """后台重建画像，返回 task_id。"""

    def _run() -> dict:
        db = _open_db()
        try:
            config = get_config()
            generator = ProfileGenerator(db, config.get("analysis", {}))
            profile = generator.generate(
                user_id=user_id, period=period, persist=True
            )
            return {"profile_id": profile.id}
        finally:
            db.close()

    return start_task(user_id, "profile_refresh", {"period": period}, _run)


def sync_user_task(user_id: str, source: str = None) -> str:
    """后台同步某个用户的数据源，返回 task_id。"""

    def _run() -> dict:
        config = get_config()
        db = _open_db()
        try:
            return {"results": sync_user(db, config, user_id, source=source)}
        finally:
            db.close()

    return start_task(user_id, "sync", {"source": source}, _run)


def get_task(task_id: str) -> dict:
    """查询任务状态（空 dict 表示不存在）。"""
    db = _open_db()
    try:
        row = db.get_task(task_id)
    finally:
        db.close()
    if not row:
        return {}
    return {
        "user_id": row["user_id"],
        "kind": row["kind"],
        "status": row["status"],
        "error": row.get("error"),
        "params": row.get("params") or {},
        "result": row.get("result") or {},
    }


def get_task_for_user(task_id: str, user_id: str) -> dict:
    """取任务状态，且校验任务属于当前用户（防止跨用户读取）。"""
    task = get_task(task_id)
    if not task:
        return {}
    if task.get("user_id") and task["user_id"] != user_id:
        return {}
    return task
