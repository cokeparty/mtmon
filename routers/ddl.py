"""
DDL 모니터링 (담당자 = 개발자 단일 뷰)
- CSV 업로드 → 파싱 → ddl_log 적재
- 행 단위 SR 번호 입력 / 취소
- enrich (SR DB 조회 + 검증 통계)
"""

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from core.permissions import page_edit, page_view
from core.web import render, default_ym
from db.database import get_db
from services.common import excel
from schemas.ddl import DdlApplySrRequest, DdlClearSrRequest, DdlSaveReasonRequest, DdlSaveFieldsRequest
import services.ddl.service as ddl_service
import logging

logger = logging.getLogger(__name__)

router    = APIRouter(prefix="/ddl", tags=["DDL"])



# ─────────────────────────────────────────
# 화면
# ─────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def ddl_view(
    request:      Request,
    year_month:   str = Query(default=None),
    system_code:  str = Query(default="HR"),
    db:           Session = Depends(get_db),
    current_user          = Depends(page_view("ddl")),
):
    ym = year_month or default_ym()
    data = ddl_service.get_view(db, ym, system_code)
    return render(request, "ddl.html", {
        "active": "ddl",
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
    _u                   = Depends(page_edit("ddl")),
):
    """DBSAFER CSV 업로드 (전체 칼럼 CSV 도 그대로 가능). 실패하면 기존 데이터는 그대로."""
    ym      = year_month or default_ym()
    content = await file.read()
    try:
        stats = ddl_service.import_csv(content, ym, system_code, db)
        return {"ok": True, "stats": stats}
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:
        logger.exception("DDL CSV 업로드 실패 ym=%s sc=%s file=%s", ym, system_code, file.filename)
        return {"ok": False, "message": f"업로드 실패 — 기존 데이터는 그대로 두었습니다. ({type(e).__name__}: {e})"}


@router.post("/apply-sr")
async def apply_sr(
    payload: DdlApplySrRequest,
    db:      Session = Depends(get_db),
    _u                = Depends(page_edit("ddl")),
):
    try:
        log, sr_found = ddl_service.apply_sr(payload.log_id, payload.sr_no.strip(), db)
        return {"ok": True, "log": log, "sr_found": sr_found}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/clear-sr")
async def clear_sr(
    payload: DdlClearSrRequest,
    db:      Session = Depends(get_db),
    _u                = Depends(page_edit("ddl")),
):
    try:
        log = ddl_service.clear_sr(payload.log_id, db)
        return {"ok": True, "log": log}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/save-reason")
async def save_reason(
    payload: DdlSaveReasonRequest,
    db:      Session = Depends(get_db),
    _u                = Depends(page_edit("ddl")),
):
    try:
        log = ddl_service.save_reason(payload.log_id, payload.reason, db)
        return {"ok": True, "log": log}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/save-fields")
async def save_fields(
    payload: DdlSaveFieldsRequest,
    db:      Session = Depends(get_db),
    _u                = Depends(page_edit("ddl")),
):
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
    _u                   = Depends(page_view("ddl")),
):
    ym  = year_month or default_ym()
    content = ddl_service.export_excel(db, ym, system_code)   # 데이터가 없어도 빈 양식
    return excel.response(content, f"DDL_{ym}_{system_code}.xlsx")
