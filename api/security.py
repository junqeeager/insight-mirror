"""进程内安全工具：登录限流。"""

import threading
import time
from collections import defaultdict, deque


class LoginRateLimiter:
    """按 username+IP 的滑动窗口失败计数（单进程内存实现）。"""

    def __init__(self, max_attempts: int = 5, window_seconds: int = 900):
        self.max_attempts = max(1, int(max_attempts))
        self.window_seconds = max(1, int(window_seconds))
        self._attempts: dict = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _key(username: str, ip: str) -> str:
        return f"{username}:{ip}"

    def is_limited(self, username: str, ip: str) -> bool:
        now = time.monotonic()
        key = self._key(username, ip)
        with self._lock:
            queue = self._attempts[key]
            while queue and now - queue[0] > self.window_seconds:
                queue.popleft()
            return len(queue) >= self.max_attempts

    def record_failure(self, username: str, ip: str) -> None:
        key = self._key(username, ip)
        with self._lock:
            queue = self._attempts[key]
            queue.append(time.monotonic())
            while len(queue) > self.max_attempts:
                queue.popleft()

    def clear(self, username: str, ip: str) -> None:
        with self._lock:
            self._attempts.pop(self._key(username, ip), None)


_limiter: LoginRateLimiter = None


def get_login_limiter(config: dict) -> LoginRateLimiter:
    """按配置创建（或复用）登录限流器。"""
    global _limiter
    if _limiter is None:
        sec = config.get("security", {})
        _limiter = LoginRateLimiter(
            max_attempts=sec.get("login_max_attempts", 5),
            window_seconds=sec.get("login_window_seconds", 900),
        )
    return _limiter
