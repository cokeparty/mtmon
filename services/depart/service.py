# services/depart/service.py
"""
부서이동자 모니터링 비즈니스 로직

일간: 조회·유지/회수·SR 입력
월간: 조회·SR 입력·회수일 입력·엑셀 출력
"""
from __future__ import annotations


from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from models.depart import DailyRecord, MonthlyRecord
from models.common import MonitoringPeriod
from services.common import excel, sr
from services.common.period import get_or_create_period, get_period


# ──────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────
def _daily_to_dict(r: DailyRecord) -> dict[str, Any]:
    return {
        "id":            r.id,
        "record_type":    r.record_type,
        "empno":          r.empno,
        "emp_name":       r.emp_name or "",
        "change_date":    str(r.change_date) if r.change_date else "",
        "dept_code":      r.dept_code or "",
        "dept_name":      r.dept_name or "",
        "prev_dept_code": r.prev_dept_code or "",
        "prev_dept_name": r.prev_dept_name or "",
        "role_code":     r.role_code or "",
        "role_name":     r.role_name or "",
        "reg_date":      str(r.reg_date) if r.reg_date else "",
        "action":        r.action or "",
        "sr_no":         r.sr_no or "",
        "sr_title":      r.sr_title or "",
        "sr_work_type":  r.sr_work_type or "",
        "remark":        r.remark or "",
        "first_seen":     str(r.first_seen) if r.first_seen else "",
        "last_seen":      str(r.last_seen)  if r.last_seen  else "",
    }


def _monthly_to_dict(r: MonthlyRecord) -> dict[str, Any]:
    return {
        "id":             r.id,
        "system_code":    r.system_code,
        "empno":          r.empno,
        "emp_name":       r.emp_name or "",
        "change_date":    str(r.change_date) if r.change_date else "",
        "dept_code":      r.dept_code or "",
        "dept_name":      r.dept_name or "",
        "prev_dept_code": r.prev_dept_code or "",
        "prev_dept_name": r.prev_dept_name or "",
        "role_code":     r.role_code or "",
        "role_name":     r.role_name or "",
        "reg_date":      str(r.reg_date) if r.reg_date else "",
        "revoke_date":   str(r.revoke_date) if r.revoke_date else "",
        "sr_no":         r.sr_no or "",
        "sr_title":      r.sr_title or "",
        "sr_work_type":  r.sr_work_type or "",
        "remark":        r.remark or "",
    }


# ──────────────────────────────────────────────────────────────
# 일간 조회
# ──────────────────────────────────────────────────────────────
def get_daily_view(db: Session, year_month: str = None) -> dict:
    from sqlalchemy import extract, func as sqlfunc
    q = db.query(DailyRecord)
    if year_month:
        y, m = map(int, year_month.split("-"))
        q = q.filter(
            extract("year",  DailyRecord.change_date) == y,
            extract("month", DailyRecord.change_date) == m,
        )
    records = q.order_by(DailyRecord.record_type, DailyRecord.change_date.desc()).all()
    rows = [_daily_to_dict(r) for r in records]
    total   = len(rows)
    pending = sum(1 for r in records if not r.action and r.record_type in ("HR권한","전자조달권한","PMS권한"))

    last_batch_at_raw = db.query(sqlfunc.max(DailyRecord.updated_at)).scalar()
    last_batch_at = (
        last_batch_at_raw.strftime("%Y-%m-%d %H:%M:%S")
        if last_batch_at_raw else ""
    )
    return {
        "summary": {"total": total, "pending": pending},
        "records": rows,
        "last_batch_at": last_batch_at,
    }


# ──────────────────────────────────────────────────────────────
# 일간 — 유지/회수 처리 (reviewer 전용)
# ──────────────────────────────────────────────────────────────
def update_daily_action(
    db: Session,
    record_id: int,
    action: str,
    sr_no: Optional[str],
    remark: Optional[str],
    processed_by: int,
) -> dict:
    rec = db.query(DailyRecord).filter_by(id=record_id).first()
    if not rec:
        raise ValueError(f"레코드 {record_id} 없음")

    rec.action       = action
    rec.processed_by = processed_by
    rec.processed_at = datetime.now()
    if remark is not None:
        rec.remark = remark

    if sr_no:
        _apply_sr_to_daily(rec, sr_no, db)

    db.commit()
    return _daily_to_dict(rec)


# ──────────────────────────────────────────────────────────────
# 일간 — SR 입력 (operator·reviewer)
# ──────────────────────────────────────────────────────────────
def update_daily_sr(
    db: Session,
    record_id: int,
    sr_no: str,
    remark: Optional[str],
) -> dict:
    rec = db.query(DailyRecord).filter_by(id=record_id).first()
    if not rec:
        raise ValueError(f"레코드 {record_id} 없음")

    sr_found = _apply_sr_to_daily(rec, sr_no, db)
    if remark is not None:
        rec.remark = remark

    db.commit()
    result = _daily_to_dict(rec)
    result["sr_found"] = sr_found
    return result


def _apply_sr_to_daily(rec: DailyRecord, sr_no: str, db: Session) -> bool:
    """SR번호 → sr_db_client 자동 매핑. 반환: SR 존재 여부."""
    rec.sr_no = sr_no
    # 못 찾으면 이전 매핑값 초기화 (stale sr_title로 인한 '매핑됨' 원복 방지)
    rec.sr_title     = None
    rec.sr_work_type = None
    meta = sr.fetch_safe(sr_no)   # 조회 실패해도 sr_no 는 저장
    if meta:
        rec.sr_title     = meta.sr_title
        rec.sr_work_type = meta.sr_work_type
        return True
    return False


