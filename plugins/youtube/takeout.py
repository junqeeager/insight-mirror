"""Google Takeout 自动导出（非官方内部接口）

Takeout 网页端通过内部接口创建/轮询“只含 YouTube 观看历史”的批量导出。
Google 未公开此接口，字段可能随网页改版变化，因此本模块集中处理请求构造与
响应解析，并把鉴权失败、格式变化翻译成可读错误；若 Google 拒绝自动导出，
用户仍可退回“导入观看历史（Takeout JSON）”手动上传。

说明：2026-08 实测前的字段以 Takeout 网页端抓包整理为准，若 Google 改版，
只需调整 CREATE_BATCH_PAYLOAD 与解析函数，无需改动后台任务与前端。
"""

import json
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

import httpx

TAKEOUT_BASE = "https://takeout.google.com/takeout/v1"
DEFAULT_POLL_INTERVAL_SECONDS = 15
DEFAULT_POLL_TIMEOUT_SECONDS = 30 * 60
DEFAULT_MAX_ARCHIVE_MB = 200
DEFAULT_MAX_TOTAL_MB = 1024

# 创建导出时的请求体。字段含义：
#   serviceIds / selectedDataToInclude —— 只导出 YouTube；
#   dataToInclude[].selectedProductIds —— 只导出观看历史（watch-history.json）；
#   deliveryMethod DOWNLOAD —— 下载 zip 而非发邮件/存网盘；
#   fileSize —— 单个压缩包上限，超过会分卷。
CREATE_BATCH_PAYLOAD = {
    "batch": {
        "exportTargetType": "THIRD_PARTY",
        "serviceIds": ["youtube"],
        "selectedDataToInclude": ["youtube"],
        "dataToInclude": [
            {
                "serviceId": "youtube",
                "selectedProductIds": ["youtube_history"],
            }
        ],
        "deliveryMethod": "DOWNLOAD",
        "fileType": "ZIP",
        "fileSize": "200MB",
        "notifyEmail": False,
    }
}

IN_PROGRESS_STATUSES = {
    "PROCESSING",
    "QUEUED",
    "CREATED",
    "PENDING",
    "BUILDING",
    "COUNTING",
    "UNKNOWN",
}
DONE_STATUSES = {"COMPLETED", "SUCCEEDED", "DONE", "READY"}
FAILED_STATUSES = {"FAILED", "CANCELLED", "CANCELED", "ERROR"}

ProgressCallback = Callable[[str], None]


class TakeoutError(RuntimeError):
    """Takeout 自动导出失败（通用）。"""


class TakeoutAuthError(TakeoutError):
    """Google 拒绝访问 Takeout（token 失效或需要浏览器会话）。"""


class TakeoutFormatError(TakeoutError):
    """Takeout 接口返回格式与预期不符（Google 改版或端点错误）。"""


class TakeoutExportFailed(TakeoutError):
    """Google 侧导出任务失败。"""


def _noop_progress(_message: str) -> None:
    """默认进度回调：什么都不做。"""


