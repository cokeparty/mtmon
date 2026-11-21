"""
DDL 모니터링 (담당자 = 개발자 단일 뷰)
- CSV 업로드 → 파싱 → ddl_log 적재
- 행 단위 SR 번호 입력 / 취소
- enrich (SR DB 조회 + 검증 통계)
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.deps import get_current_user
from core.permissions import can_upload_csv, can_edit_ddl, PERM_DENIED_MSG
from db.database import get_db
from models.auth import AppUser
from schemas.ddl import DdlApplySrRequest, DdlClearSrRequest, DdlSaveReasonRequest, DdlSaveFieldsRequest
import services.ddl_service as ddl_service

BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
router    = APIRouter(prefix="/ddl", tags=["DDL"])


def _default_ym() -> str:
    """월간 모니터링 기본 회차 = 전월(당월 아님)."""
    from core.periods import prev_month_ym
    return prev_month_ym()


# ─────────────────────────────────────────
# 화면
# ─────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def ddl_view(
    request:      Request,
    year_month:   str = Query(default=None),
    system_code:  str = Query(default="HR"),
    db:           Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ym = year_month or _default_ym()
    try:
        data = ddl_service.get_view(db, ym, system_code)
        data["db_error"] = False
    except OperationalError:
        data = {
            "period": ym, "system_code": system_code,
            "last_uploaded_at": "",
            "summary": {"total": 0, "applied": 0, "pending": 0,
                        "no_reason": 0, "progress_pct": 0},
            "logs": [], "db_error": True,
        }
    return templates.TemplateResponse("ddl.html", {
        "request": request,
        "active":  "ddl",
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
    request:     Request,
    file:        UploadFile = File(...),
    year_month:  str = Query(default=None),
    system_code: str = Query(default="HR"),
    db:          Session = Depends(get_db),
):
    if not can_upload_csv(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    ym      = year_month or _default_ym()
    content = await file.read()
    try:
        stats = ddl_service.import_csv(content, ym, system_code, db)
        return {"ok": True, "stats": stats}
    except ValueError as e:
        return {"ok": False, "message": str(e)}


@router.post("/apply-sr")
async def apply_sr(
    payload: DdlApplySrRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_edit_ddl(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        log, sr_found = ddl_service.apply_sr(payload.log_id, payload.sr_no.strip(), db)
        return {"ok": True, "log": log, "sr_found": sr_found}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/clear-sr")
async def clear_sr(
    payload: DdlClearSrRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_edit_ddl(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        log = ddl_service.clear_sr(payload.log_id, db)
        return {"ok": True, "log": log}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/save-reason")
async def save_reason(
    payload: DdlSaveReasonRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_edit_ddl(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        log = ddl_service.save_reason(payload.log_id, payload.reason, db)
        return {"ok": True, "log": log}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/save-fields")
async def save_fields(
    payload: DdlSaveFieldsRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_edit_ddl(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        log = ddl_service.save_fields(payload.log_id, payload.fields, db)
        return {"ok": True, "log": log}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.get("/excel")
async def download_excel(
    year_month:  str = Query(default=None),
    system_code: str = Query(default="HR"),
    db:          Session = Depends(get_db),
):
    ym  = year_month or _default_ym()
    buf = ddl_service.export_excel(db, ym, system_code)
    if buf is None:
        return JSONResponse({"ok": False, "message": "내보낼 데이터가 없습니다."}, status_code=404)
    filename = f"DDL_{ym}_{system_code}.xlsx"
    encoded  = quote(filename, safe="")
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
    )
