"""账号管理：改密、数据导出、注销。"""

import csv
import io
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.deps import get_current_user, get_db
from api.schemas import ChangePasswordIn, DeleteAccountIn, EventOut
from core.auth import hash_password, verify_password
from core.database import Database

router = APIRouter(prefix="/api/v1/account", tags=["account"])


def _events_to_csv(events) -> str:
    """把事件列表转为带 BOM 的 CSV（便于 Excel 打开中文）。"""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "timestamp",
            "source",
            "event_type",
            "title",
            "url",
            "description",
            "tags",
            "duration",
            "progress",
            "depth",
            "metadata",
        ]
    )
    for event in events:
        writer.writerow(
            [
                event.id,
                event.timestamp.isoformat(),
                event.source,
                event.event_type.value,
                event.title,
                event.url or "",
                event.description or "",
                "; ".join(event.tags),
                event.duration if event.duration is not None else "",
                event.progress if event.progress is not None else "",
                event.depth.value,
                json.dumps(event.metadata, ensure_ascii=False),
            ]
        )
    return "\ufeff" + buffer.getvalue()


@router.post("/password")
def change_password(
    body: ChangePasswordIn,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """修改当前用户密码，并使该用户所有会话失效。"""
    current = db.get_user_by_id(user["id"])
    if not verify_password(body.old_password, current["password_hash"]):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    db.update_user_password(user["id"], hash_password(body.new_password))
    db.delete_user_sessions(user["id"])
    return {"ok": True}


@router.post("/export")
def export_data(
    format: str = Query("csv", pattern="^(csv|json)$"),
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """服务端导出当前用户全部事件。"""
    events = db.get_all_events(user["id"])
    if format == "csv":
        content = _events_to_csv(events)
        media_type = "text/csv; charset=utf-8"
        filename = f"events_{user['username']}.csv"
    else:
        content = json.dumps(
            [EventOut.from_event(e).model_dump(mode="json") for e in events],
            ensure_ascii=False,
            indent=2,
        )
        media_type = "application/json; charset=utf-8"
        filename = f"events_{user['username']}.json"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("")
def delete_account(
    body: DeleteAccountIn,
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """注销账号：物理删除该用户全部数据，不可恢复。"""
    current = db.get_user_by_id(user["id"])
    if not verify_password(body.password, current["password_hash"]):
        raise HTTPException(status_code=400, detail="密码不正确")
    db.delete_user_data(user["id"])
    return {"ok": True}
