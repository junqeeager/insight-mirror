"""YouTube OAuth 授权与 Takeout 观看历史导入 API"""

import json
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import get_config, get_current_user, get_db
from api.schemas import (
    YouTubeAuthUrlOut,
    YouTubeTakeoutOut,
    YouTubeTokenIn,
    YouTubeTokenOut,
)
from core.auth import decrypt_config, encrypt_config
from core.database import Database
from core.plugin_loader import PluginManager

router = APIRouter(prefix="/api/v1/sources/youtube", tags=["youtube"])

OAUTH_TTL_MINUTES = 10


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
    except Exception:
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
