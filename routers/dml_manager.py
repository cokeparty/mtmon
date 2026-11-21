"""
DML 운영자 화면 (데이터변경 - 운영자 화면)
- CSV 업로드 → 파싱 → DB 적재      (수정 권한)
- 전체 그룹 조회 · 엑셀             (조회 권한)
- SR 입력 · DML여부 · 사유 등은 /dml/manager/... (routers/dml_group_api.py) — 운영자 화면 권한으로만 검사
"""
import logging

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from core.permissions import page_edit, page_view
from core.web import render, default_ym
from db.database import get_db
from services.common import excel
import services.dml.service as dml_service
from routers.dml_group_api import add_group_api

router    = APIRouter(prefix="/dml/manager", tags=["DML-Manager"])
logger    = logging.getLogger(__name__)



# ─────────────────────────────────────────
# 화면
# ─────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def dml_manager_view(
    request:      Request,
    year_month:   str = Query(default=None),
    system_code:  str = Query(default="HR"),
    db:           Session = Depends(get_db),
    current_user          = Depends(page_view("dml_manager")),
):
    ym = year_month or default_ym()
    data = dml_service.get_manager_view(db, ym, system_code)
    return render(request, "dml_manager.html", {
        "active": "dml_manager",
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
    _u                  = Depends(page_edit("dml_manager")),
):
    """DBSAFER CSV 업로드 → dml_log + dml_group 적재.
    업무명(system_code)은 접속계정에서 자동 결정됨. 전체 칼럼 CSV 도 그대로 올릴 수 있다."""
    ym      = year_month or default_ym()
    content = await file.read()
    try:
        stats = dml_service.import_csv(content, ym, db)
        return {"ok": True, "stats": stats}
    except ValueError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:                       # 적재 중 오류 → 전부 되돌렸으므로 기존 데이터 그대로
        logger.exception("DML CSV 업로드 실패 ym=%s file=%s", ym, file.filename)
        return {"ok": False, "message": f"업로드 실패 — 기존 데이터는 그대로 두었습니다. ({type(e).__name__}: {e})"}


@router.post("/group")
async def run_grouping(_u=Depends(page_view("dml_manager"))):
    """그루핑은 CSV 업로드 시 자동 실행됨 (재실행 필요 시 재업로드)."""
    return {"ok": True, "message": "그루핑은 CSV 업로드 시 자동 실행됩니다."}


@router.post("/enrich")
async def run_enrich(
    year_month:  str = Query(default=None),
    system_code: str = Query(default="HR"),
    db:          Session = Depends(get_db),
    _u                   = Depends(page_view("dml_manager")),
):
    """SR DB 조회 + 검증 통계 반환."""
    ym     = year_month or default_ym()
    result = dml_service.run_enrich(db, ym, system_code)
    return result


@router.get("/excel")
async def download_excel(
    year_month:  str = Query(default=None),
    system_code: str = Query(default="HR"),
    db:          Session = Depends(get_db),
    _u                   = Depends(page_view("dml_manager")),
):
    """DML 로그 + SR 정보 + 검증결과 엑셀 다운로드 (데이터가 없어도 빈 양식)."""
    ym  = year_month or default_ym()
    content = dml_service.export_excel(db, ym, system_code)
    return excel.response(content, f"DML_{ym}_{system_code}.xlsx")


# 그룹 조회·수정 API (운영자 화면 권한으로만 검사)
add_group_api(router, "dml_manager")
