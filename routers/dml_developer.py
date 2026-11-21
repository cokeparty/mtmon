"""
DML 개발자 뷰
- 본인에게 할당된 그룹만 조회
- SR 번호 입력 → 그룹 + 소속 로그 행 일괄 적용
"""
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from core.deps import get_current_user
from core.permissions import can_edit_dml_developer, PERM_DENIED_MSG
from db.database import get_db
from models.auth import AppUser
from schemas.dml import ApplySrRequest, BulkApplySrRequest, ClearSrRequest, SetDmlRequest, SetReasonRequest
import services.dml_service as dml_service

BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
router    = APIRouter(prefix="/dml/developer", tags=["DML-Developer"])


def _default_ym() -> str:
    """월간 모니터링 기본 회차 = 전월(당월 아님)."""
    from core.periods import prev_month_ym
    return prev_month_ym()


# ─────────────────────────────────────────
# 화면
# ─────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def dml_developer_view(
    request:      Request,
    year_month:   str = Query(default=None),
    db:           Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ym = year_month or _default_ym()

    db_user = current_user.name

    try:
        data = dml_service.get_developer_view(db, ym, current_user.name)
        data["db_error"] = False
    except OperationalError:
        data = {
            "period": ym,
            "summary": {"total": 0, "applied": 0, "pending": 0, "progress_pct": 0},
            "groups": [], "db_error": True,
        }
    return templates.TemplateResponse("dml_developer.html", {
        "request":      request,
        "active":       "dml_developer",
        "current_user": {
            "id": current_user.id,
            "name": current_user.name,
            "role": current_user.role,
        },
        **data,
    })


# ─────────────────────────────────────────
# API
# ─────────────────────────────────────────
@router.get("/group/{group_id}/logs")
async def get_group_logs_api(
    group_id: int,
    db:       Session = Depends(get_db),
):
    """그룹에 속한 DmlLog 행 목록 반환."""
    try:
        logs = dml_service.get_group_logs(group_id, db)
        return {"ok": True, "logs": logs}
    except Exception as e:
        return {"ok": False, "message": str(e)}


@router.post("/apply-sr")
async def apply_sr_to_group(
    payload: ApplySrRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    """그룹에 SR번호 일괄 적용 (그룹 + 소속 dml_log 행 모두 업데이트)."""
    if not can_edit_dml_developer(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        group, sr_found = dml_service.apply_sr(payload.group_id, payload.sr_no.strip(), db)
        return {"ok": True, "group": group, "sr_found": sr_found}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/clear-sr")
async def clear_sr_from_group(
    payload: ClearSrRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    """그룹의 SR번호 제거."""
    if not can_edit_dml_developer(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        group = dml_service.clear_sr(payload.group_id, db)
        return {"ok": True, "group": group}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/set-dml")
async def set_group_dml(
    payload: SetDmlRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    """그룹의 DML여부 설정 (비DML이면 SR 없이도 정상·적용완료)."""
    if not can_edit_dml_developer(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        group = dml_service.set_dml(payload.group_id, payload.is_dml, db)
        return {"ok": True, "group": group}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)


@router.post("/bulk-apply-sr")
async def bulk_apply_sr(
    payload: BulkApplySrRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    """순번 범위 일괄 SR 적용. 비DML 및 skip_existing 대상은 건너뜀."""
    if not can_edit_dml_developer(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    if not payload.group_ids:
        return JSONResponse({"ok": False, "message": "적용할 그룹이 없습니다."}, status_code=400)
    try:
        result = dml_service.bulk_apply_sr(
            payload.group_ids, payload.sr_no.strip(), payload.skip_existing, db
        )
        return {"ok": True, **result}
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


@router.post("/set-reason")
async def set_group_reason(
    payload: SetReasonRequest,
    request: Request,
    db:      Session = Depends(get_db),
):
    """비정상 그룹의 소명 사유 저장 (최대 500자)."""
    if not can_edit_dml_developer(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        group = dml_service.set_reason(payload.group_id, payload.reason, db)
        return {"ok": True, "group": group}
    except ValueError as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=404)
