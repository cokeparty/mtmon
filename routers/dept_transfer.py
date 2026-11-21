"""
부서이동자 모니터링
GET  /dept-transfer              → 월간 모니터링 화면
GET  /dept-transfer/daily        → 일간 모니터링 화면
POST /dept-transfer/daily/action → 유지/회수 (operator·reviewer)
POST /dept-transfer/daily/sr     → SR 입력 (operator·reviewer·developer)
POST /dept-transfer/monthly/run  → 월간 조회 실행
POST /dept-transfer/monthly/sr   → 월간 SR 입력
POST /dept-transfer/monthly/revoke → 월간 회수일 입력 (reviewer)
GET  /dept-transfer/monthly/excel/{system} → 엑셀 다운로드
"""
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.deps import get_current_user
from core.permissions import (
    can_daily_dept_action, can_edit_daily_sr,
    can_monthly_dept_action,
    can_run_daily_batch, can_run_monthly_batch, PERM_DENIED_MSG,
)
from db.database import get_db
from models.auth import AppUser
from schemas.dept_transfer import (
    DailyActionRequest, DailySrRequest,
    MonthlySrRequest,
)
import services.dept_transfer_service as svc

logger = logging.getLogger(__name__)

BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
router    = APIRouter(tags=["DeptTransfer"])


def _default_ym() -> str:
    """월간 모니터링 기본 회차 = 전월(당월 아님)."""
    from core.periods import prev_month_ym
    return prev_month_ym()


def _current_ym() -> str:
    """일간 모니터링 기본 회차 = 당월."""
    return datetime.now().strftime("%Y-%m")


# ─────────────────────────────────────────
# 일간 화면
# ─────────────────────────────────────────
@router.get("/dept-transfer/daily", response_class=HTMLResponse)
async def daily_view(
    request:      Request,
    year_month:   str     = Query(default=None),
    db:           Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ym = year_month or _current_ym()
    try:
        data     = svc.get_daily_view(db, ym)
        db_error = False
    except OperationalError:
        data     = {"summary": {"total": 0, "pending": 0}, "records": [], "last_batch_at": ""}
        db_error = True

    return templates.TemplateResponse("dept_transfer_daily.html", {
        "request":  request,
        "active":   "dept_transfer",
        "current_user": {
            "id":   current_user.id,
            "name": current_user.name,
            "role": current_user.role,
        },
        "db_error": db_error,
        "year_month": ym,
        **data,
    })


@router.post("/dept-transfer/daily/action")
async def daily_action(
    payload: DailyActionRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_daily_dept_action(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
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


@router.post("/dept-transfer/daily/sr")
async def daily_sr(
    payload: DailySrRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_edit_daily_sr(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        rec = svc.update_daily_sr(db, payload.record_id, payload.sr_no, payload.remark)
        return {"ok": True, "record": rec, "sr_found": rec.get("sr_found", False)}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/dept-transfer/daily/run")
async def daily_run(
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_run_daily_batch(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        from services.dept_transfer_collector import collect_daily
        result = collect_daily(db)
        partial_error = any(not t["ok"] for t in result.get("tasks", []))
        return {"ok": True, "result": result, "partial_error": partial_error}
    except Exception as e:
        logger.exception("일간 배치 실행 실패")
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


# ─────────────────────────────────────────
# 월간 화면
# ─────────────────────────────────────────
@router.get("/dept-transfer", response_class=HTMLResponse)
async def monthly_view(
    request:      Request,
    year_month:   str = Query(default=None),
    system_code:  str = Query(default="공통"),
    db:           Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ym = year_month or _default_ym()
    _kpi_empty = {
        "공통": {"total": 0},
        "HR":   {"total": 0, "applied": 0, "pending": 0},
        "PMS":  {"total": 0, "applied": 0, "pending": 0},
        "EPRO": {"total": 0, "applied": 0, "pending": 0},
        "progress": 0,
    }
    try:
        data     = svc.get_monthly_view(db, ym, system_code)
        kpi      = svc.get_monthly_summary(db, ym)
        db_error = False
    except OperationalError:
        data     = {"records": [], "summary": {"total": 0}, "system_code": system_code, "last_batch_at": ""}
        kpi      = _kpi_empty
        db_error = True

    return templates.TemplateResponse("dept_transfer.html", {
        "request":  request,
        "active":   "dept_transfer",
        "period":   ym,
        "kpi":      kpi,
        "current_user": {
            "id":   current_user.id,
            "name": current_user.name,
            "role": current_user.role,
        },
        "db_error": db_error,
        **data,
    })


@router.post("/dept-transfer/monthly/run")
async def monthly_run(
    request:    Request,
    year_month: str = Query(default=None),
    db:         Session = Depends(get_db),
):
    if not can_run_monthly_batch(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    ym = year_month or _default_ym()
    try:
        result = svc.run_monthly_collect(db, ym)
        for task in result.get("tasks", []):
            if not task.get("ok"):
                logger.error("[월간수집] %s 실패: %s", task["code"], task.get("error"))
        return {"ok": True, "result": result}
    except Exception as e:
        logger.exception("월간 조회 실행 실패 year_month=%s", ym)
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


@router.post("/dept-transfer/monthly/sr")
async def monthly_sr(
    payload: MonthlySrRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    if not can_monthly_dept_action(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        rec = svc.update_monthly_sr(db, payload.record_id, payload.sr_no, payload.remark)
        sr_found = rec.pop("sr_found", False)
        kpi      = rec.pop("kpi", None)
        return {"ok": True, "record": rec, "sr_found": sr_found, "kpi": kpi}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.get("/dept-transfer/monthly/excel/{system_code}")
async def monthly_excel(
    system_code: str,
    year_month:  str = Query(default=None),
    db:          Session = Depends(get_db),
):
    ym = year_month or _default_ym()
    try:
        xlsx = svc.export_monthly_excel(db, ym, system_code)
        filename = f"부서이동자_{ym}_{system_code}.xlsx"
        encoded  = quote(filename, safe="")
        return Response(
            content=xlsx,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"},
        )
    except ValueError as e:
        logger.error("엑셀 다운로드 실패 ym=%s sc=%s: %s", ym, system_code, e)
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)
