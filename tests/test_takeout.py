"""Google Takeout 自动导出客户端测试（离线，httpx MockTransport）"""

import io
import json
import sys
import zipfile
from pathlib import Path

project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import httpx  # noqa: E402

from plugins.youtube.takeout import (  # noqa: E402
    TakeoutAuthError,
    TakeoutError,
    TakeoutExportFailed,
    TakeoutExporter,
    TakeoutFormatError,
    make_temp_dir,
    remove_temp_dir,
)

WATCH_PAYLOAD = [
    {
        "title": "Watched 测试视频",
        "titleUrl": "https://www.youtube.com/watch?v=abc123",
        "time": "2026-08-01T10:00:00Z",
        "subtitles": [{"name": "示例频道"}],
    },
    {
        "title": "Watched 另一个视频",
        "titleUrl": "https://www.youtube.com/watch?v=def456",
        "time": "2026-08-02T09:00:00Z",
    },
]


def _zip_bytes(entries: list) -> bytes:
    """把 JSON 数组打包成 Takeout 目录结构的 zip。"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "Takeout/YouTube and YouTube Music/history/watch-history.json",
            json.dumps(entries),
        )
    return buffer.getvalue()


def _make_client(
    *,
    create_batch_id: str = "batch-1",
    poll_count: int = 1,
    final_status: str = "COMPLETED",
    fail_reason: str = "",
    archive_bytes: bytes | None = None,
    create_status: int = 200,
    download_status: int = 200,
) -> httpx.Client:
    """构造覆盖创建/轮询/下载的 MockTransport 客户端。"""
    state = {"polls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if request.method == "POST" and url.endswith("/takeout/v1/batches"):
            if create_status != 200:
                return httpx.Response(create_status, text="denied")
            return httpx.Response(
                200,
                json={"batchId": create_batch_id, "status": "PROCESSING"},
            )
        if request.method == "GET" and "/takeout/v1/batches/" in url:
            state["polls"] += 1
            if state["polls"] <= poll_count:
                return httpx.Response(
                    200,
                    json={
                        "batchId": create_batch_id,
                        "status": "PROCESSING",
                        "percentDone": 42,
                    },
                )
            if final_status == "FAILED":
                return httpx.Response(
                    200,
                    json={
                        "batchId": create_batch_id,
                        "status": "FAILED",
                        "failReason": fail_reason or "内部错误",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "batchId": create_batch_id,
                    "status": "COMPLETED",
                    "files": [
                        {
                            "fileName": "takeout.zip",
                            "downloadUrl": "https://takeout.example.com/a.zip",
                        }
                    ],
                },
            )
        if url.startswith("https://takeout.example.com/"):
            if download_status != 200:
                return httpx.Response(download_status, text="denied")
            return httpx.Response(
                200,
                content=archive_bytes
                if archive_bytes is not None
                else _zip_bytes(WATCH_PAYLOAD),
            )
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _exporter(**overrides) -> TakeoutExporter:
    params = {
        "access_token": "at-1",
        "max_archive_mb": 200,
        "max_total_mb": 1024,
        "poll_interval": 0,
        "poll_timeout": 10,
    }
    params.update(overrides)
    return TakeoutExporter(**params)


def test_create_batch_returns_id():
    exporter = _exporter(client=_make_client())
    assert exporter.create_batch() == "batch-1"
    exporter.close()


def test_create_batch_missing_id_raises_format_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "PROCESSING"})

    exporter = _exporter(
        client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    try:
        exporter.create_batch()
        assert False, "应抛出 TakeoutFormatError"
    except TakeoutFormatError:
        pass
    finally:
        exporter.close()


def test_create_batch_unauthorized_raises_auth_error():
    exporter = _exporter(client=_make_client(create_status=403))
    try:
        exporter.create_batch()
        assert False, "应抛出 TakeoutAuthError"
    except TakeoutAuthError as exc:
        assert "重新连接" in str(exc)
    finally:
        exporter.close()


def test_poll_waits_until_completed_and_reports_progress():
    exporter = _exporter(client=_make_client(poll_count=2))
    messages = []

    def progress(message: str):
        messages.append(message)

    data = exporter.poll_until_ready("batch-1", progress)
    assert data["status"] == "COMPLETED"
    assert any("42%" in message for message in messages)
    assert any("等待" in message for message in messages)
    exporter.close()


def test_poll_failed_status_raises_export_failed():
    exporter = _exporter(
        client=_make_client(final_status="FAILED", fail_reason="磁盘不足")
    )
    try:
        exporter.poll_until_ready("batch-1")
        assert False, "应抛出 TakeoutExportFailed"
    except TakeoutExportFailed as exc:
        assert "磁盘不足" in str(exc)
    finally:
        exporter.close()


def test_poll_timeout_raises():
    exporter = _exporter(
        client=_make_client(poll_count=10**9),
        poll_timeout=1,
        poll_interval=0,
    )
    try:
        exporter.poll_until_ready("batch-1")
        assert False, "应抛出 TakeoutError"
    except TakeoutError as exc:
        assert "超时" in str(exc)
    finally:
        exporter.close()


def test_download_and_extract_watch_history():
    exporter = _exporter(client=_make_client())
    temp_dir = make_temp_dir()
    try:
        data = exporter.poll_until_ready("batch-1")
        archives = exporter.download_archives(data, temp_dir)
        assert len(archives) == 1
        payload = exporter.extract_watch_history(archives)
        assert payload == WATCH_PAYLOAD
    finally:
        remove_temp_dir(temp_dir)
        exporter.close()
    assert not temp_dir.exists()


def test_download_too_large_raises():
    exporter = _exporter(
        client=_make_client(archive_bytes=b"x" * (2 * 1024 * 1024)),
        max_archive_mb=1,
    )
    temp_dir = make_temp_dir()
    try:
        data = exporter.poll_until_ready("batch-1")
        exporter.download_archives(data, temp_dir)
        assert False, "应抛出 TakeoutError"
    except TakeoutError as exc:
        assert "上限" in str(exc)
    finally:
        remove_temp_dir(temp_dir)
        exporter.close()


def test_download_unauthorized_raises_auth_error():
    exporter = _exporter(client=_make_client(download_status=403))
    temp_dir = make_temp_dir()
    try:
        data = exporter.poll_until_ready("batch-1")
        exporter.download_archives(data, temp_dir)
        assert False, "应抛出 TakeoutAuthError"
    except TakeoutAuthError:
        pass
    finally:
        remove_temp_dir(temp_dir)
        exporter.close()


def test_extract_skips_bad_zip_and_merges_payloads():
    first = _zip_bytes(WATCH_PAYLOAD[:1])
    second = _zip_bytes(WATCH_PAYLOAD[1:])
    bad = Path(make_temp_dir()) / "bad.zip"
    bad.write_bytes(b"not-a-zip")
    good1 = Path(make_temp_dir()) / "good1.zip"
    good2 = Path(make_temp_dir()) / "good2.zip"
    good1.write_bytes(first)
    good2.write_bytes(second)
    try:
        payload = TakeoutExporter.extract_watch_history([bad, good1, good2])
        assert payload == WATCH_PAYLOAD
    finally:
        bad.unlink(missing_ok=True)
        good1.unlink(missing_ok=True)
        good2.unlink(missing_ok=True)
        for parent in {bad.parent, good1.parent, good2.parent}:
            remove_temp_dir(parent)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✅ {name}")
    print("\n🎉 Takeout 测试通过！")
