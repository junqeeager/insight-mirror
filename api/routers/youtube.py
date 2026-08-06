"""YouTube OAuth 授权、Takeout 观看历史导入与自动导出 API"""

import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse

from analysis.profile import ProfileGenerator
from api.deps import get_config, get_current_user, get_db
from api.schemas import (
    YouTubeAuthUrlOut,
    YouTubeTakeoutFileOut,
    YouTubeTakeoutOut,
    YouTubeTakeoutExportOut,
    YouTubeTakeoutExportStatusOut,
    YouTubeTokenIn,
    YouTubeTokenOut,
)
from api.tasks import (
    TaskConflictError,
    get_task_for_user,
    open_task_db,
    start_task,
    takeout_export_progress,
)
from core.auth import decrypt_config, encrypt_config
from core.database import Database
from core.plugin_loader import PluginManager
from plugins.youtube.takeout import (
    TakeoutError,
    TakeoutExporter,
    make_temp_dir,
    remove_temp_dir,
)

router = APIRouter(prefix="/api/v1/sources/youtube", tags=["youtube"])

OAUTH_TTL_MINUTES = 10
TAKEOUT_COOLDOWN_MINUTES = 5
logger = logging.getLogger("api.youtube")


def _safe_component(value: str) -> str:
    """把用户 ID / 导出批次号清洗为安全的目录名。"""
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", str(value or ""))[:100]
    cleaned = cleaned.strip("_-")
    return cleaned or "_"


def _takeout_store_root(config: dict) -> Path:
    """自动获取的 Takeout 观看历史持久化根目录（按用户隔离）。"""
    data_dir = str(
        config.get("system", {}).get("data_dir", "./data") or "./data"
    )
    return Path(data_dir) / "youtube" / "takeout"


def _user_takeout_dir(config: dict, user_id: str) -> Path:
    return _takeout_store_root(config) / _safe_component(user_id)


def _batch_takeout_dir(config: dict, user_id: str, batch_id: str) -> Path:
    return _user_takeout_dir(config, user_id) / _safe_component(batch_id)


def _write_takeout_meta(target_dir: Path, meta: dict) -> None:
    """原子写入批次元数据。"""
    tmp = target_dir / "meta.json.tmp"
    tmp.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(target_dir / "meta.json")


