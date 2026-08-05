"""迁移 001：把旧版 topic-{word} ID 迁移为命名空间 ID。

- general 分类 -> topic-general-{word}
- cluster_N 分类 -> topic-cluster-cluster_N-{word}

已存在的同名新 ID 采用合并策略：重挂 event_topics 后删除旧行。
"""

from sqlalchemy import delete, select, update

from core.database import event_topics, topics


def _namespace(old_id: str, category: str) -> str:
    word = old_id[len("topic-"):]
    if category == "general":
        return f"topic-general-{word}"
    return f"topic-cluster-{category}-{word}"


def upgrade(db) -> None:
    """将历史 topic ID 改写为命名空间格式。"""
    with db.engine.begin() as conn:
        legacy_rows = conn.execute(
            select(topics)
            .where(
                topics.c.id.like("topic-%"),
                ~topics.c.id.like("topic-general-%"),
                ~topics.c.id.like("topic-cluster-%"),
            )
        ).mappings().all()

        for row in legacy_rows:
            old_id = row["id"]
            category = row["category"] or "general"
            new_id = _namespace(old_id, category)
            if new_id == old_id:
                continue

            existing = conn.execute(
                select(topics.c.id).where(
                    topics.c.id == new_id, topics.c.user_id == row["user_id"]
                )
            ).first()
            if existing is None:
                conn.execute(
                    topics.insert().values(
                        id=new_id,
                        user_id=row["user_id"],
                        name=row["name"],
                        category=row["category"],
                        frequency=row["frequency"],
                        weight=row["weight"],
                        first_seen=row["first_seen"],
                        last_seen=row["last_seen"],
                        related_topics=row["related_topics"],
                    )
                )

            conn.execute(
                update(event_topics)
                .where(
                    event_topics.c.topic_id == old_id,
                    event_topics.c.user_id == row["user_id"],
                )
                .values(topic_id=new_id)
            )
            conn.execute(
                delete(topics).where(
                    topics.c.id == old_id, topics.c.user_id == row["user_id"]
                )
            )