class TakeoutExporter:
    """创建并下载只含 YouTube 观看历史的 Takeout 导出。"""

    def __init__(
        self,
        access_token: str,
        max_archive_mb: int = DEFAULT_MAX_ARCHIVE_MB,
        max_total_mb: int = DEFAULT_MAX_TOTAL_MB,
        poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
        poll_timeout: int = DEFAULT_POLL_TIMEOUT_SECONDS,
        client: Optional[httpx.Client] = None,
    ):
        self.access_token = access_token
        self.max_archive_bytes = max(1, int(max_archive_mb)) * 1024 * 1024
        self.max_total_bytes = max(1, int(max_total_mb)) * 1024 * 1024
        self.poll_interval = max(0, int(poll_interval))
        self.poll_timeout = max(1, int(poll_timeout))
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(30.0, read=300.0),
            follow_redirects=True,
        )
        self._owns_client = client is None

    # ---------- 请求辅助 ----------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Origin": "https://takeout.google.com",
            "Referer": "https://takeout.google.com/",
        }

    def _raise_for_auth(self, resp: httpx.Response) -> None:
        """把鉴权失败翻译成可读错误。"""
        if resp.status_code in (401, 403):
            raise TakeoutAuthError(
                "Google 拒绝访问 Takeout（HTTP "
                f"{resp.status_code}）。请重新连接 YouTube 授权后重试；"
                "若仍失败，可改用“导入观看历史（Takeout JSON）”手动上传。"
            )
        content_type = (resp.headers.get("content-type") or "").lower()
        if "text/html" in content_type or "login" in content_type:
            raise TakeoutAuthError(
                "Takeout 返回了登录页，自动导出需要 Google 浏览器会话。"
                "请重新连接 YouTube 授权后重试，或使用手动上传。"
            )

    @staticmethod
    def _json(resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise TakeoutFormatError(
                "Takeout 返回的不是 JSON（可能是登录页或接口已改版）"
            )
        if not isinstance(data, dict):
            raise TakeoutFormatError("Takeout 返回格式异常（应为 JSON 对象）")
        return data

    # ---------- 创建与轮询 ----------

    def create_batch(self) -> str:
        """创建只含 YouTube 观看历史的导出，返回批次 ID。"""
        try:
            resp = self.client.post(
                f"{TAKEOUT_BASE}/batches",
                json=CREATE_BATCH_PAYLOAD,
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise TakeoutError(f"请求 Takeout 失败: {exc}")
        self._raise_for_auth(resp)
        if resp.status_code >= 400:
            raise TakeoutError(
                f"Takeout 创建导出失败（HTTP {resp.status_code}）："
                f"{resp.text[:300]}"
            )
        data = self._json(resp)
        batch_id = (
            data.get("batchId")
            or data.get("batch_id")
            or data.get("id")
            or (data.get("batch") or {}).get("id")
        )
        if not batch_id:
            raise TakeoutFormatError(
                "Takeout 返回中未找到导出批次 ID，接口格式可能已变化"
            )
        return str(batch_id)

    def poll_until_ready(
        self,
        batch_id: str,
        progress: Optional[ProgressCallback] = None,
    ) -> dict:
        """轮询批次状态，直到 COMPLETED 或失败；返回完成时的完整响应。"""
        progress = progress or _noop_progress
        deadline = time.monotonic() + self.poll_timeout
        waited = 0
        while True:
            try:
                resp = self.client.get(
                    f"{TAKEOUT_BASE}/batches/{batch_id}",
                    headers=self._headers(),
                )
            except httpx.HTTPError as exc:
                raise TakeoutError(f"查询 Takeout 导出状态失败: {exc}")
            self._raise_for_auth(resp)
            if resp.status_code == 404:
                raise TakeoutFormatError(
                    "Takeout 导出任务不存在（可能已过期或接口改版）"
                )
            if resp.status_code >= 400:
                raise TakeoutError(
                    f"查询 Takeout 导出状态失败（HTTP {resp.status_code}）"
                )
            data = self._json(resp)
            status = str(data.get("status") or "").upper()
            if status in DONE_STATUSES:
                return data
            if status in FAILED_STATUSES:
                reason = (
                    data.get("failReason")
                    or data.get("error")
                    or data.get("message")
                    or "未知原因"
                )
                raise TakeoutExportFailed(f"Google 导出任务失败：{reason}")
            if status and status not in IN_PROGRESS_STATUSES:
                # 遇到未知状态先按处理中处理，避免误判失败
                pass
            percent = data.get("percentDone")
            percent_text = f"（{percent}%）" if percent is not None else ""
            progress(
                f"等待 Google 打包导出{percent_text}…已等待 {waited} 秒，"
                "完整观看历史通常需要几分钟"
            )
            if time.monotonic() >= deadline:
                raise TakeoutError(
                    "等待 Google 打包导出超时"
                    f"（{self.poll_timeout // 60} 分钟），请稍后重试"
                )
            if self.poll_interval:
                time.sleep(self.poll_interval)
            waited += self.poll_interval

    # ---------- 下载与解压 ----------

    def download_archives(
        self,
        batch_data: dict,
        target_dir: Path,
        progress: Optional[ProgressCallback] = None,
    ) -> List[Path]:
        """下载所有分卷压缩包到 target_dir，返回本地文件路径列表。"""
        progress = progress or _noop_progress
        urls = self._extract_download_urls(batch_data)
        if not urls:
            raise TakeoutFormatError(
                "Takeout 导出已完成但响应中没有下载地址，接口格式可能已变化"
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        paths: List[Path] = []
        total_bytes = 0
        for index, url in enumerate(urls, start=1):
            if url.startswith("/"):
                url = f"https://takeout.google.com{url}"
            try:
                with self.client.stream(
                    "GET", url, headers=self._headers()
                ) as resp:
                    self._raise_for_auth(resp)
                    if resp.status_code >= 400:
                        raise TakeoutError(
                            f"下载 Takeout 压缩包失败（HTTP {resp.status_code}）"
                        )
                    filename = f"takeout-part-{index}.zip"
                    dest = target_dir / filename
                    size = 0
                    with dest.open("wb") as handle:
                        for chunk in resp.iter_bytes(1024 * 1024):
                            size += len(chunk)
                            total_bytes += len(chunk)
                            if size > self.max_archive_bytes:
                                raise TakeoutError(
                                    "单个 Takeout 压缩包超过 "
                                    f"{self.max_archive_bytes // (1024 * 1024)}MB"
                                    " 上限，无法自动导入"
                                )
                            if total_bytes > self.max_total_bytes:
                                raise TakeoutError(
                                    "Takeout 压缩包总大小超过 1GB 上限，"
                                    "无法自动导入；可尝试手动上传"
                                )
                            handle.write(chunk)
                    paths.append(dest)
                    progress(
                        f"已下载第 {index}/{len(urls)} 个压缩包"
                        f"（{size / (1024 * 1024):.1f}MB）"
                    )
            except httpx.HTTPError as exc:
                raise TakeoutError(f"下载 Takeout 压缩包失败: {exc}")
        return paths

    @staticmethod
    def _extract_download_urls(data: dict) -> List[str]:
        """从多种响应形态中提取下载地址，兼容 Google 改版。"""
        urls: List[str] = []

        def add(value):
            if isinstance(value, str) and value and value not in urls:
                urls.append(value)

        add(data.get("downloadUrl"))
        add(data.get("download_url"))
        for key in ("downloadUrls", "download_urls"):
            for value in data.get(key) or []:
                add(value)
        for group in ("files", "archives", "parts", "items"):
            for item in data.get(group) or []:
                if not isinstance(item, dict):
                    continue
                for key in (
                    "downloadUrl",
                    "download_url",
                    "url",
                    "href",
                    "storagePath",
                    "storage_path",
                ):
                    add(item.get(key))
        return urls

    @staticmethod
    def extract_watch_history(archive_paths: List[Path]) -> list:
        """从压缩包中定位 watch-history.json 并合并为 JSON 数组。"""
        payload: list = []
        for archive in archive_paths:
            try:
                with zipfile.ZipFile(archive) as zf:
                    candidates = [
                        name
                        for name in zf.namelist()
                        if name.lower().endswith("watch-history.json")
                    ]
                    if not candidates:
                        continue
                    candidates.sort(key=len, reverse=True)
                    for name in candidates:
                        raw = zf.read(name)
                        try:
                            data = json.loads(raw.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        if isinstance(data, list):
                            payload.extend(data)
                            break
            except (zipfile.BadZipFile, OSError):
                continue
        return payload

    def close(self) -> None:
        """释放本模块创建的 HTTP 客户端。"""
        if self._owns_client and self.client is not None:
            self.client.close()
            self.client = None

    def __enter__(self) -> "TakeoutExporter":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def make_temp_dir(prefix: str = "takeout-") -> Path:
    """创建自动导出专用的临时目录。"""
    return Path(tempfile.mkdtemp(prefix=prefix))


def remove_temp_dir(path: Path) -> None:
    """删除临时目录（失败时静默忽略）。"""
    if path is None:
        return
    shutil.rmtree(path, ignore_errors=True)