# ──────────────────────────────────────────────────────────────
# 월간 조회
# ──────────────────────────────────────────────────────────────
def get_monthly_view(db: Session, year_month: str, system_code: str) -> dict:
    from sqlalchemy import func as sqlfunc
    period = get_period(db, year_month)
    if not period:
        return {"records": [], "summary": {"total": 0}, "system_code": system_code, "last_batch_at": ""}

    records = (
        db.query(MonthlyRecord)
        .filter_by(period_id=period.id, system_code=system_code)
        .order_by(MonthlyRecord.change_date.desc())
        .all()
    )

    last_batch_at_raw = (
        db.query(sqlfunc.max(MonthlyRecord.updated_at))
        .filter_by(period_id=period.id)
        .scalar()
    )
    last_batch_at = (
        last_batch_at_raw.strftime("%Y-%m-%d %H:%M:%S")
        if last_batch_at_raw else ""
    )
    return {
        "system_code":  system_code,
        "summary":      {"total": len(records)},
        "records":      [_monthly_to_dict(r) for r in records],
        "last_batch_at": last_batch_at,
    }


def run_monthly_collect(db: Session, year_month: str) -> dict:
    from services.depart.collector import collect_monthly
    period = get_or_create_period(db, year_month)
    return collect_monthly(db, period.id, year_month)


def get_monthly_summary(db: Session, year_month: str) -> dict:
    period = get_period(db, year_month)
    kpi: dict = {
        "공통": {"total": 0},
        "HR":   {"total": 0, "applied": 0, "pending": 0},
        "PMS":  {"total": 0, "applied": 0, "pending": 0},
        "EPRO": {"total": 0, "applied": 0, "pending": 0},
        "progress": 0,
    }
    if not period:
        return kpi
    for sc in ("공통", "HR", "PMS", "EPRO"):
        rows = db.query(MonthlyRecord).filter_by(period_id=period.id, system_code=sc).all()
        total = len(rows)
        if sc == "공통":
            kpi[sc] = {"total": total}
        else:
            # 미적용 = SR번호 미입력 OR SR이 SR DB에 없음(=sr_title 미매핑)
            pending = sum(1 for r in rows if not r.sr_no or not r.sr_title)
            kpi[sc] = {"total": total, "applied": total - pending, "pending": pending}
    total_perm   = sum(kpi[sc]["total"] for sc in ("HR", "PMS", "EPRO"))
    applied_perm = sum(kpi[sc]["applied"] for sc in ("HR", "PMS", "EPRO"))
    kpi["progress"] = round(applied_perm / total_perm * 100) if total_perm else 0
    return kpi


# ──────────────────────────────────────────────────────────────
# 월간 — SR 입력 (operator·reviewer)
# ──────────────────────────────────────────────────────────────
def update_monthly_sr(
    db: Session,
    record_id: int,
    sr_no: str,
    remark: Optional[str],
) -> dict:
    rec = db.query(MonthlyRecord).filter_by(id=record_id).first()
    if not rec:
        raise ValueError(f"레코드 {record_id} 없음")

    rec.sr_no = sr_no
    sr_found = False
    # SR을 못 찾거나 조회 실패 시 이전 매핑값(sr_title·sr_work_type)을 반드시 초기화.
    # 그렇지 않으면 새로고침 때 stale sr_title 때문에 '매핑됨'으로 원복되고
    # KPI 미적용 집계에서도 누락됨.
    rec.sr_title     = None
    rec.sr_work_type = None
    meta = sr.fetch_safe(sr_no)
    if meta:
        rec.sr_title     = meta.sr_title
        rec.sr_work_type = meta.sr_work_type
        sr_found = True

    if remark is not None:
        rec.remark = remark

    db.commit()
    result = _monthly_to_dict(rec)
    result["sr_found"] = sr_found

    # SR 매핑/해제 즉시 반영을 위해 재계산된 KPI를 함께 반환 (새로고침 불필요)
    period = db.query(MonitoringPeriod).filter_by(id=rec.period_id).first()
    result["kpi"] = get_monthly_summary(db, period.year_month) if period else None
    return result


# ──────────────────────────────────────────────────────────────
# 월간 — 엑셀 출력 (final_file.md 형태)
# ──────────────────────────────────────────────────────────────
def export_monthly_excel(db: Session, year_month: str, system_code: str) -> bytes:
    """월간 부서이동자 엑셀.
    - 공통: 부서이동자 리스트 (부서변경일 · 사번 · 이름 · 이전부서 · 현재부서)
    - PMS · HR · EPRO: 권한 현황 (권한 · 등록/회수일 · 부서 · SR · 비고)
    """
    period = get_period(db, year_month)
    records = [] if not period else (
        db.query(MonthlyRecord).filter_by(period_id=period.id, system_code=system_code)
        .order_by(MonthlyRecord.change_date).all())

    def _d(v) -> str:
        return str(v) if v else ""

    if system_code == "공통":
        headers = ["부서변경일", "사번", "이름", "이전부서코드", "이전부서명", "현재부서코드", "현재부서명"]
        rows = [[_d(r.change_date), r.empno, r.emp_name or "", r.prev_dept_code or "",
                 r.prev_dept_name or "", r.dept_code or "", r.dept_name or ""] for r in records]
    else:
        headers = ["업무명", "부서변경일", "권한명", "권한코드", "사번", "이름", "권한등록일", "권한회수일",
                   "이전부서명", "현재부서명", "SR", "비고"]
        rows = [[r.system_code, _d(r.change_date), r.role_name or "", r.role_code or "", r.empno,
                 r.emp_name or "", _d(r.reg_date), _d(r.revoke_date), r.prev_dept_name or "",
                 r.dept_name or "", r.sr_no or "", r.remark or ""] for r in records]
    sheet = system_code if system_code != "공통" else "부서이동자"
    return excel.build(sheet, headers, rows, header_style="dark", auto_width=True)


