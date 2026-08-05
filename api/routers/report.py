"""报告下载：基于最近画像快照生成 HTML / TXT / JSON。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.deps import get_current_user, get_db
from api.schemas import ProfileOut
from core.database import Database
from report.generator import ReportGenerator

router = APIRouter(prefix="/api/v1/report", tags=["report"])

_PERIOD_RE = "^(weekly|monthly|yearly)$"
_FORMAT_RE = "^(html|txt|json)$"


@router.get("")
def get_report(
    period: str = Query("weekly", pattern=_PERIOD_RE),
    format: str = Query("html", pattern=_FORMAT_RE),
    user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """返回最近画像快照的报告文件（无快照时返回 404）。"""
    profiles = db.get_profiles(user_id=user["id"], period=period, limit=1)
    if not profiles:
        raise HTTPException(
            status_code=404,
            detail=f"暂无 {period} 画像快照，请先调用 POST /api/v1/profile/refresh",
        )
    profile = profiles[0]
    generator = ReportGenerator()

    if format == "html":
        content = generator.render_html(profile)
        media_type = "text/html; charset=utf-8"
        filename = f"{profile.id}_{profile.period}.html"
    elif format == "txt":
        content = generator.generate_summary(profile)
        media_type = "text/plain; charset=utf-8"
        filename = f"{profile.id}_{profile.period}.txt"
    else:
        content = ProfileOut.from_profile(profile).model_dump_json(indent=2)
        media_type = "application/json; charset=utf-8"
        filename = f"{profile.id}_{profile.period}.json"

    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
