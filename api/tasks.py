"""画像刷新后台任务管理"""

import threading
import uuid

from core.database import Database
from analysis.profile import ProfileGenerator
from api.deps import get_config, get_db_path

TASKS: dict = {}
TASKS_LOCK = threading.Lock()


def refresh_profile(period: str = "weekly") -> str:
    """后台重建画像，返回 task_id"""
    task_id = uuid.uuid4().hex[:12]
    with TASKS_LOCK:
        TASKS[task_id] = {"status": "running", "profile_id": None, "error": None}

    config = get_config()

    def _run():
        profile_id = None
        try:
            db = Database(get_db_path(config))
            db.init_tables()
            try:
                generator = ProfileGenerator(db, config.get("analysis", {}))
                profile = generator.generate(period=period, persist=True)
                profile_id = profile.id
            finally:
                db.close()
            with TASKS_LOCK:
                TASKS[task_id] = {"status": "done", "profile_id": profile_id, "error": None}
        except Exception as e:
            with TASKS_LOCK:
                TASKS[task_id] = {"status": "error", "profile_id": None, "error": str(e)}

    threading.Thread(target=_run, daemon=True).start()
    return task_id


def get_task(task_id: str):
    with TASKS_LOCK:
        return dict(TASKS.get(task_id, {}))
