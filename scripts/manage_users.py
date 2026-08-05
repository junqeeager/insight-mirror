"""用户管理 CLI：创建管理员、审核、禁用、重置密码。"""

import argparse
import getpass
import os
import sys
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from core.auth import hash_password  # noqa: E402
from core.database import Database, database_url  # noqa: E402
from core.utils import load_config, setup_logging  # noqa: E402


def _connect(config: dict) -> Database:
    db = Database(database_url(config))
    db.init_tables()
    return db


def _password_from_args_or_env(args) -> str:
    password = args.password or os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        password = getpass.getpass("请输入密码（至少 8 位）: ")
    if len(password) < 8:
        raise SystemExit("❌ 密码至少 8 位")
    return password


def cmd_create_admin(args) -> int:
    username = (args.username or "admin").strip().lower()
    password = _password_from_args_or_env(args)
    db = _connect(load_config(args.config))
    try:
        if db.get_user_by_username(username):
            print(f"⚠️ 用户 {username} 已存在")
            return 1
        db.create_user(username, hash_password(password), role="admin", status="active")
        print(f"✅ 管理员 {username} 已创建")
        return 0
    finally:
        db.close()


def cmd_list(args) -> int:
    db = _connect(load_config(args.config))
    try:
        users = db.list_users()
        if not users:
            print("（暂无用户）")
            return 0
        print(f"{'用户名':<20} {'角色':<8} {'状态':<10} 创建时间")
        for u in users:
            created = u["created_at"].strftime("%Y-%m-%d %H:%M") if u["created_at"] else "-"
            print(f"{u['username']:<20} {u['role']:<8} {u['status']:<10} {created}")
        return 0
    finally:
        db.close()


def cmd_set_status(args, status: str) -> int:
    db = _connect(load_config(args.config))
    try:
        user = db.get_user_by_username(args.username.strip().lower())
        if not user:
            print(f"❌ 用户 {args.username} 不存在")
            return 1
        db.update_user_status(user["id"], status)
        print(f"✅ 用户 {user['username']} 状态已更新为 {status}")
        return 0
    finally:
        db.close()


def cmd_reset_password(args) -> int:
    password = _password_from_args_or_env(args)
    db = _connect(load_config(args.config))
    try:
        user = db.get_user_by_username(args.username.strip().lower())
        if not user:
            print(f"❌ 用户 {args.username} 不存在")
            return 1
        db.update_user_password(user["id"], hash_password(password))
        print(f"✅ 用户 {user['username']} 密码已重置")
        return 0
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="用户管理工具")
    parser.add_argument("--config", type=str, default="config.yaml", help="配置文件路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="创建管理员账号")
    p_admin.add_argument("--username", default="admin")
    p_admin.add_argument("--password", default="")
    p_admin.set_defaults(func=cmd_create_admin)

    sub.add_parser("list", help="列出全部用户").set_defaults(func=cmd_list)

    for name, status in (("approve", "active"), ("disable", "disabled")):
        p = sub.add_parser(name, help=f"{name} 用户")
        p.add_argument("username")
        p.set_defaults(func=lambda args, _status=status: cmd_set_status(args, _status))

    p_reset = sub.add_parser("reset-password", help="重置用户密码")
    p_reset.add_argument("username")
    p_reset.add_argument("--password", default="")
    p_reset.set_defaults(func=cmd_reset_password)

    args = parser.parse_args()
    setup_logging()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
