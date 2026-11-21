# services/ddl_service.py
"""
DDL 모니터링 비즈니스 로직

담당자 = 개발자 (단일 역할) → 화면 1개
행 단위 SR 입력 (DML처럼 그룹 테이블 없음)
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO
from typing import Any, Optional

import pandas as pd
from sqlalchemy.orm import Session

from config import settings
from models.ddl import DdlLog, DdlType
from models.dml import DmlStatus
from models.period import MonitoringPeriod
from services import ddl_parser as parser
from services import sr_validation as validation
from services.sr_db_client import SrDbClient


def _safe_ddl_type(raw: str) -> DdlType:
    """감지된 DDL 타입 문자열 → DdlType enum.
    None 이거나 알 수 없는 값이면 ALTER 대신 None 처리를 피하기 위해
    CREATE 로 fallback하지 않고 ALTER 를 쓴다.
    실질적으로는 파서가 반환하는 값(CREATE/ALTER/DROP/TRUNCATE/RENAME)만 들어온다.
    """
    if not raw:
        return DdlType.ALTER
    try:
        return DdlType(raw.upper())
    except ValueError:
        return DdlType.ALTER


# ──────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────
def _current_ym() -> str:
    return datetime.now().strftime("%Y-%m")


def _get_or_create_period(db: Session, year_month: str) -> MonitoringPeriod:
    p = db.query(MonitoringPeriod).filter_by(year_month=year_month).first()
    if not p:
        p = MonitoringPeriod(year_month=year_month)
        db.add(p)
        db.flush()
    return p


def _fmt_date(d) -> str:
    """날짜/Timestamp → YYYY-MM-DD 문자열. 없으면 빈 문자열."""
    if d is None:
        return ""
    try:
        if pd.isna(d):
            return ""
    except (TypeError, ValueError):
        pass
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    s = str(d)
    return s[:10] if len(s) >= 10 else s


def _fetch_sr_info_map(sr_nos: list[str]) -> dict[str, dict]:
    """SR번호 목록을 SR DB에서 조회 → {sr_no: {sr_title, work_type, appr_date, close_date}}"""
    if not sr_nos:
        return {}
    try:
        sr_client = SrDbClient(settings.SR_DB_URL)
        sr_df = sr_client.fetch_many_df(sr_nos)
        result: dict[str, dict] = {}
        for _, row in sr_df.iterrows():
            no = str(row.get("SR번호", "")).strip()
            if no:
                result[no] = {
                    "sr_title":   str(row.get("SR제목") or ""),
                    "work_type":  str(row.get("작업구분") or ""),
                    "appr_date":  _fmt_date(row.get("작업승인일")),
                    "close_date": _fmt_date(row.get("SR종료일")),
                }
        return result
    except Exception:
        return {}


def _compute_ui_status(l: DdlLog, sr_info: dict | None) -> str:
    """3단계 UI 표시 상태: 미적용 / 비정상 / 정상"""
    if not l.sr_no:
        return "미적용"

    # sr_info가 None == SR DB에 해당 번호 없음
    if sr_info is None:
        return "미적용"

    work_type  = sr_info.get("work_type") or ""
    appr_date  = sr_info.get("appr_date") or ""
    close_date = sr_info.get("close_date") or ""

    def _parse(s: str):
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d") if s else None
        except ValueError:
            return None

    result = validation.judge_validation(
        l.request_time, _parse(appr_date), _parse(close_date), work_type
    )
    return "정상" if result == "정상" else "비정상"


def _log_to_dict(l: DdlLog, sr_info: dict | None = None) -> dict[str, Any]:
    info = sr_info or {}
    return {
        "log_id":               l.id,
        "system":               l.system_code,
        "request_time":         l.request_time.strftime("%Y-%m-%d %H:%M:%S") if l.request_time else "",
        "db_user":              l.db_user,
        "conn_account":         l.conn_account,
        "target_object":        l.target_object,
        "ddl_type":             str(l.ddl_type or ""),
        "query_summary":        l.query_summary or "",
        "is_abnormal":          l.is_abnormal,
        "sr_no":                l.sr_no or "",
        "status":               str(l.status or ""),
        "ui_status":            _compute_ui_status(l, sr_info),
        "ddl_reason":           l.ddl_reason or "",
        "sr_title":             info.get("sr_title") or "",
        "work_type":            info.get("work_type") or "",
        "appr_date":            info.get("appr_date") or "",
        "close_date":           info.get("close_date") or "",
        "proc_change_approval": l.proc_change_approval or "O",
        "user_test":            l.user_test or "O",
        "pre_release_approval": l.pre_release_approval or "",
        "developer":            l.developer or "",
        "releaser":             l.releaser or "이기헌",
        "reviewer_name":        l.reviewer_name or "노광환",
    }


# ──────────────────────────────────────────────────────────────
# CSV 업로드 & 적재
# ──────────────────────────────────────────────────────────────
def import_csv(
    content: bytes,
    year_month: str,
    system_code: str,
    db: Session,
) -> dict:
    result = parser.parse(content)
    period = _get_or_create_period(db, year_month)

    # 기존 데이터 삭제 (재업로드)
    db.query(DdlLog).filter_by(period_id=period.id, system_code=system_code).delete()

    for _, row in result.rows.iterrows():
        sr_val   = row.get("sr_no") or None
        ddl_type = row.get("ddl_type")
        dl = DdlLog(
            period_id            = period.id,
            system_code          = system_code,
            request_time         = row["req_time"] if not pd.isna(row["req_time"]) else None,
            db_user              = row["user_name"],
            conn_account         = row["account"],
            target_object        = row["target_object"],
            ddl_type             = _safe_ddl_type(ddl_type),
            query_summary        = (row["command"] or "")[:500] or None,
            is_abnormal          = bool(row.get("is_abnormal", False)),
            sr_no                = sr_val,
            status               = DmlStatus.적용됨 if sr_val else DmlStatus.미입력,
            proc_change_approval = "O",
            user_test            = "O",
            releaser             = "이기헌",
            reviewer_name        = "노광환",
        )
        db.add(dl)

    db.commit()
    return {**result.stats, "period_id": period.id}


# ──────────────────────────────────────────────────────────────
# 단일 뷰 조회
# ──────────────────────────────────────────────────────────────
def get_view(
    db: Session,
    year_month: str,
    system_code: str,
) -> dict:
    period = db.query(MonitoringPeriod).filter_by(year_month=year_month).first()
    if not period:
        return _empty_view(year_month, system_code)

    logs = (
        db.query(DdlLog)
        .filter_by(period_id=period.id, system_code=system_code)
        .order_by(DdlLog.request_time)
        .all()
    )

    total = len(logs)

    sr_nos = list({l.sr_no for l in logs if l.sr_no})
    sr_map = _fetch_sr_info_map(sr_nos)

    # KPI 정의
    #   미적용    = SR없음 (ui_status == "미적용")
    #   사유미입력 = 비정상 + ddl_reason 없음
    #   적용완료  = SR있음 + (정상 OR (비정상 + 사유있음))
    #   진행률    = 적용완료 / 전체
    ui_statuses = [_compute_ui_status(l, sr_map.get(l.sr_no or "")) for l in logs]
    pending   = sum(1 for u in ui_statuses if u == "미적용")
    no_reason = sum(
        1 for l, u in zip(logs, ui_statuses)
        if u == "비정상" and not (l.ddl_reason or "").strip()
    )
    applied = sum(
        1 for l, u in zip(logs, ui_statuses)
        if u == "정상" or (u == "비정상" and (l.ddl_reason or "").strip())
    )

    from sqlalchemy import func as sqlfunc
    last_uploaded_at_raw = (
        db.query(sqlfunc.max(DdlLog.created_at))
        .filter_by(period_id=period.id, system_code=system_code)
        .scalar()
    )
    last_uploaded_at = (
        last_uploaded_at_raw.strftime("%Y-%m-%d %H:%M:%S")
        if last_uploaded_at_raw else ""
    )

    return {
        "period":           year_month,
        "system_code":      system_code,
        "last_uploaded_at": last_uploaded_at,
        "summary": {
            "total":        total,
            "applied":      applied,
            "pending":      pending,
            "no_reason":    no_reason,
            "progress_pct": round(applied / total * 100) if total else 0,
        },
        "logs": [_log_to_dict(l, sr_map.get(l.sr_no or "")) for l in logs],
    }


# ──────────────────────────────────────────────────────────────
# SR 행 단위 적용 / 취소
# ──────────────────────────────────────────────────────────────
def apply_sr(log_id: int, sr_no: str, db: Session) -> tuple[dict, bool]:
    log = db.query(DdlLog).filter_by(id=log_id).first()
    if not log:
        raise ValueError(f"로그 {log_id} 없음")
    log.sr_no  = sr_no
    log.status = DmlStatus.적용됨
    db.commit()
    db.refresh(log)
    sr_info_map = _fetch_sr_info_map([sr_no]) if sr_no else {}
    sr_info  = sr_info_map.get(sr_no)
    sr_found = sr_no in sr_info_map

    # 이관전승인: 항상 최신화 (SR없거나 승인일 없으면 X)
    auto_pre = "X"
    if sr_info and sr_info.get("appr_date") and log.request_time:
        try:
            appr_dt = datetime.strptime(sr_info["appr_date"][:10], "%Y-%m-%d")
            req_dt  = log.request_time if hasattr(log.request_time, "date") else datetime.fromisoformat(str(log.request_time))
            auto_pre = "O" if appr_dt <= req_dt else "X"
        except (ValueError, TypeError):
            auto_pre = "X"
    log.pre_release_approval = auto_pre
    db.commit()
    db.refresh(log)

    return _log_to_dict(log, sr_info), sr_found


def clear_sr(log_id: int, db: Session) -> dict:
    log = db.query(DdlLog).filter_by(id=log_id).first()
    if not log:
        raise ValueError(f"로그 {log_id} 없음")
    log.sr_no  = None
    log.status = DmlStatus.미입력
    db.commit()
    db.refresh(log)
    return _log_to_dict(log)


def save_reason(log_id: int, reason: str, db: Session) -> dict:
    log = db.query(DdlLog).filter_by(id=log_id).first()
    if not log:
        raise ValueError(f"로그 {log_id} 없음")
    log.ddl_reason = (reason or "").strip()[:500] or None
    db.commit()
    db.refresh(log)
    sr_map = _fetch_sr_info_map([log.sr_no]) if log.sr_no else {}
    return _log_to_dict(log, sr_map.get(log.sr_no or ""))


_EDITABLE_FIELDS = {
    "proc_change_approval", "user_test", "pre_release_approval",
    "developer", "releaser", "reviewer_name",
}

def save_fields(log_id: int, fields: dict, db: Session) -> dict:
    log = db.query(DdlLog).filter_by(id=log_id).first()
    if not log:
        raise ValueError(f"로그 {log_id} 없음")
    for k, v in fields.items():
        if k in _EDITABLE_FIELDS:
            setattr(log, k, (str(v).strip()[:100] or None) if v else None)
    db.commit()
    db.refresh(log)
    sr_map = _fetch_sr_info_map([log.sr_no]) if log.sr_no else {}
    return _log_to_dict(log, sr_map.get(log.sr_no or ""))


# ──────────────────────────────────────────────────────────────
# Enrich (SR DB 조회 + 검증 통계 + 로그별 SR 정보)
# ──────────────────────────────────────────────────────────────
def run_enrich(db: Session, year_month: str, system_code: str) -> dict:
    period = db.query(MonitoringPeriod).filter_by(year_month=year_month).first()
    if not period:
        return {"ok": False, "message": "해당 회차 없음"}

    logs = db.query(DdlLog).filter_by(
        period_id=period.id, system_code=system_code
    ).all()
    if not logs:
        return {"ok": False, "message": "적재된 로그 없음"}

    rows_df = pd.DataFrame([
        {"sr_no": l.sr_no, "req_time": l.request_time}
        for l in logs
    ])

    try:
        sr_client = SrDbClient(settings.SR_DB_URL)
        enriched  = validation.enrich_and_validate(rows_df, sr_client)
    except Exception as e:
        return {"ok": False, "message": f"SR DB 조회 실패: {e}"}

    v = enriched.get("validation", pd.Series(dtype=object))
    ok_cnt = int((v == "정상").sum())
    ng_cnt = int((v == "비정상").sum())
    na_cnt = int(v.isna().sum())

    # enriched df에서 sr_no별 SR 정보 추출
    sr_info_by_no: dict[str, dict] = {}
    if "sr_title" in enriched.columns:
        valid_mask = (
            enriched["sr_no"].notna()
            & (enriched["sr_no"].astype(str).str.strip() != "")
        )
        for _, row in enriched[valid_mask].drop_duplicates("sr_no").iterrows():
            no = str(row["sr_no"]).strip()
            if no:
                sr_info_by_no[no] = {
                    "sr_title":   str(row.get("sr_title") or ""),
                    "work_type":  str(row.get("work_type") or ""),
                    "appr_date":  _fmt_date(row.get("appr_date")),
                    "close_date": _fmt_date(row.get("close_date")),
                }

    # 로그별 SR 정보 매핑 (JS에서 테이블 셀 업데이트용)
    log_sr: dict[str, dict] = {}
    for l in logs:
        if l.sr_no and l.sr_no in sr_info_by_no:
            log_sr[str(l.id)] = sr_info_by_no[l.sr_no]

    return {
        "ok":     True,
        "stats":  {"정상": ok_cnt, "비정상": ng_cnt, "판정불가": na_cnt},
        "log_sr": log_sr,
    }


# ──────────────────────────────────────────────────────────────
# 엑셀 출력
# ──────────────────────────────────────────────────────────────
def export_excel(db: Session, year_month: str, system_code: str) -> Optional[BytesIO]:
    """
    DDL 로그 + SR 정보 + 검증결과 → XLSX BytesIO.
    컬럼: 명령어, 요청 시각, 접속계정, 사용자명, SR번호, SR제목, 작업구분, 작업승인일, SR종료일, 검증결과,
          프로시저 변경요청/승인, 사용자테스트, 이관전 승인, 개발자, 이관자, 검토수행자, 모니터링 결과
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    period = db.query(MonitoringPeriod).filter_by(year_month=year_month).first()
    if not period:
        return None

    logs = (
        db.query(DdlLog)
        .filter_by(period_id=period.id, system_code=system_code)
        .order_by(DdlLog.request_time)
        .all()
    )
    if not logs:
        return None

    # 검증결과는 웹 화면과 동일하게 _compute_ui_status로 산출 (정상/비정상/미적용 일치)
    sr_nos = list({l.sr_no for l in logs if l.sr_no})
    sr_info_map = _fetch_sr_info_map(sr_nos)

    def _req_str(v) -> str:
        if v is None:
            return ""
        try:
            if pd.isna(v):
                return ""
        except (TypeError, ValueError):
            pass
        return v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime") else str(v)

    HEADERS = [
        "명령어", "요청 시각", "접속계정", "사용자명",
        "SR번호", "SR제목", "작업구분", "작업승인일", "SR종료일", "검증결과",
        "프로시저변경요청승인", "사용자테스트", "이관전승인", "개발자", "이관자", "검토수행자", "모니터링결과",
    ]

    GREEN  = PatternFill("solid", fgColor="C6EFCE")
    YELLOW = PatternFill("solid", fgColor="FFEB9C")
    RED    = PatternFill("solid", fgColor="FFC7CE")
    FONT_GREEN  = Font(color="006100")
    FONT_YELLOW = Font(color="9C6500")
    FONT_RED    = Font(color="9C0006")

    status_col  = HEADERS.index("검증결과") + 1
    monitor_col = HEADERS.index("모니터링결과") + 1

    wb = Workbook()
    ws = wb.active
    ws.title = "DDL모니터링"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for l in logs:
        sr_info = sr_info_map.get(l.sr_no) if l.sr_no else None
        val_str = _compute_ui_status(l, sr_info)
        info    = sr_info or {}

        # 모니터링결과 텍스트
        if val_str == "정상":
            monitor = "특이사항 없음"
        elif val_str == "비정상":
            reason  = (l.ddl_reason or "").strip()
            monitor = reason if reason else "사유 입력이 필요합니다"
        else:
            monitor = "SR번호 없음"

        ws.append([
            l.query_summary or "",
            _req_str(l.request_time),
            l.conn_account or "",
            l.db_user or "",
            l.sr_no or "",
            info.get("sr_title", ""),
            info.get("work_type", ""),
            info.get("appr_date", ""),
            info.get("close_date", ""),
            val_str,
            l.proc_change_approval or "O",
            l.user_test or "O",
            l.pre_release_approval or "",
            l.developer or "",
            l.releaser or "이기헌",
            l.reviewer_name or "노광환",
            monitor,
        ])

        row_idx = ws.max_row
        # 검증결과 셀 색칠: 정상=초록, 비정상=노랑, 미적용=빨강
        _color_map = {
            "정상":  (GREEN,  FONT_GREEN),
            "비정상": (YELLOW, FONT_YELLOW),
            "미적용": (RED,    FONT_RED),
        }
        if val_str in _color_map:
            cell = ws.cell(row=row_idx, column=status_col)
            cell.fill, cell.font = _color_map[val_str]

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _empty_view(year_month: str, system_code: str) -> dict:
    return {
        "period": year_month, "system_code": system_code,
        "summary": {"total": 0, "applied": 0, "pending": 0,
                    "no_reason": 0, "progress_pct": 0},
        "logs": [],
    }