def _read_takeout_meta(target_dir: Path) -> dict:
    try:
        meta = json.loads((target_dir / "meta.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def _save_takeout_payload(
    config: dict, user_id: str, batch_id: str, payload: list
) -> dict:
    """把自动下载的 watch-history.json 持久化到用户目录。"""
    target_dir = _batch_takeout_dir(config, user_id, batch_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / "watch-history.json"
    tmp = target_dir / "watch-history.json.tmp"
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp.replace(dest)
    meta = {
        "batch_id": batch_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "record_count": len(payload),
        "file_size": dest.stat().st_size,
        "imported": None,
    }
    _write_takeout_meta(target_dir, meta)
    return meta


def _update_takeout_imported(
    config: dict, user_id: str, batch_id: str, imported: int
) -> None:
    target_dir = _batch_takeout_dir(config, user_id, batch_id)
    meta = _read_takeout_meta(target_dir)
    if not meta:
        return
    meta["imported"] = int(imported)
    _write_takeout_meta(target_dir, meta)


def _list_takeout_files(config: dict, user_id: str) -> list[dict]:
    """列出当前用户自动获取的观看历史文件，按时间倒序。"""
    root = _user_takeout_dir(config, user_id)
    if not root.is_dir():
        return []
    items = []
    for batch_dir in sorted(
        root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        if not batch_dir.is_dir():
            continue
        meta = _read_takeout_meta(batch_dir)
        if not meta:
            continue
        dest = batch_dir / "watch-history.json"
        meta.setdefault("record_count", 0)
        meta.setdefault("file_size", dest.stat().st_size if dest.exists() else 0)
        meta.setdefault("file_name", "watch-history.json")
        meta["path"] = str(dest.resolve()) if dest.exists() else ""
        items.append(meta)
    return items


def _read_takeout_payload(
    config: dict, user_id: str, batch_id: str
) -> list:
    """读取已保存的 watch-history.json；不存在或损坏时返回空列表。"""
    dest = _batch_takeout_dir(config, user_id, batch_id) / "watch-history.json"
    if not dest.is_file():
        return []
    try:
        payload = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def _refresh_profiles(
    db: Database, config: dict, user_id: str
) -> dict:
    """导入观看历史后重算周/月/年画像（失败只记日志，不阻断导入）。"""
    generator = ProfileGenerator(db, config.get("analysis", {}))
    profile_ids = {}
    for period in ("weekly", "monthly", "yearly"):
        try:
            profile = generator.generate(
                user_id=user_id, period=period, persist=True
            )
            profile_ids[period] = profile.id
        except Exception:
            logger.exception(
                "Takeout 导入后生成 %s 画像失败（user=%s）", period, user_id
            )
    return profile_ids


def _takeout_cooldown_seconds(last: dict) -> int:
    """返回自动导出的剩余冷却秒数；失败或仍在运行的任务不参与冷却。"""
    if not last or last.get("status") != "done":
        return 0
    created_at = last.get("created_at")
    if not created_at:
        return 0
    elapsed = (datetime.now() - created_at).total_seconds()
    return max(0, int(TAKEOUT_COOLDOWN_MINUTES * 60 - elapsed))


def _plugin_for(db: Database, user_id: str, config: dict):
    """构建 YouTube 插件：全局凭据 + 用户保存的 refresh_token。"""
    saved = db.get_source_config(user_id, "youtube") or {}
    decrypted = decrypt_config(saved.get("config") or {})
    global_cfg = config.get("sources", {}).get("youtube", {}).get("config", {}) or {}
    merged = dict(global_cfg)
    merged.update(decrypted)
    merged["public_url"] = str(config.get("app", {}).get("public_url", "") or "")

    user_config = dict(config)
    user_config["sources"] = {
        "youtube": {"enabled": True, "config": merged}
    }
    manager = PluginManager(config["system"]["plugins_dir"], user_config)
    manager.discover()
    try:
        return manager.load("youtube")
    except KeyError:
        raise HTTPException(status_code=500, detail="YouTube 插件未加载")


@router.get("/auth-url", response_model=YouTubeAuthUrlOut)
def youtube_auth_url(
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """生成带 PKCE 的 Google 授权地址，并保存一次性授权流。"""
    db.cleanup_expired_oauth_flows()
    plugin = _plugin_for(db, user["id"], config)
    if not plugin.client_id or not plugin.client_secret:
        raise HTTPException(
            status_code=400,
            detail="服务端未配置 YouTube OAuth 凭据（YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET）",
        )
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)
    expires_at = datetime.now().replace(microsecond=0) + timedelta(
        minutes=OAUTH_TTL_MINUTES
    )
    db.save_oauth_flow(user["id"], state, code_verifier, expires_at)
    return {"url": plugin.build_auth_url(state, code_verifier)}


@router.post("/token", response_model=YouTubeTokenOut)
def youtube_token(
    body: YouTubeTokenIn,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """用授权码换取 refresh_token 并加密保存、启用该数据源。"""
    flow = db.consume_oauth_flow(user["id"], body.state)
    if flow is None:
        raise HTTPException(status_code=400, detail="授权状态无效或已过期，请重新连接")
    plugin = _plugin_for(db, user["id"], config)
    try:
        tokens = plugin.exchange_code(body.code, flow["code_verifier"])
    except Exception as exc:
        logger.exception("YouTube token 交换失败: %s", exc)
        raise HTTPException(status_code=400, detail="Google 授权失败，请重新连接")
    refresh_token = str(tokens.get("refresh_token") or "")
    if not refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google 未返回 refresh_token，请在 Google 账号中撤销本应用授权后重试",
        )
    db.set_source_config(
        user["id"],
        "youtube",
        encrypt_config({"refresh_token": refresh_token}),
        enabled=True,
    )
    return {"ok": True, "message": "YouTube 已连接，等待同步"}


@router.get("/callback")
def youtube_callback(
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """Google 授权回跳入口：服务端换 token 后 302 回设置页，不依赖前端回调。"""
    public_url = str(config.get("app", {}).get("public_url", "") or "").rstrip("/")

    def redirect(message: str, ok: bool = False) -> RedirectResponse:
        query = urlencode({"youtube": "ok" if ok else "error", "message": message})
        return RedirectResponse(f"{public_url}/settings?{query}")

    if error:
        return redirect(error_description or error)
    if not code or not state:
        return redirect("授权参数缺失，请重新连接")

    flow = db.consume_oauth_flow_by_state(state)
    if flow is None:
        return redirect("授权状态无效或已过期，请重新连接")

    plugin = _plugin_for(db, flow["user_id"], config)
    try:
        tokens = plugin.exchange_code(code, flow["code_verifier"])
    except Exception as exc:
        logger.exception("YouTube 回调换 token 失败: %s", exc)
        return redirect("Google 授权失败，请重新连接")

    refresh_token = str(tokens.get("refresh_token") or "")
    if not refresh_token:
        return redirect("Google 未返回 refresh_token，请撤销本应用授权后重试")

    db.set_source_config(
        flow["user_id"],
        "youtube",
        encrypt_config({"refresh_token": refresh_token}),
        enabled=True,
    )
    return redirect("YouTube 已连接，等待同步", ok=True)


@router.post("/takeout", response_model=YouTubeTakeoutOut)
async def youtube_takeout(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """上传 Google Takeout watch-history.json，解析后幂等导入。"""
    plugin = _plugin_for(db, user["id"], config)
    max_bytes = plugin.takeout_max_mb * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大，最大 {plugin.takeout_max_mb}MB",
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(
            status_code=400,
            detail="无法解析 Takeout JSON（应为 watch-history.json）",
        )
    events = plugin.parse_takeout(payload)
    imported = db.insert_events(events, user["id"])
    return {
        "received": len(payload) if isinstance(payload, list) else 0,
        "parsed": len(events),
        "imported": imported,
    }


@router.get(
    "/takeout/history",
    response_model=list[YouTubeTakeoutFileOut],
)
def youtube_takeout_history(
    user: dict = Depends(get_current_user),
    config: dict = Depends(get_config),
):
    """列出自动获取并保存到服务端的观看历史文件。"""
    return _list_takeout_files(config, user["id"])


@router.post(
    "/takeout/history/{batch_id}/import",
    response_model=YouTubeTakeoutOut,
)
def youtube_takeout_history_import(
    batch_id: str,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """从服务端保存的自动获取历史重新导入（幂等）。"""
    payload = _read_takeout_payload(config, user["id"], batch_id)
    if not payload:
        raise HTTPException(
            status_code=404,
            detail="自动获取的观看历史不存在或已损坏",
        )
    plugin = _plugin_for(db, user["id"], config)
    events = plugin.parse_takeout(payload)
    imported = db.insert_events(events, user["id"])
    if imported > 0:
        _refresh_profiles(db, config, user["id"])
    _update_takeout_imported(config, user["id"], batch_id, imported)
    return {
        "received": len(payload),
        "parsed": len(events),
        "imported": imported,
    }


@router.get("/takeout/history/{batch_id}/download")
def youtube_takeout_history_download(
    batch_id: str,
    user: dict = Depends(get_current_user),
    config: dict = Depends(get_config),
):
    """下载自动获取的 watch-history.json 副本。"""
    dest = (
        _batch_takeout_dir(config, user["id"], batch_id) / "watch-history.json"
    )
    if not dest.is_file():
        raise HTTPException(
            status_code=404,
            detail="自动获取的观看历史不存在或已损坏",
        )
    filename = f"watch-history-{_safe_component(batch_id)}.json"
    return FileResponse(
        dest,
        media_type="application/json",
        filename=filename,
    )


def _takeout_run(user_id: str, config: dict):
    """构造自动导出的后台任务执行体（在任务线程中运行）。"""

    def run(progress) -> dict:
        task_db = open_task_db()
        plugin = None
        exporter = None
        temp_dir = None
        try:
            plugin = _plugin_for(task_db, user_id, config)
            if not plugin.refresh_token:
                raise RuntimeError("未连接 YouTube，请先连接后再自动导出")
            progress("正在刷新 Google 授权…")
            token = plugin._refresh_access_token()
            exporter = TakeoutExporter(
                access_token=token,
                max_archive_mb=plugin.takeout_max_archive_mb,
                max_total_mb=plugin.takeout_max_total_mb,
            )
            progress("正在向 Google Takeout 提交导出请求…")
            export_id = exporter.create_export()
            progress(
                f"导出任务已创建（{export_id}），等待 Google 打包，"
                "通常需要几分钟…"
            )
            export_data = exporter.poll_until_ready(export_id, progress)
            temp_dir = make_temp_dir("takeout-export-")
            archives = exporter.download_archives(export_data, temp_dir, progress)
            progress("正在解压并解析观看历史…")
            payload = exporter.extract_watch_history(archives)
            _save_takeout_payload(config, user_id, export_id, payload)
            if not payload:
                raise TakeoutError(
                    "自动导出的归档中未找到 watch-history.json 或内容为空；"
                    "文件已保留，可稍后重试或手动上传"
                )
            events = plugin.parse_takeout(payload)
            if payload and not events:
                raise TakeoutError(
                    "自动导出的观看历史无法解析（0 条可识别记录），"
                    "文件已保留，可稍后重试或手动上传"
                )
            imported = task_db.insert_events(events, user_id)
            profile_ids = {}
            if imported > 0:
                progress("正在基于观看历史重新生成画像…")
                profile_ids = _refresh_profiles(task_db, config, user_id)
            _update_takeout_imported(config, user_id, export_id, imported)
            message = (
                f"已导入 {imported} 条观看记录"
                f"（识别 {len(events)} 条，共 {len(payload)} 条记录）"
            )
            if profile_ids:
                message += "，周/月/年画像已重新生成"
            return {
                "message": message,
                "received": len(payload),
                "parsed": len(events),
                "imported": imported,
                "batch_id": export_id,
                "profile_ids": profile_ids,
            }
        finally:
            if exporter is not None:
                exporter.close()
            if plugin is not None:
                plugin.cleanup()
            if temp_dir is not None:
                remove_temp_dir(temp_dir)
            task_db.close()

    return run


@router.post(
    "/takeout/export",
    response_model=YouTubeTakeoutExportOut,
    status_code=202,
)
def youtube_takeout_export_start(
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """后台自动创建 Takeout 导出并导入观看历史（用户侧一键触发）。"""
    plugin = _plugin_for(db, user["id"], config)
    if not plugin.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="未连接 YouTube，请先连接后再自动导出",
        )
    last = db.get_last_task(user["id"], "takeout_export")
    remaining = _takeout_cooldown_seconds(last)
    if remaining > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{TAKEOUT_COOLDOWN_MINUTES} 分钟内已执行过自动导出，"
                f"请约 {remaining} 秒后再试"
            ),
        )
    try:
        task_id = start_task(
            user["id"],
            "takeout_export",
            {},
            _takeout_run(user["id"], config),
            progress_factory=takeout_export_progress,
        )
    except TaskConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"task_id": task_id, "status": "started"}


@router.get(
    "/takeout/export/{task_id}",
    response_model=YouTubeTakeoutExportStatusOut,
)
def youtube_takeout_export_status(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """查询自动导出任务状态与实时消息。"""
    task = get_task_for_user(task_id, user["id"])
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    result = task.get("result") or {}
    return {
        "task_id": task_id,
        "status": task["status"],
        "error": task.get("error"),
        "message": str(result.get("message") or ""),
        "batch_id": result.get("batch_id"),
        "imported": int(result.get("imported") or 0),
        "parsed": int(result.get("parsed") or 0),
    }
