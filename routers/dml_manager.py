"""
DML 담당자 뷰
- CSV 업로드 → 파싱 → DB 적재
- 개발자별 진행률 모니터링
- 전체 그룹 조회 및 검증 실행
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.deps import get_current_user
from core.permissions import can_upload_csv, PERM_DENIED_MSG
from db.database import get_db
from models.auth import AppUser
from fastapi.responses import JSONResponse
import services.dml_service as dml_service

BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
router    = APIRouter(prefix="/dml/manager", tags=["DML-Manager"])


def _default_ym() -> str:
    """월간 모니터링 기본 회차 = 전월(당월 아님)."""
    from core.periods import prev_month_ym
    return prev_month_ym()


# ─────────────────────────────────────────
# 화면
# ─────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def dml_manager_view(
    request:      Request,
    year_month:   str = Query(default=None),
    system_code:  str = Query(default="HR"),
    db:           Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ym = year_month or _default_ym()
    try:
        data = dml_service.get_manager_view(db, ym, system_code)
        data["db_error"] = False
    except OperationalError:
        data = {
            "period": ym, "system_code": system_code,
            "last_uploaded_at": "",
            "summary": {"total_groups": 0, "applied_groups": 0,
                        "pending_groups": 0, "progress_pct": 0},
            "developers": [], "groups": [], "db_error": True,
        }
    return templates.TemplateResponse("dml_manager.html", {
        "request": request,
        "active":  "dml_manager",
        "current_user": {
            "id":   current_user.id,
            "name": current_user.name,
            "role": current_user.role,
        },
        **data,
    })


# ─────────────────────────────────────────
# API
# ─────────────────────────────────────────
@router.post("/upload")
async def upload_csv(
    request:    Request,
    file:       UploadFile = File(...),
    year_month: str = Query(default=None),
    db:         Session = Depends(get_db),
):
    """DBSAFER CSV 업로드 → dml_log + dml_group 적재 (운영자 전용).
    업무명(system_code)은 접속계정에서 자동 결정됨."""
    if not can_upload_csv(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    ym      = year_month or _default_ym()
    content = await file.read()
    try:
        stats = dml_service.import_csv(content, ym, db)
        return {"ok": True, "stats": stats}
    except ValueError as e:
        return {"ok": False, "message": str(e)}


@router.post("/group")
async def run_grouping():
    """그루핑은 CSV 업로드 시 자동 실행됨 (재실행 필요 시 재업로드)."""
    return {"ok": True, "message": "그루핑은 CSV 업로드 시 자동 실행됩니다."}


@router.post("/enrich")
async def run_enrich(
    year_month:  str = Query(default=None),
    system_code: str = Query(default="HR"),
    db:          Session = Depends(get_db),
):
    """SR DB 조회 + 검증 통계 반환."""
    ym     = year_month or _default_ym()
    result = dml_service.run_enrich(db, ym, system_code)
    return result


@router.get("/excel")
async def download_excel(
    year_month:  str = Query(default=None),
    system_code: str = Query(default="HR"),
    db:          Session = Depends(get_db),
):
    """DML 로그 + SR 정보 + 검증결과 엑셀 다운로드."""
    ym  = year_month or _default_ym()
    buf = dml_service.export_excel(db, ym, system_code)
    if buf is None:
        return {"ok": False, "message": "내보낼 데이터가 없습니다."}

    filename = f"DML_{ym}_{system_code}.xlsx"
    encoded  = quote(filename, safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
