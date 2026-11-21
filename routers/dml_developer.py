"""
DML 개발자 화면 (데이터변경 - 개발자 화면)
- 선택한 개발자(기본: 로그인한 본인)의 그룹 조회 — 운영자도 개발자를 골라 같은 화면을 본다
- SR 번호 입력 → 그룹 + 소속 로그 행 일괄 적용

수정 API 는 routers/dml_group_api.py — 이 화면 주소(/dml/developer/...)는 개발자 화면 권한으로만 검사한다.
"""

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from core.permissions import page_view
from core.web import render, default_ym
from db.database import get_db
from routers.dml_group_api import add_group_api
import services.dml.service as dml_service

router    = APIRouter(prefix="/dml/developer", tags=["DML-Developer"])



# ─────────────────────────────────────────
# 화면
# ─────────────────────────────────────────
@router.get("", response_class=HTMLResponse)
async def dml_developer_view(
    request:      Request,
    year_month:   str = Query(default=None),
    developer:    str = Query(default=None),
    db:           Session = Depends(get_db),
    current_user          = Depends(page_view("dml_developer")),
):
    ym  = year_month or default_ym()
    dev = (developer or "").strip() or current_user.name

    data = dml_service.get_developer_view(db, ym, dev)
    return render(request, "dml_developer.html", {
        "active":    "dml_developer",
        "developer": dev,
        "choices":   dml_service.developer_choices(db, ym),
        **data,
    })


# ─────────────────────────────────────────
# API — 그룹 조회·수정 (개발자 화면 권한으로만 검사)
# ─────────────────────────────────────────
add_group_api(router, "dml_developer")
