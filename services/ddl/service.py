# services/ddl/service.py
"""
DDL 모니터링 비즈니스 로직

담당자 = 개발자 (단일 역할) → 화면 1개
행 단위 SR 입력 (DML처럼 그룹 테이블 없음)
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models.ddl import DdlLog, DdlType
from models.dml import DmlStatus
from services.ddl import parser
from services.common import sr_validation as validation
from services.common import excel, sr
from services.common.fmt import fmt_date, fmt_datetime
from services.common.fmt import key_time
from services.common.period import get_or_create_period, get_period


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
    """CSV → ddl_log 재적재 (같은 회차·시스템의 기존 데이터를 교체).

    안전장치
      - 파일을 먼저 읽고 검사한다. 읽을 수 없거나 적재할 행이 없으면 기존 데이터는 그대로 둔다.
      - 같은 로그(요청시각·사용자·계정·오브젝트·쿼리 동일)에 이미 입력한 SR·사유·결재 칸은 새 행에 옮겨 담는다.
      - 삭제와 적재는 한 번에 처리하고, 중간에 실패하면 모두 되돌린다.
    """
    result = parser.parse(content)
    rows = result.rows
    if rows.empty:
        raise ValueError("적재할 DDL 로그가 없습니다. 기존 데이터는 그대로 두었습니다.")
    if rows["req_time"].isna().all():
        raise ValueError("요청 시각을 읽을 수 없습니다. 파일 형식을 확인하세요. 기존 데이터는 그대로 두었습니다.")

    try:
        period = get_or_create_period(db, year_month)
        old = db.query(DdlLog).filter_by(period_id=period.id, system_code=system_code).all()
        keep = {_ddl_key(l.request_time, l.db_user, l.conn_account, l.target_object, l.query_summary): l
                for l in old}

        db.query(DdlLog).filter_by(period_id=period.id, system_code=system_code).delete()

        kept = 0
        for _, row in rows.iterrows():
            req_time = row["req_time"] if not pd.isna(row["req_time"]) else None
            summary  = (row["command"] or "")[:500] or None
            sr_val   = row.get("sr_no") or None
            dl = DdlLog(
                period_id            = period.id,
                system_code          = system_code,
                request_time         = req_time,
                db_user              = row["user_name"],
                conn_account         = row["account"],
                target_object        = row["target_object"],
                ddl_type             = _safe_ddl_type(row.get("ddl_type")),
                query_summary        = summary,
                sr_no                = sr_val,
                status               = DmlStatus.적용됨 if sr_val else DmlStatus.미입력,
                proc_change_approval = "O",
                user_test            = "O",
                releaser             = "이기헌",
                reviewer_name        = "노광환",
            )
            prev = keep.get(_ddl_key(req_time, row["user_name"], row["account"], row["target_object"], summary))
            if prev is not None:
                for f in _DDL_USER_FIELDS:
                    setattr(dl, f, getattr(prev, f))
                if prev.sr_no:                      # 입력해 둔 SR 이 있으면 그것을 유지
                    dl.sr_no, dl.status = prev.sr_no, prev.status
                kept += 1
            db.add(dl)

        db.commit()
    except Exception:
        db.rollback()
        raise
    return {**result.stats, "period_id": period.id, "replaced": len(old), "kept_input": kept}


# 재업로드 시 그대로 옮겨 담는 사용자 입력 칸
_DDL_USER_FIELDS = ("ddl_reason", "proc_change_approval", "user_test",
                    "pre_release_approval", "developer", "releaser", "reviewer_name")


def _ddl_key(req_time, db_user, account, obj, summary) -> tuple:
    return (key_time(req_time), db_user or "", account or "", obj or "", summary or "")


# ──────────────────────────────────────────────────────────────
# 단일 뷰 조회
# ──────────────────────────────────────────────────────────────
def get_view(
    db: Session,
    year_month: str,
    system_code: str,
) -> dict:
    period = get_period(db, year_month)
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
    sr_map = sr.fetch_info_map(sr_nos)

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
    sr_info_map = sr.fetch_info_map([sr_no]) if sr_no else {}
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
    sr_map = sr.fetch_info_map([log.sr_no]) if log.sr_no else {}
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
    sr_map = sr.fetch_info_map([log.sr_no]) if log.sr_no else {}
    return _log_to_dict(log, sr_map.get(log.sr_no or ""))


# ──────────────────────────────────────────────────────────────
# Enrich (SR DB 조회 + 검증 통계 + 로그별 SR 정보)
# ──────────────────────────────────────────────────────────────
def run_enrich(db: Session, year_month: str, system_code: str) -> dict:
    period = get_period(db, year_month)
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
        sr_client = sr.client()
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
                    "appr_date":  fmt_date(row.get("appr_date")),
                    "close_date": fmt_date(row.get("close_date")),
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
EXCEL_HEADERS = [
    "명령어", "요청 시각", "접속계정", "사용자명",
    "SR번호", "SR제목", "작업구분", "작업승인일", "SR종료일", "검증결과",
    "프로시저변경요청승인", "사용자테스트", "이관전승인", "개발자", "이관자", "검토수행자", "모니터링결과",
]


def export_excel(db: Session, year_month: str, system_code: str) -> bytes:
    """DDL 로그 + SR 정보 + 검증결과(웹 화면과 같은 판정) → xlsx. 데이터가 없으면 빈 양식."""
    period = get_period(db, year_month)
    logs = [] if not period else (
        db.query(DdlLog).filter_by(period_id=period.id, system_code=system_code)
        .order_by(DdlLog.request_time).all())

    sr_info_map = sr.fetch_info_map(l.sr_no for l in logs)
    rows = []
    for l in logs:
        sr_info = sr_info_map.get(l.sr_no) if l.sr_no else None
        status  = _compute_ui_status(l, sr_info)
        info    = sr_info or {}
        if status == "정상":
            monitor = "특이사항 없음"
        elif status == "비정상":
            monitor = (l.ddl_reason or "").strip() or "사유 입력이 필요합니다"
        else:
            monitor = "SR번호 없음"
        rows.append([
            l.query_summary or "", fmt_datetime(l.request_time), l.conn_account or "", l.db_user or "",
            l.sr_no or "", info.get("sr_title", ""), info.get("work_type", ""),
            info.get("appr_date", ""), info.get("close_date", ""), status,
            l.proc_change_approval or "O", l.user_test or "O", l.pre_release_approval or "",
            l.developer or "", l.releaser or "이기헌", l.reviewer_name or "노광환", monitor,
        ])
    return excel.build("DDL모니터링", EXCEL_HEADERS, rows, status_col="검증결과")


def _empty_view(year_month: str, system_code: str) -> dict:
    return {
        "period": year_month, "system_code": system_code,
        "summary": {"total": 0, "applied": 0, "pending": 0,
                    "no_reason": 0, "progress_pct": 0},
        "logs": [],
    }
