"""
부서이동자 모니터링 — 일간 · 월간은 메뉴와 권한이 따로다.
GET  /depart/daily        → 일간 화면                (부서이동자(일간) 조회)
POST /depart/daily/action → 유지/회수                (부서이동자(일간) 수정)
POST /depart/daily/sr     → SR 입력                  (부서이동자(일간) 수정)
GET  /depart              → 월간 화면                (부서이동자(월간) 조회)
POST /depart/monthly/sr   → 월간 SR 입력             (부서이동자(월간) 수정)
GET  /depart/monthly/excel/{system} → 엑셀 다운로드  (부서이동자(월간) 조회)

수집 실행은 '배치관리' 화면에서만 한다.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from core.permissions import page_edit, page_view
from core.web import render, default_ym
from db.database import get_db
from services.common import excel
from schemas.depart import (
    DailyActionRequest, DailySrRequest,
    MonthlySrRequest,
)
import services.depart.service as svc

logger = logging.getLogger(__name__)

router    = APIRouter(tags=["DeptTransfer"])


def _current_ym() -> str:
    """일간 모니터링 기본 회차 = 당월."""
    return datetime.now().strftime("%Y-%m")


# ─────────────────────────────────────────
# 일간 화면
# ─────────────────────────────────────────
@router.get("/depart/daily", response_class=HTMLResponse)
async def daily_view(
    request:      Request,
    year_month:   str     = Query(default=None),
    db:           Session = Depends(get_db),
    current_user          = Depends(page_view("depart_daily")),
):
    ym = year_month or _current_ym()
    data = svc.get_daily_view(db, ym)
    return render(request, "depart_daily.html", {
        "active": "depart_daily",
        "year_month": ym,
        **data,
    })


@router.post("/depart/daily/action")
async def daily_action(
    payload: DailyActionRequest,
    request: Request,
    db:      Session = Depends(get_db),
    _u                = Depends(page_edit("depart_daily")),
):
    processed_by = request.session.get("user_id", 0)
    if payload.action not in ("유지", "회수"):
        return JSONResponse({"ok": False, "message": "action은 유지 또는 회수"}, status_code=400)
    try:
        rec = svc.update_daily_action(
            db, payload.record_id, payload.action,
            payload.sr_no, payload.remark, processed_by,
        )
        return {"ok": True, "record": rec}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/depart/daily/sr")
async def daily_sr(
    payload: DailySrRequest,
    db:      Session = Depends(get_db),
    _u                = Depends(page_edit("depart_daily")),
):
    try:
        rec = svc.update_daily_sr(db, payload.record_id, payload.sr_no, payload.remark)
        return {"ok": True, "record": rec, "sr_found": rec.get("sr_found", False)}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


# ─────────────────────────────────────────
# 월간 화면
# ─────────────────────────────────────────
@router.get("/depart", response_class=HTMLResponse)
async def monthly_view(
    request:      Request,
    year_month:   str = Query(default=None),
    system_code:  str = Query(default="공통"),
    db:           Session = Depends(get_db),
    current_user          = Depends(page_view("depart_monthly")),
):
    ym = year_month or default_ym()
    data = svc.get_monthly_view(db, ym, system_code)
    kpi = svc.get_monthly_summary(db, ym)
    return render(request, "depart.html", {
        "active": "depart_monthly",
        "period":   ym,
        "kpi":      kpi,
        **data,
    })


@router.post("/depart/monthly/sr")
async def monthly_sr(
    payload: MonthlySrRequest,
    db:      Session = Depends(get_db),
    _u                = Depends(page_edit("depart_monthly")),
):
    try:
        rec = svc.update_monthly_sr(db, payload.record_id, payload.sr_no, payload.remark)
        sr_found = rec.pop("sr_found", False)
        kpi      = rec.pop("kpi", None)
        return {"ok": True, "record": rec, "sr_found": sr_found, "kpi": kpi}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.get("/depart/monthly/excel/{system_code}")
async def monthly_excel(
    system_code: str,
    year_month:  str = Query(default=None),
    db:          Session = Depends(get_db),
    _u                   = Depends(page_view("depart_monthly")),
):
    ym = year_month or default_ym()
    content = svc.export_monthly_excel(db, ym, system_code)   # 데이터가 없어도 빈 양식
    return excel.response(content, f"부서이동자_{ym}_{system_code}.xlsx")
