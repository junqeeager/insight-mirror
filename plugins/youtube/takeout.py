"""Google Takeout 自动导出（takeout-pa 内部 API）

Takeout 的“创建导出/查询状态/下载归档”走的是 Google 内部 API：

    POST /v2/{service}/exports      -> 创建导出任务（返回 exportJob.id）
    GET  /v2/{service}/exports/{id} -> 查询状态与归档下载地址

该 API 接受 OAuth Bearer token，但要求 `drive.readonly` scope
（Google 把 Takeout 归档视为云端硬盘数据）。2026-08 实测：端点存在、
token 可识别，缺 scope 时返回 403；加上该 scope 后即可后台全自动创建
YouTube 导出 → 轮询 → 下载 zip/tgz → 解析 watch-history.json。

接口非公开，字段以 Google Discovery 文档（takeout-pa）为准；若 Google
改版，只需调整本模块的请求体与解析函数。
"""

import json
import shutil
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

import httpx

TAKEOUT_PA_BASE = "https://takeout-pa.googleapis.com/v2"
DEFAULT_SERVICE = "youtube"
DEFAULT_POLL_INTERVAL_SECONDS = 15
DEFAULT_POLL_TIMEOUT_SECONDS = 30 * 60
DEFAULT_MAX_ARCHIVE_MB = 200
DEFAULT_MAX_TOTAL_MB = 1024

IN_PROGRESS_STATUSES = {
    "UNKNOWN",
    "QUEUED",
    "COUNTING",
    "BUILDING",
    "PROCESSING",
    "PENDING",
    "CREATED",
}
DONE_STATUSES = {"SUCCEEDED", "COMPLETED", "DONE", "READY"}
FAILED_STATUSES = {"FAILED", "CANCELLED", "CANCELED", "ERROR"}

ProgressCallback = Callable[[str], None]


class TakeoutError(RuntimeError):
    """Takeout 自动导出失败（通用）。"""


class TakeoutAuthError(TakeoutError):
    """Google 拒绝访问（scope 不足或 token 失效）。"""


class TakeoutApiDisabledError(TakeoutError):
    """Google 云项目未启用 Takeout API（需要到 Cloud Console 开启）。"""


class TakeoutFormatError(TakeoutError):
    """Takeout 返回格式与预期不符（接口改版或参数错误）。"""


class TakeoutExportFailed(TakeoutError):
    """Google 侧导出任务失败。"""


def _noop_progress(_message: str) -> None:
    """默认进度回调：什么都不做。"""


