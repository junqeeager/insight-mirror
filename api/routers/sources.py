"""用户自己的数据源配置与测试"""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_config, get_current_user, get_db
from api.schemas import SourceConfigIn, SourceConfigOut
from core.auth import decrypt_config, encrypt_config, mask_config
from core.database import Database
from core.plugin_loader import PluginManager

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


def _saved_or_empty(db: Database, user_id: str, source: str) -> dict:
    row = db.get_source_config(user_id, source)
    return {"config": {}, "enabled": False} if not row else row


@router.get("", response_model=list[SourceConfigOut])
def list_sources(
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """列出系统支持的数据源及当前用户已保存的配置（敏感字段脱敏）。"""
    out = []
    for source, source_cfg in config.get("sources", {}).items():
        saved = _saved_or_empty(db, user["id"], source)
        decrypted = decrypt_config(saved.get("config") or {})
        has_secrets = {
            key: bool(value)
            for key, value in decrypted.items()
            if any(kw in key.lower() for kw in ("cookie", "csrf", "token", "secret"))
        }
        enabled = bool(saved.get("enabled", source_cfg.get("enabled", False)))
        out.append(
            SourceConfigOut(
                source=source,
                enabled=enabled,
                config=mask_config(decrypted),
                has_secrets=has_secrets,
            )
        )
    return out


@router.put("/{source}", response_model=SourceConfigOut)
def save_source(
    source: str,
    body: SourceConfigIn,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """保存数据源配置；敏感字段留空或 *** 时保持不变。"""
    if source not in config.get("sources", {}):
        raise HTTPException(status_code=404, detail="未知数据源")
    existing = decrypt_config(
        (_saved_or_empty(db, user["id"], source)).get("config") or {}
    )
    merged = dict(existing)
    for key, value in body.config.items():
        if any(kw in key.lower() for kw in ("cookie", "csrf", "token", "secret")):
            if value in ("", "***") and key in merged:
                continue
            merged[key] = value
        else:
            merged[key] = value
    db.set_source_config(user["id"], source, encrypt_config(merged), body.enabled)
    saved = db.get_source_config(user["id"], source)
    decrypted = decrypt_config(saved.get("config") or {})
    return SourceConfigOut(
        source=source,
        enabled=bool(saved["enabled"]),
        config=mask_config(decrypted),
        has_secrets={
            key: bool(value)
            for key, value in decrypted.items()
            if any(kw in key.lower() for kw in ("cookie", "csrf", "token", "secret"))
        },
    )


@router.post("/{source}/test")
def test_source(
    source: str,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
    config: dict = Depends(get_config),
):
    """测试当前用户该数据源配置是否可用。"""
    if source not in config.get("sources", {}):
        raise HTTPException(status_code=404, detail="未知数据源")
    saved = _saved_or_empty(db, user["id"], source)
    decrypted = decrypt_config(saved.get("config") or {})
    sources = {source: {"enabled": True, "config": decrypted}}
    user_config = dict(config)
    user_config["sources"] = sources
    manager = PluginManager(config["system"]["plugins_dir"], user_config)
    manager.discover()
    try:
        plugin = manager.load(source)
        ok = plugin.test_connection()
        return {"ok": ok, "message": "连接成功" if ok else "连接失败，请检查配置"}
    except KeyError:
        raise HTTPException(status_code=404, detail="插件未找到")
