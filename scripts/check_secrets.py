"""Git 推送前密钥扫描器（纯标准库，无第三方依赖）。

用法：
    python3 scripts/check_secrets.py <path>...                # 扫描工作区文件
    python3 scripts/check_secrets.py --rev <sha> <path>...    # 扫描指定提交中的文件

检测到疑似真实凭据时以退出码 1 结束，便于 pre-push 钩子 fail-closed。
输出只包含规则名、文件路径与行号，不打印密钥本身。
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

_MAX_SCAN_BYTES = 10 * 1024 * 1024

_PLACEHOLDER_WORDS = {
    "xxx", "your_password", "your_username", "password", "pass",
    "changeme", "change_me", "redacted", "secret", "profile",
    "postgres", "root", "test", "example",
}


def _is_placeholder(value: str) -> bool:
    """判断值是否为示例/占位符（真实凭据不应被放行）。"""
    v = value.strip().strip("\"'")
    if not v:
        return True
    if v.startswith("${") and v.endswith("}"):
        return True
    if v.startswith("<") and v.endswith(">"):
        return True
    if v.lower() in _PLACEHOLDER_WORDS:
        return True
    if len(v) <= 12 and set(v) <= {"x", "X"}:
        return True
    if re.fullmatch(r"[A-Za-z0-9_]+_xxx", v):
        return True
    return False


def _valid_app_password(match: re.Match) -> bool:
    """APP_PASSWORD 只有写成真实字面值时才算命中。"""
    return not _is_placeholder(match.group("value"))


def _valid_db_password(match: re.Match) -> bool:
    """数据库 URL 中密码与用户名相同或为常见占位词时放行。"""
    password = match.group("pass")
    if not password or password == match.group("user"):
        return False
    return not _is_placeholder(password)


_CONTENT_RULES = [
    ("B 站 SESSDATA Cookie", re.compile(r"SESSDATA\s*=\s*[A-Za-z0-9%._-]{16,}"), None),
    ("B 站 bili_jct/CSRF 令牌", re.compile(r"(?:bili_jct|BILIBILI_CSRF)\s*=\s*[0-9a-fA-F]{16,}"), None),
    ("GitHub Token", re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), None),
    ("GitHub 细粒度 Token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), None),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}"), None),
    ("私钥块", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), None),
    ("Bearer Token", re.compile(r"Bearer [A-Za-z0-9._~+/=-]{20,}"), None),
    (
        "APP_PASSWORD 字面值",
        re.compile(r"(?m)^\s*APP_PASSWORD\s*=\s*(?P<value>.*)$"),
        _valid_app_password,
    ),
    (
        "带密码的数据库 URL",
        re.compile(
            r"(?i)(?:postgres(?:ql)?|mysql|mariadb|mongo(?:db)?|redis)"
            r"(?:\+[a-z0-9]+)?://(?P<user>[^:/@\s]*):(?P<pass>[^@\s/]+)@"
        ),
        _valid_db_password,
    ),
]


def _filename_rule(path: str) -> str | None:
    """按文件名判断是否可能携带凭据（示例模板放行）。"""
    name = path.rsplit("/", 1)[-1]
    if name == ".env" or (name.startswith(".env.") and not name.endswith(".example")):
        return "环境变量文件"
    if re.search(r"\.(pem|key|p12|pfx|asc)$", name, re.IGNORECASE):
        return "私钥/证书文件"
    if name.startswith("id_rsa") and not name.endswith(".pub"):
        return "SSH 私钥文件"
    if re.search(r"credentials\.json$", name, re.IGNORECASE):
        return "云服务凭证文件"
    if re.search(r"tunnel[^/]*\.json$", name, re.IGNORECASE):
        return "隧道凭证文件"
    return None


def scan_bytes(path: str, data: bytes) -> list[str]:
    """扫描单个文件（名称 + 内容），返回形如“规则（第 N 行）”的发现列表。"""
    findings: list[str] = []
    rule = _filename_rule(path)
    if rule:
        findings.append(f"{rule}（文件名）")

    if len(data) > _MAX_SCAN_BYTES or b"\x00" in data[:4096]:
        return findings

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("utf-8", errors="replace")

    for name, regex, validator in _CONTENT_RULES:
        for match in regex.finditer(text):
            if validator is not None and not validator(match):
                continue
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{name}（第 {line} 行）")
    return findings


def _read_from_rev(rev: str, path: str) -> bytes | None:
    """从指定提交读取文件内容；读取失败返回 None。"""
    proc = subprocess.run(
        ["git", "show", f"{rev}:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return proc.stdout if proc.returncode == 0 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检测提交内容中的疑似真实凭据")
    parser.add_argument("--rev", metavar="SHA", help="从指定提交读取文件内容（默认读取工作区）")
    parser.add_argument("paths", nargs="*", help="要扫描的文件路径")
    args = parser.parse_args(argv)

    total = 0
    for path in args.paths:
        if args.rev:
            data = _read_from_rev(args.rev, path)
            if data is None:
                print(f"[secret-guard] 跳过无法读取的文件: {path}", file=sys.stderr)
                continue
        else:
            try:
                data = Path(path).read_bytes()
            except OSError as exc:
                print(f"[secret-guard] 跳过无法读取的文件: {path}（{exc}）", file=sys.stderr)
                continue

        for finding in scan_bytes(path, data):
            print(f"[secret-guard] 疑似密钥：{finding} -> {path}")
            total += 1

    if total:
        print("[secret-guard] 检测到疑似敏感信息，已阻止（请人工确认并移除后再推送）。", file=sys.stderr)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