class TakeoutExporter:
    """通过 takeout-pa 内部 API 创建并下载 YouTube Takeout 导出。"""

    def __init__(
        self,
        access_token: str,
        service: str = DEFAULT_SERVICE,
        max_archive_mb: int = DEFAULT_MAX_ARCHIVE_MB,
        max_total_mb: int = DEFAULT_MAX_TOTAL_MB,
        poll_interval: int = DEFAULT_POLL_INTERVAL_SECONDS,
        poll_timeout: int = DEFAULT_POLL_TIMEOUT_SECONDS,
        client: Optional[httpx.Client] = None,
    ):
        self.access_token = access_token
        self.service = service
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
            "Content-Type": "application/json",
        }

    def _raise_for_auth(self, resp: httpx.Response) -> None:
        """把鉴权失败翻译成可读错误。"""
        if resp.status_code in (401, 403):
            message = ""
            try:
                message = (
                    (resp.json().get("error") or {}).get("message") or ""
                )
            except (json.JSONDecodeError, ValueError):
                pass
            if "scope" in message.lower() or "scopes" in message.lower():
                raise TakeoutAuthError(
                    "缺少 Google 云端硬盘读取权限（takeout-pa 需要 "
                    "drive.readonly）。请在设置页重新连接 YouTube 授权一次。"
                )
            if (
                "has not been used in project" in message.lower()
                or "access not configured" in message.lower()
                or "enable it by visiting" in message.lower()
                or "it is disabled" in message.lower()
            ):
                raise TakeoutApiDisabledError(
                    "Google 云项目尚未启用 Takeout API（HTTP 403）："
                    f"{message} 请按提示到 Google Cloud Console 启用该 API，"
                    "等待几分钟后重试；这不是账号授权问题，无需重新连接 "
                    "YouTube 授权。若 Console 无法加载或该 API 为 Google "
                    "内部接口，可改用 takeout.google.com 导出 "
                    "watch-history.json 后手动上传。"
                )
            raise TakeoutAuthError(
                "Google 拒绝访问 Takeout（HTTP "
                f"{resp.status_code}）：{message or '未知原因'}。"
                "请重新连接 YouTube 授权后重试。"
            )
        content_type = (resp.headers.get("content-type") or "").lower()
        if "text/html" in content_type:
            raise TakeoutAuthError(
                "Takeout 返回了网页而不是 API 响应，接口可能已改版。"
                "请稍后重试，或使用手动上传。"
            )

    @staticmethod
    def _json(resp: httpx.Response) -> dict:
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            raise TakeoutFormatError("Takeout 返回的不是 JSON")
        if not isinstance(data, dict):
            raise TakeoutFormatError("Takeout 返回格式异常（应为 JSON 对象）")
        return data

    @staticmethod
    def _unwrap_export_job(data: dict) -> dict:
        """兼容 exportJob 包装层，返回导出任务本体。"""
        job = data.get("exportJob") or data
        return job if isinstance(job, dict) else data

    @staticmethod
    def _error_message(data: dict) -> str:
        """从 Errors 或错误字段中提取简短原因。"""
        errors = data.get("errors") or {}
        if isinstance(errors, dict):
            for item in errors.get("error") or []:
                if isinstance(item, dict) and item.get("externalErrorMessage"):
                    return str(item["externalErrorMessage"])
            if errors.get("code"):
                return f"{errors.get('code')}: {errors.get('requestId', '')}"
        for key in ("failReason", "debugFailureInfo", "message"):
            if data.get(key):
                return str(data[key])
        return ""

    # ---------- 创建与轮询 ----------

    def create_export(self) -> str:
        """创建只含 YouTube 服务的导出任务，返回导出任务 ID。"""
        body = {
            "service": self.service,
            "items": [],
            "locale": "zh-CN",
            "initiatingClientService": "TAKEOUT_INTERNAL",
            "archivePrefix": "takeout",
        }
        try:
            resp = self.client.post(
                f"{TAKEOUT_PA_BASE}/{self.service}/exports",
                json=body,
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
        job = self._unwrap_export_job(data)
        export_id = (
            job.get("id")
            or job.get("exportId")
            or data.get("exportJobId")
            or data.get("id")
        )
        if not export_id:
            raise TakeoutFormatError(
                "Takeout 返回中未找到导出任务 ID，接口格式可能已变化"
            )
        return str(export_id)

    def poll_until_ready(
        self,
        export_id: str,
        progress: Optional[ProgressCallback] = None,
    ) -> dict:
        """轮询导出状态直到 SUCCEEDED/FAILED；返回完成时的完整响应。"""
        progress = progress or _noop_progress
        deadline = time.monotonic() + self.poll_timeout
        waited = 0
        while True:
            try:
                resp = self.client.get(
                    f"{TAKEOUT_PA_BASE}/{self.service}/exports/{export_id}",
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
            job = self._unwrap_export_job(data)
            status = str(job.get("status") or "").upper()
            if status in DONE_STATUSES:
                return data
            if status in FAILED_STATUSES:
                reason = self._error_message(job) or "未知原因"
                raise TakeoutExportFailed(f"Google 导出任务失败：{reason}")
            percent = data.get("percentDone") or job.get("percentDone")
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
        export_data: dict,
        target_dir: Path,
        progress: Optional[ProgressCallback] = None,
    ) -> List[Path]:
        """下载所有分卷归档到 target_dir，返回本地文件路径列表。"""
        progress = progress or _noop_progress
        job = self._unwrap_export_job(export_data)
        urls = self._extract_download_urls(job)
        if not urls:
            raise TakeoutFormatError(
                "Takeout 导出已完成但响应中没有下载地址，接口格式可能已变化"
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        paths: List[Path] = []
        total_bytes = 0
        for index, url in enumerate(urls, start=1):
            if url.startswith("/"):
                url = f"https://takeout-pa.googleapis.com{url}"
            try:
                with self.client.stream(
                    "GET", url, headers=self._headers()
                ) as resp:
                    self._raise_for_auth(resp)
                    if resp.status_code >= 400:
                        raise TakeoutError(
                            f"下载 Takeout 归档失败（HTTP {resp.status_code}）"
                        )
                    dest = target_dir / f"takeout-part-{index}.zip"
                    size = 0
                    with dest.open("wb") as handle:
                        for chunk in resp.iter_bytes(1024 * 1024):
                            size += len(chunk)
                            total_bytes += len(chunk)
                            if size > self.max_archive_bytes:
                                raise TakeoutError(
                                    "单个 Takeout 归档超过 "
                                    f"{self.max_archive_bytes // (1024 * 1024)}MB"
                                    " 上限，无法自动导入"
                                )
                            if total_bytes > self.max_total_bytes:
                                raise TakeoutError(
                                    "Takeout 归档总大小超过 1GB 上限，"
                                    "无法自动导入；可尝试手动上传"
                                )
                            handle.write(chunk)
                    paths.append(dest)
                    progress(
                        f"已下载第 {index}/{len(urls)} 个归档"
                        f"（{size / (1024 * 1024):.1f}MB）"
                    )
            except httpx.HTTPError as exc:
                raise TakeoutError(f"下载 Takeout 归档失败: {exc}")
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
        for group in ("archives", "files", "parts", "items"):
            for item in data.get(group) or []:
                if not isinstance(item, dict):
                    continue
                for key in (
                    "storagePath",
                    "storage_path",
                    "downloadUrl",
                    "download_url",
                    "url",
                    "href",
                ):
                    add(item.get(key))
        return urls

    @staticmethod
    def extract_watch_history(archive_paths: List[Path]) -> list:
        """从 zip/tgz 中定位 watch-history.json 并合并为 JSON 数组。"""
        payload: list = []
        for archive in archive_paths:
            payload.extend(TakeoutExporter._read_archive(archive))
        return payload

    @staticmethod
    def _read_archive(archive: Path) -> list:
        """读取单个归档中的 watch-history.json（zip 或 tgz）。"""
        entries: list = []
        try:
            if zipfile.is_zipfile(archive):
                with zipfile.ZipFile(archive) as zf:
                    candidates = [
                        name
                        for name in zf.namelist()
                        if name.lower().endswith("watch-history.json")
                    ]
                    candidates.sort(key=len, reverse=True)
                    for name in candidates:
                        raw = zf.read(name)
                        data = TakeoutExporter._decode_json(raw)
                        if data is not None:
                            entries.extend(data)
                            break
            else:
                with tarfile.open(archive, "r:*") as tf:
                    candidates = [
                        member
                        for member in tf.getmembers()
                        if member.isfile()
                        and member.name.lower().endswith("watch-history.json")
                    ]
                    candidates.sort(key=lambda m: len(m.name), reverse=True)
                    for member in candidates:
                        raw = tf.extractfile(member)
                        if raw is None:
                            continue
                        data = TakeoutExporter._decode_json(raw.read())
                        if data is not None:
                            entries.extend(data)
                            break
        except (zipfile.BadZipFile, tarfile.TarError, OSError):
            return []
        return entries

    @staticmethod
    def _decode_json(raw: bytes) -> Optional[list]:
        """解析 watch-history.json 内容；不是 JSON 数组时返回 None。"""
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return data if isinstance(data, list) else None

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
