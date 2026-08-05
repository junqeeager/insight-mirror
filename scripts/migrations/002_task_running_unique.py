"""迁移 002：tasks 表增加 running 任务的部分唯一索引。

- 对同 (user_id, kind) 的重复 running 记录先清理（保留最新一条），
- 再创建部分唯一索引，避免并发启动同类任务时双跑。
- SQLite 与 PostgreSQL 均支持 CREATE UNIQUE INDEX ... WHERE，幂等可重跑。
"""

from sqlalchemy import text


def upgrade(db) -> None:
    """清理重复 running 任务并创建部分唯一索引。"""
    with db.engine.begin() as conn:
        dupes = conn.execute(
            text(
                "SELECT user_id, kind FROM tasks "
                "WHERE status = 'running' "
                "GROUP BY user_id, kind HAVING COUNT(*) > 1"
            )
        ).mappings().all()
        for row in dupes:
            conn.execute(
                text(
                    "DELETE FROM tasks "
                    "WHERE status = 'running' "
                    "AND user_id = :user_id AND kind = :kind "
                    "AND id NOT IN ("
                    "  SELECT id FROM tasks "
                    "  WHERE status = 'running' "
                    "  AND user_id = :user_id AND kind = :kind "
                    "  ORDER BY created_at DESC LIMIT 1"
                    ")"
                ),
                {"user_id": row["user_id"], "kind": row["kind"]},
            )
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_running "
                "ON tasks (user_id, kind) WHERE status = 'running'"
            )
        )
