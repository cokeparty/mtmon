"""
프로그램변경 (조회 · SR 입력 · 엑셀)
GET   /program                 → 화면
GET   /program/api/list        → 목록 (필터)
GET   /program/api/load-info   → 적재 정보 (푸터)
PATCH /program/api/{id}/sr     → SR 입력 + SR DB 자동 매핑 + 판정
PATCH /program/api/{id}/fields → 결재/담당 항목 수정
GET   /program/api/export      → 엑셀

수집 실행은 '배치관리' 화면에서만 한다.
권한: 화면·조회 = 프로그램변경 조회 권한, SR·항목 수정 = 수정 권한 (core/permissions.py).
DB 연결 실패(OperationalError)는 main.py 의 공통 핸들러가 503 으로 응답한다.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from core.permissions import page_edit, page_view
from core.web import render
from db.database import get_db
from models.common import MonitoringPeriod
from models.program import ProgramChangeLog
from schemas.program import (FieldUpdate, LoadInfo, ProgramChangeListResponse,
                             ProgramChangeRow, SrUpdate)
from services.common import excel, sr
from services.common.fmt import fmt_datetime
from services.common.period import get_period
from services.common.sr_validation import judge_validation
from services.program import excel as program_excel, view as pcl_view

router = APIRouter(prefix="/program", tags=["program-change"])
SYSTEMS = ["HR", "EPRO", "SR", "PMS"]


def _period(db: Session, ym: str) -> MonitoringPeriod:
    p = get_period(db, ym)
    if not p:
        raise HTTPException(404, f"회차 없음: {ym}")
    return p


def _day(v):
    """판정(검증결과)·이관전승인 계산은 날짜 단위 → 자정 기준 datetime."""
    if v is None:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d")
    except ValueError:
        return None


# ----- 화면 -----
@router.get("", response_class=HTMLResponse)
def page(request: Request, current_user=Depends(page_view("program"))):
    return render(request, "program.html", {"active": "program", "systems": SYSTEMS})


# ----- 리스트 조회 (필터) -----
@router.get("/api/list", response_model=ProgramChangeListResponse)
def list_rows(year_month: str, system_code: str,
              source_file: str | None = None, sr_no: str | None = None,
              result: str = Query("전체"),
              db: Session = Depends(get_db), _u=Depends(page_view("program"))):
    p = _period(db, year_month)
    q = db.query(ProgramChangeLog).filter(ProgramChangeLog.period_id == p.id,
                                          ProgramChangeLog.system_code == system_code)
    if source_file:
        q = q.filter(ProgramChangeLog.file_name.ilike(f"%{source_file}%"))
    if sr_no:
        q = q.filter(ProgramChangeLog.sr_no.ilike(f"%{sr_no}%"))
    if result != "전체":
        q = q.filter(ProgramChangeLog.result == result)
    rows = q.order_by(ProgramChangeLog.deploy_time).all()

    # SR DB 존재여부 → 검증결과 (엑셀과 같은 기준)
    in_db = sr.existing_set(r.sr_no for r in rows)
    row_objs = []
    for r in rows:
        obj = ProgramChangeRow.model_validate(r)
        if r.sr_no and in_db is not None:
            obj.sr_in_db = r.sr_no in in_db
        row_objs.append(obj)
    return ProgramChangeListResponse(year_month=year_month, system_code=system_code,
                                     total=len(row_objs), rows=row_objs)


# ----- 배치 적재 메타 (푸터 표시용) -----
@router.get("/api/load-info", response_model=LoadInfo)
def load_info(year_month: str, system_code: str, db: Session = Depends(get_db),
              _u=Depends(page_view("program"))):
    p = _period(db, year_month)
    q = db.query(ProgramChangeLog).filter(ProgramChangeLog.period_id == p.id,
                                          ProgramChangeLog.system_code == system_code)
    last = q.order_by(ProgramChangeLog.created_at.desc()).first()
    return LoadInfo(period=year_month, loaded_at=last.created_at if last else None,
                    row_count=q.count())


# ----- SR 번호 수정 + SR DB 자동매핑 + 판정 -----
@router.patch("/api/{row_id}/sr")
def update_sr(row_id: int, body: SrUpdate, db: Session = Depends(get_db),
              _u=Depends(page_edit("program"))):
    row = db.get(ProgramChangeLog, row_id)
    if not row:
        raise HTTPException(404, "행 없음")

    sr_no = (body.sr_no or "").strip()
    meta = sr.fetch_safe(sr_no) if sr_no else None
    row.sr_no          = sr_no or None
    row.sr_title       = ((meta.sr_title or "").strip() or None) if meta else None
    row.sr_work_type   = ((meta.sr_work_type or "").strip() or None) if meta else None
    row.sr_approved_at = meta.sr_approved_at if meta else None
    row.sr_closed_at   = meta.sr_closed_at if meta else None
    # '이관전 승인'은 SR(작업승인일) 기준 자동값 → 고정 저장값을 비워 즉시 재계산되게 한다.
    row.approval_pre_deploy = None

    # 검증결과 계산 후 DB에도 반영 (새로고침 시 일관성 유지)
    if not meta:
        ui_status, row.result, row.normal_yn = "미적용", "SR없음", "이상"
    elif judge_validation(row.deploy_time, _day(row.sr_approved_at), _day(row.sr_closed_at),
                          row.sr_work_type or "") == "정상":
        ui_status, row.result, row.normal_yn = "정상", "정상", "정상"
    else:
        ui_status, row.result, row.normal_yn = "비정상", "이상", "이상"
    db.commit()

    return {
        "ok":             True,
        "sr_found":       meta is not None,
        "sr_title":       row.sr_title or "",
        "sr_work_type":   row.sr_work_type or "",
        "sr_approved_at": fmt_datetime(row.sr_approved_at),
        "sr_closed_at":   fmt_datetime(row.sr_closed_at),
        "ui_status":      ui_status,
        "monitoring_result": pcl_view.monitoring_result(ui_status, row.reason),
        "eff_approval_pre_deploy": pcl_view._pick(
            row.approval_pre_deploy,
            pcl_view.default_pre_deploy(row.deploy_time, _day(row.sr_approved_at))),
    }


# ----- 편집 칼럼 저장 (결재/이관자/개발자/검토수행자/사유) -----
@router.patch("/api/{row_id}/fields")
def update_fields(row_id: int, body: FieldUpdate, db: Session = Depends(get_db),
                  _u=Depends(page_edit("program"))):
    row = db.get(ProgramChangeLog, row_id)
    if not row:
        raise HTTPException(404, "행 없음")

    # 보낸 필드만 반영 (빈 문자열은 None 으로 저장 → 디폴트 재적용)
    for k, v in body.model_dump(exclude_unset=True).items():
        v = (v or "").strip() if isinstance(v, str) else v
        setattr(row, k, v or None)
    db.commit()
    db.refresh(row)

    obj = ProgramChangeRow.model_validate(row)
    if row.sr_no:   # 검증결과는 SR DB 존재여부에 의존 → 단건 재조회
        s = sr.existing_set([row.sr_no])
        if s is not None:
            obj.sr_in_db = row.sr_no in s
    return {
        "ok": True,
        "ui_status": obj.ui_status,
        "monitoring_result": obj.monitoring_result,
        "eff": {
            "approval_change_request": obj.eff_approval_change_request,
            "approval_user_test":      obj.eff_approval_user_test,
            "approval_pre_deploy":     obj.eff_approval_pre_deploy,
            "transferer":              obj.eff_transferer,
            "sr_developer":            obj.eff_sr_developer,
            "sr_reviewer":             obj.eff_sr_reviewer,
        },
        "reason": row.reason or "",
    }


# ----- 엑셀 출력 -----
@router.get("/api/export")
def export(year_month: str, system_code: str, db: Session = Depends(get_db),
           _u=Depends(page_view("program"))):
    p = get_period(db, year_month)          # 회차가 없어도 빈 양식으로 내려준다
    content = program_excel.export(db, p.id if p else None, system_code)
    return excel.response(content, f"{system_code}_프로그램변경_리스트_{year_month.replace('-', '')}.xlsx",
                          ascii_fallback=f"program_change_{system_code}_{year_month}.xlsx")
