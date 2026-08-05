"""推送密钥扫描器测试（离线：内存样例 + /tmp 临时 Git 仓库）。"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from scripts.check_secrets import _is_placeholder, scan_bytes  # noqa: E402

_SCANNER = str(Path(project_root) / "scripts" / "check_secrets.py")
_PRE_PUSH = str(Path(project_root) / "deploy" / "pre-push")

_ENV_EXAMPLE = """\
# Bilibili
BILIBILI_COOKIE=SESSDATA=xxx; bili_jct=xxx
BILIBILI_CSRF=xxx

# GitHub
GITHUB_TOKEN=ghp_xxx
GITHUB_USERNAME=your_username

# 公开看板访问密码
APP_PASSWORD=
"""


def _bili_cookie() -> str:
    return "SESSDATA=" + "0123456789abcdef" * 3


def _bili_jct() -> str:
    return "bili_jct=" + "0" * 32


def _github_token() -> str:
    return "ghp_" + "0" * 36


def _github_fine_grained_token() -> str:
    return "github_pat_" + "A" * 60


def _private_key() -> str:
    return "-----BEGIN " + "OPENSSH PRIVATE KEY-----"


def _bearer_token() -> str:
    return "Bearer " + "a" * 40


def _db_url() -> str:
    return "postgresql+psycopg://admin:" + "RealPass123" + "@db.example.com:5432/profile"


def _aws_key() -> str:
    return "AKIA" + "1234567890ABCDEF"


def _findings(path: str, content: str) -> list:
    return scan_bytes(path, content.encode("utf-8"))


def test_placeholder_detection():
    assert _is_placeholder("")
    assert _is_placeholder("xxx")
    assert _is_placeholder("ghp_xxx")
    assert _is_placeholder("${GITHUB_TOKEN}")
    assert _is_placeholder("your_password")
    assert _is_placeholder("profile")
    assert not _is_placeholder("my-secret-123")
    assert not _is_placeholder("RealPass123")


def test_allowed_samples():
    allowed = [
        (".env.example", _ENV_EXAMPLE),
        ("config.yaml", 'url: sqlite:///./data/profile.db\ntoken: "${GITHUB_TOKEN}"\n'),
        ("README.md", "复制 `SESSDATA=xxx` 和 `bili_jct=xxx` 的值\n设置 `APP_PASSWORD` 作为访问密码\n"),
        ("frontend/auth.py", 'expected = os.environ.get("APP_PASSWORD", "")\n'),
        ("docs/example.md", "postgresql+psycopg://profile:profile@localhost:5433/profile\n"),
        ("lib/binary.dat", "\x00\x01" + _bili_cookie()),
    ]
    for name, content in allowed:
        assert _findings(name, content) == [], (name, _findings(name, content))


def test_blocked_samples():
    blocked = [
        (".env", "BILIBILI_COOKIE=" + _bili_cookie() + "\n"),
        ("config.local.yaml", _bili_jct() + "\n"),
        (".env", "GITHUB_TOKEN=" + _github_token() + "\n"),
        (
            ".env",
            "GITHUB_TOKEN=" + _github_fine_grained_token() + "\n",
        ),
        (".env", "APP_PASSWORD=my-secret-123\n"),
        ("key.pem", _private_key() + "\nabc\n-----END OPENSSH PRIVATE KEY-----\n"),
        ("settings.py", 'headers = {"Authorization": "' + _bearer_token() + '"}\n'),
        ("README.md", _db_url() + "\n"),
        ("aws.txt", _aws_key()),
        ("id_rsa", "not really a key"),
        ("cloudflared-credentials.json", "{}"),
        (".env.local", "# nothing"),
    ]
    for name, content in blocked:
        assert _findings(name, content), (name, content)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_cli_rev_scan():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "config", "user.email", "t@example.com")
        _git(repo, "config", "user.name", "t")

        env_file = repo / ".env"
        env_file.write_text("APP_PASSWORD=my-secret-123\n", encoding="utf-8")
        _git(repo, "add", ".env")
        _git(repo, "commit", "-q", "-m", "bad")
        proc = subprocess.run(
            [sys.executable, _SCANNER, "--rev", "HEAD", ".env"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 1, proc.stdout

        # .env 文件名本身永远拦截；换普通文件验证内容放行路径
        ok_file = repo / "ok.yaml"
        ok_file.write_text("APP_PASSWORD=\n", encoding="utf-8")
        _git(repo, "add", "ok.yaml")
        _git(repo, "commit", "-q", "-m", "fix")
        proc = subprocess.run(
            [sys.executable, _SCANNER, "--rev", "HEAD", "ok.yaml"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stdout


def test_pre_push_hook_blocks_and_allows():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        src = root / "src"
        src.mkdir()
        remote = root / "remote.git"

        _git(src, "init", "-q", "-b", "main")
        _git(src, "config", "user.email", "t@example.com")
        _git(src, "config", "user.name", "t")

        hooks_dir = src / ".git" / "hooks"
        shutil.copy(_PRE_PUSH, hooks_dir / "pre-push")
        os.chmod(hooks_dir / "pre-push", 0o755)
        (src / "scripts").mkdir()
        shutil.copy(_SCANNER, src / "scripts" / "check_secrets.py")

        (src / "ok.txt").write_text("hello\n", encoding="utf-8")
        _git(src, "add", "ok.txt")
        _git(src, "commit", "-q", "-m", "ok")

        _git(root, "init", "--bare", "-q", "remote.git")
        proc = subprocess.run(
            ["git", "push", "-u", str(remote), "main"],
            cwd=src,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr

        (src / ".env").write_text("APP_PASSWORD=my-secret-123\n", encoding="utf-8")
        _git(src, "add", ".env")
        _git(src, "commit", "-q", "-m", "bad")
        proc = subprocess.run(
            ["git", "push", str(remote), "main"],
            cwd=src,
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0, proc.stdout
        assert "secret-guard" in proc.stderr

        # 非 ASCII 文件名也必须被扫描，防止路径转义绕过
        unicode_file = src / "秘钥.txt"
        unicode_file.write_text("APP_PASSWORD=my-secret-123\n", encoding="utf-8")
        _git(src, "add", "秘钥.txt")
        _git(src, "commit", "-q", "-m", "bad-unicode")
        proc = subprocess.run(
            ["git", "push", str(remote), "main"],
            cwd=src,
            capture_output=True,
            text=True,
        )
        assert proc.returncode != 0, proc.stdout
        assert "secret-guard" in proc.stderr

        # 清除全部问题文件后推送恢复
        (src / ".env").unlink()
        unicode_file.unlink()
        _git(src, "add", "-A")
        _git(src, "commit", "-q", "-m", "fix")
        proc = subprocess.run(
            ["git", "push", str(remote), "main"],
            cwd=src,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("🎉 密钥扫描器测试通过！")
