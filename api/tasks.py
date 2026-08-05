"""画像刷新后台任务管理"""

import threading
import uuid

from core.database import Database
from core.sync_service import sync_user
from analysis.profile import ProfileGenerator
from api.deps import get_config, get_db_url

TASKS: dict = {}
TASKS_LOCK = threading.Lock()


def _register_task(user_id: str = "") -> str:
    """创建任务占位，返回 task_id。"""
    task_id = uuid.uuid4().hex[:12]
    with TASKS_LOCK:
        TASKS[task_id] = {"status": "running", "error": None, "user_id": user_id}
    return task_id


def refresh_profile(period: str = "weekly", user_id: str = "") -> str:
    """后台重建画像，返回 task_id"""
    task_id = _register_task(user_id)

    config = get_config()

    def _run():
        profile_id = None
        try:
            db = Database(get_db_url(config))
            db.init_tables()
            try:
                generator = ProfileGenerator(db, config.get("analysis", {}))
                profile = generator.generate(
                    user_id=user_id, period=period, persist=True
                )
                profile_id = profile.id
            finally:
                db.close()
            with TASKS_LOCK:
                TASKS[task_id] = {
                    "status": "done",
                    "profile_id": profile_id,
                    "error": None,
                    "user_id": user_id,
                }
        except Exception as e:
            with TASKS_LOCK:
                TASKS[task_id] = {
                    "status": "error",
                    "profile_id": None,
                    "error": str(e),
                    "user_id": user_id,
                }

    threading.Thread(target=_run, daemon=True).start()
    return task_id


def sync_user_task(user_id: str, source: str = None) -> str:
    """后台同步某个用户的数据源，返回 task_id"""
    task_id = _register_task(user_id)
    config = get_config()

    def _run():
        try:
            db = Database(get_db_url(config))
            db.init_tables()
            try:
                results = sync_user(db, config, user_id, source=source)
            finally:
                db.close()
            with TASKS_LOCK:
                TASKS[task_id] = {
                    "status": "done",
                    "results": results,
                    "error": None,
                    "user_id": user_id,
                }
        except Exception as e:
            with TASKS_LOCK:
                TASKS[task_id] = {
                    "status": "error",
                    "results": {},
                    "error": str(e),
                    "user_id": user_id,
                }

    threading.Thread(target=_run, daemon=True).start()
    return task_id


def get_task(task_id: str):
    with TASKS_LOCK:
        return dict(TASKS.get(task_id, {}))


def get_task_for_user(task_id: str, user_id: str):
    """取任务状态，且校验任务属于当前用户（防止跨用户读取）。"""
    task = get_task(task_id)
    if not task:
        return None
    if task.get("user_id") and task["user_id"] != user_id:
        return None
    return task
