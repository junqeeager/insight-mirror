"""迁移 003：新增 oauth_flows 表，保存 OAuth PKCE 授权流临时状态。

- state 为主键，user_id 归属校验；
- expires_at 支持定期清理，防止堆积；
- SQLite 与 PostgreSQL 通用，幂等可重跑。
"""

from sqlalchemy import text


def upgrade(db) -> None:
    """创建 oauth_flows 表与用户索引（已存在时跳过）。"""
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS oauth_flows ("
                "  user_id VARCHAR NOT NULL,"
                "  state VARCHAR PRIMARY KEY,"
                "  code_verifier VARCHAR NOT NULL,"
                "  expires_at TIMESTAMP NOT NULL,"
                "  FOREIGN KEY (user_id) REFERENCES users(id)"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_oauth_flows_user "
                "ON oauth_flows (user_id)"
            )
        )
