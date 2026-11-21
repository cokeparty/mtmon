# services/dml/service.py
"""
DML 모니터링 비즈니스 로직

담당자 뷰: CSV 업로드, 그룹 조회, 검증(enrich), 진행률 집계
개발자 뷰: 본인 그룹 조회, SR 적용/취소
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from models.dml import DbUserDeveloperMap, DmlGroup, DmlLog, DmlStatus
from services.dml import parser
from services.common import sr_validation as validation
from services.common import excel, sr
from services.common.fmt import fmt_date, fmt_datetime, key_time, safe_str
from services.common.period import get_or_create_period, get_period


# ──────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────
def _compute_ui_status(g: DmlGroup, sr_info: dict | None) -> str:
    """3단계 UI 표시 상태: 미적용 / 비정상 / 정상"""
    # 비DML(개발자가 SR 불필요로 표시) → SR 없이도 정상·적용완료로 간주
    if not g.is_dml:
        return "정상"

    if not g.sr_no:
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
        g.base_time, _parse(appr_date), _parse(close_date), work_type
    )
    return "정상" if result == "정상" else "비정상"


def _group_to_dict(g: DmlGroup, sr_info: dict | None = None) -> dict[str, Any]:
    info = sr_info or {}
    return {
        "group_id":     g.id,
        "system":       g.system_code,
        "db_user":      g.db_user,
        "conn_account": g.conn_account,
        "target_table": g.target_table,
        "row_count":    g.row_count,
        "base_time":    g.base_time.strftime("%Y-%m-%d %H:%M:%S") if g.base_time else "",
        "developer_id": g.developer_id,
        "sr_no":        g.sr_no or "",
        "status":       g.status,
        "is_dml":       g.is_dml,
        "reason":       g.dml_reason or "",
        "ui_status":    _compute_ui_status(g, sr_info),
        "sr_title":     info.get("sr_title") or "",
        "work_type":    info.get("work_type") or "",
        "appr_date":    info.get("appr_date") or "",
        "close_date":   info.get("close_date") or "",
    }


# ──────────────────────────────────────────────────────────────
# CSV 업로드 & 적재
# ──────────────────────────────────────────────────────────────
def import_csv(
    content: bytes,
    year_month: str,
    db: Session,
) -> dict:
    """
    DBSAFER CSV → parse → dml_log + dml_group 적재.
    접속계정에서 업무명(system_code)을 자동 결정하며,
    같은 period + system_code 의 기존 데이터는 교체한다.

    안전장치
      - 파일을 먼저 읽고 검사한다. 적재할 행이 없으면 기존 데이터는 그대로 둔다.
      - 같은 그룹(시각·사용자·계정·테이블 동일)에 이미 입력한 SR·DML여부·사유는 새 그룹에 옮겨 담는다.
      - 삭제와 적재는 한 번에 처리하고, 중간에 실패하면 모두 되돌린다.
    """
    result = parser.parse(content)

    import numpy as np
    groups_df = result.groups.replace({np.nan: None})
    rows_df   = result.rows.replace({np.nan: None})

    if groups_df.empty:
        raise ValueError("적재할 DML 로그가 없습니다 (업무명에 해당하는 접속계정 없음). "
                         "기존 데이터는 그대로 두었습니다.")

    try:
        period = get_or_create_period(db, year_month)

        # CSV에 존재하는 업무명 목록
        system_codes: list[str] = groups_df["system_code"].dropna().unique().tolist()

        # 기존 그룹의 사용자 입력값 보관 → 같은 그룹이면 다시 채운다
        keep: dict[tuple, DmlGroup] = {}
        replaced = 0
        for g in (db.query(DmlGroup)
                  .filter(DmlGroup.period_id == period.id, DmlGroup.system_code.in_(system_codes))
                  .all()):
            keep[_group_key(g.system_code, g.base_time, g.db_user, g.conn_account, g.target_table)] = g
            replaced += 1
        kept_vals = {k: (g.sr_no, g.status, g.is_dml, g.dml_reason) for k, g in keep.items()}

        # 업무명별 기존 데이터 삭제 (재업로드 지원)
        for sc in system_codes:
            existing_gids = (
                db.query(DmlGroup.id)
                .filter_by(period_id=period.id, system_code=sc)
                .subquery()
            )
            db.query(DmlLog).filter(DmlLog.group_id.in_(existing_gids)).delete(
                synchronize_session=False
            )
            db.query(DmlGroup).filter_by(period_id=period.id, system_code=sc).delete(
                synchronize_session=False
            )

        # 업무명별 db_user → developer_id 매핑 로드
        dev_maps: dict[str, dict[str, int]] = {}
        for sc in system_codes:
            dev_maps[sc] = {
                row.db_user: row.developer_id
                for row in db.query(DbUserDeveloperMap).filter_by(system_code=sc).all()
            }

        # DmlGroup 삽입 (parser group_id → DB PK 매핑)
        gid_map: dict[int, int] = {}
        group_sr: dict[int, str] = {}           # 입력값을 되살린 그룹의 SR → 소속 로그에도 적용
        kept = 0
        for _, grp in groups_df.iterrows():
            sc           = grp["system_code"]
            db_user      = grp["user_name"]
            developer_id = dev_maps.get(sc, {}).get(db_user)
            sr_val       = grp["sr_no"] if grp["sr_no"] else None
            base_time    = grp["time_from"] if not pd.isna(grp["time_from"]) else None
            dg = DmlGroup(
                period_id    = period.id,
                system_code  = sc,
                base_time    = base_time,
                db_user      = db_user,
                conn_account = grp["account"],
                target_table = grp["table_name"],
                developer_id = developer_id,
                row_count    = int(grp["row_count"]),
                sr_no        = sr_val,
                status       = DmlStatus.적용됨 if sr_val else DmlStatus.미입력,
            )
            prev = kept_vals.get(_group_key(sc, base_time, db_user, grp["account"], grp["table_name"]))
            if prev is not None:
                p_sr, p_status, p_is_dml, p_reason = prev
                dg.is_dml, dg.dml_reason = p_is_dml, p_reason
                if p_sr:
                    dg.sr_no, dg.status = p_sr, p_status
                kept += 1
            db.add(dg)
            db.flush()
            gid_map[int(grp["group_id"])] = dg.id
            if prev is not None and prev[0]:
                group_sr[dg.id] = prev[0]

        # DmlLog 삽입
        for _, row in rows_df.iterrows():
            sc          = row.get("system_code", "")
            parser_gid  = row.get("group_id")
            db_group_id = gid_map.get(int(parser_gid)) if parser_gid is not None else None
            sr_val      = group_sr.get(db_group_id) or row.get("sr_no") or None
            dl = DmlLog(
                period_id     = period.id,
                system_code   = sc,
                request_time  = row["req_time"] if not pd.isna(row["req_time"]) else None,
                db_user       = row["user_name"],
                conn_account  = row["account"],
                target_table  = row["table_name"],
                query_summary = (row["command"] or "")[:500] or None,
                group_id      = db_group_id,
                sr_no         = sr_val,
                status        = DmlStatus.적용됨 if sr_val else DmlStatus.미입력,
            )
            db.add(dl)

        db.commit()
    except Exception:
        db.rollback()
        raise
    return {**result.stats, "period_id": period.id, "replaced": replaced, "kept_input": kept}


def _group_key(system_code, base_time, db_user, account, table) -> tuple:
    return (system_code or "", key_time(base_time), db_user or "", account or "", table or "")


# ──────────────────────────────────────────────────────────────
# 담당자 뷰 조회
# ──────────────────────────────────────────────────────────────
def get_manager_view(
    db: Session,
    year_month: str,
    system_code: str,
) -> dict:
    period = get_period(db, year_month)
    if not period:
        return {
            "period": year_month, "system_code": system_code,
            "last_uploaded_at": "",
            "summary": {"total_groups": 0, "applied_groups": 0,
                        "no_reason_groups": 0, "pending_groups": 0, "progress_pct": 0},
            "developers": [], "groups": [],
        }

    groups = (
        db.query(DmlGroup)
        .filter_by(period_id=period.id, system_code=system_code)
        .order_by(DmlGroup.base_time)
        .all()
    )

    total = len(groups)

    # SR DB 일괄 조회
    sr_nos = list({g.sr_no for g in groups if g.sr_no})
    sr_info_map = sr.fetch_info_map(sr_nos)

    # ui_status 기반 KPI + 개발자별 집계 (단일 순회)
    pending   = 0  # 미적용: SR 없음 or SR DB 미조회
    no_reason = 0  # 사유미입력: 비정상 + 소명 없음
    dev_stats: dict[str, dict] = {}
    for g in groups:
        ui_st = _compute_ui_status(g, sr_info_map.get(g.sr_no or ""))
        if g.is_dml:
            if ui_st == "미적용":
                pending += 1
            elif ui_st == "비정상" and not g.dml_reason:
                no_reason += 1
        name = g.db_user or "미배정"
        if name not in dev_stats:
            dev_stats[name] = {"developer_name": name, "total": 0, "done": 0}
        dev_stats[name]["total"] += 1
        is_done = (not g.is_dml) or (ui_st == "정상") or (ui_st == "비정상" and bool(g.dml_reason))
        if is_done:
            dev_stats[name]["done"] += 1
    for s in dev_stats.values():
        s["pct"] = round(s["done"] / s["total"] * 100) if s["total"] else 0

    applied = total - pending - no_reason
    pct     = round(applied / total * 100) if total else 0

    from sqlalchemy import func as sqlfunc
    last_uploaded_at_raw = (
        db.query(sqlfunc.max(DmlGroup.created_at))
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
            "total_groups":     total,
            "applied_groups":   applied,
            "no_reason_groups": no_reason,
            "pending_groups":   pending,
            "progress_pct":     pct,
        },
        "developers": list(dev_stats.values()),
        "groups": [
            _group_to_dict(g, sr_info_map.get(g.sr_no or ""))
            for g in groups
        ],
    }


# ──────────────────────────────────────────────────────────────
# 개발자 뷰 조회
# ──────────────────────────────────────────────────────────────
def get_developer_view(
    db: Session,
    year_month: str,
    developer_name: str,
) -> dict:
    period = get_period(db, year_month)
    if not period:
        return {
            "period": year_month,
            "summary": {"total": 0, "applied": 0, "no_reason": 0, "pending": 0, "progress_pct": 0},
            "groups": [],
        }

    groups = (
        db.query(DmlGroup)
        .filter_by(period_id=period.id, db_user=developer_name)
        .order_by(DmlGroup.base_time)
        .all()
    )

    total  = len(groups)
    sr_nos = list({g.sr_no for g in groups if g.sr_no})
    sr_map = sr.fetch_info_map(sr_nos)

    # ui_status 기반 KPI 집계 (상태 칼럼 기준)
    pending   = 0  # 미적용
    no_reason = 0  # 사유미입력 (비정상 + 소명 없음)
    for g in groups:
        ui_st = _compute_ui_status(g, sr_map.get(g.sr_no or ""))
        if g.is_dml:
            if ui_st == "미적용":
                pending += 1
            elif ui_st == "비정상" and not g.dml_reason:
                no_reason += 1
    applied = total - pending - no_reason

    return {
        "period": year_month,
        "summary": {
            "total":        total,
            "applied":      applied,
            "no_reason":    no_reason,
            "pending":      pending,
            "progress_pct": round(applied / total * 100) if total else 0,
        },
        "groups": [_group_to_dict(g, sr_map.get(g.sr_no or "")) for g in groups],
    }


def developer_choices(db: Session, year_month: str) -> dict:
    """개발자 화면 '개발자 선택' 목록.

    in_log : 이 회차 DML 로그에 나온 사용자명 (CSV 의 사용자명)
    others : 활성 계정 중 이 회차 로그에 없는 사람 (선택하면 빈 목록)
    """
    from models.account import AppUser
    period = get_period(db, year_month)
    in_log: list[str] = []
    if period:
        in_log = sorted({n for (n,) in db.query(DmlGroup.db_user)
                         .filter(DmlGroup.period_id == period.id).distinct() if n})
    names = {u.name for u in db.query(AppUser).filter(AppUser.active.is_(True)).all() if u.name}
    return {"in_log": in_log, "others": sorted(names - set(in_log))}


# ──────────────────────────────────────────────────────────────
# 그룹 상세 로그 조회
# ──────────────────────────────────────────────────────────────
def get_group_logs(group_id: int, db: Session) -> list[dict]:
    """그룹에 속한 DmlLog 행 목록 반환 (개발자 상세 보기용)."""
    logs = (
        db.query(DmlLog)
        .filter_by(group_id=group_id)
        .order_by(DmlLog.request_time)
        .all()
    )
    return [
        {
            "log_id":        l.id,
            "request_time":  l.request_time.strftime("%Y-%m-%d %H:%M:%S") if l.request_time else "",
            "db_user":       l.db_user or "",
            "target_table":  l.target_table or "",
            "query_summary": l.query_summary or "",
            "sr_no":         l.sr_no or "",
            "status":        l.status,
        }
        for l in logs
    ]


# ──────────────────────────────────────────────────────────────
# SR 적용 / 취소
# ──────────────────────────────────────────────────────────────
def apply_sr(group_id: int, sr_no: str, db: Session) -> dict:
    """그룹 + 소속 로그 행 전체에 SR번호 적용."""
    group = db.query(DmlGroup).filter_by(id=group_id).first()
    if not group:
        raise ValueError(f"그룹 {group_id} 없음")

    group.sr_no  = sr_no
    group.status = DmlStatus.적용됨
    db.query(DmlLog).filter_by(group_id=group_id).update(
        {"sr_no": sr_no, "status": DmlStatus.적용됨}
    )
    db.commit()
    sr_info_map = sr.fetch_info_map([sr_no]) if sr_no else {}
    sr_info  = sr_info_map.get(sr_no)
    sr_found = sr_no in sr_info_map  # SR DB에 해당 번호가 실제로 존재하는지
    return _group_to_dict(group, sr_info), sr_found


def set_dml(group_id: int, is_dml: bool, db: Session) -> dict:
    """그룹의 DML여부 설정.

    is_dml=False(비DML) 이면 SR이 없어도 정상·적용완료로 처리된다.
    SR 입력값(sr_no)은 건드리지 않으며, 다시 DML로 되돌리면 SR 기준으로 재판정된다.
    """
    group = db.query(DmlGroup).filter_by(id=group_id).first()
    if not group:
        raise ValueError(f"그룹 {group_id} 없음")

    group.is_dml = is_dml
    db.commit()

    sr_info_map = sr.fetch_info_map([group.sr_no]) if group.sr_no else {}
    return _group_to_dict(group, sr_info_map.get(group.sr_no or ""))


def set_reason(group_id: int, reason: str, db: Session) -> dict:
    """그룹의 비정상 소명 사유 저장 (최대 500자, 비정상 행 전용)."""
    group = db.query(DmlGroup).filter_by(id=group_id).first()
    if not group:
        raise ValueError(f"그룹 {group_id} 없음")

    group.dml_reason = (reason or "").strip()[:500] or None
    db.commit()

    sr_info_map = sr.fetch_info_map([group.sr_no]) if group.sr_no else {}
    return _group_to_dict(group, sr_info_map.get(group.sr_no or ""))


def bulk_apply_sr(
    group_ids: list[int],
    sr_no: str,
    skip_existing: bool,
    db: Session,
) -> dict:
    """순번 범위 일괄 SR 적용.

    비DML(is_dml=False) 그룹은 항상 건너뜀.
    skip_existing=True 이면 이미 SR이 있는 그룹도 건너뜀.
    """
    sr_info_map = sr.fetch_info_map([sr_no]) if sr_no else {}
    sr_info  = sr_info_map.get(sr_no)
    sr_found = sr_no in sr_info_map

    applied_groups: list[DmlGroup] = []
    skipped_ids:    list[int]      = []

    for gid in group_ids:
        group = db.query(DmlGroup).filter_by(id=gid).first()
        if not group:
            continue
        if not group.is_dml:
            skipped_ids.append(gid)
            continue
        if skip_existing and group.sr_no:
            skipped_ids.append(gid)
            continue
        group.sr_no  = sr_no
        group.status = DmlStatus.적용됨
        db.query(DmlLog).filter_by(group_id=gid).update(
            {"sr_no": sr_no, "status": DmlStatus.적용됨}
        )
        applied_groups.append(group)

    db.commit()

    return {
        "applied":     [_group_to_dict(g, sr_info) for g in applied_groups],
        "skipped_ids": skipped_ids,
        "sr_found":    sr_found,
    }


def clear_sr(group_id: int, db: Session) -> dict:
    """그룹 + 소속 로그 행 전체에서 SR번호 제거."""
    group = db.query(DmlGroup).filter_by(id=group_id).first()
    if not group:
        raise ValueError(f"그룹 {group_id} 없음")

    group.sr_no  = None
    group.status = DmlStatus.미입력
    db.query(DmlLog).filter_by(group_id=group_id).update(
        {"sr_no": None, "status": DmlStatus.미입력}
    )
    db.commit()
    return _group_to_dict(group)


# ──────────────────────────────────────────────────────────────
# Enrich (SR DB 조회 + 검증 통계)
# ──────────────────────────────────────────────────────────────
def run_enrich(db: Session, year_month: str, system_code: str) -> dict:
    """
    SR DB에서 내용 조회 후 검증 통계 + 그룹별 SR 정보 반환.
    결과는 DB에 저장하지 않고 통계만 응답 (엑셀 출력 시 재계산).
    """
    period = get_period(db, year_month)
    if not period:
        return {"ok": False, "message": "해당 회차 없음"}

    logs = (
        db.query(DmlLog)
        .filter_by(period_id=period.id, system_code=system_code)
        .all()
    )
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

    ok_cnt = int((enriched.get("validation", pd.Series()) == "정상").sum())
    ng_cnt = int((enriched.get("validation", pd.Series()) == "비정상").sum())
    na_cnt = int(enriched.get("validation", pd.Series(dtype=object)).isna().sum())

    # enriched df에서 sr_no별 SR 정보 추출
    sr_info_by_no: dict[str, dict] = {}
    if "sr_title" in enriched.columns:
        valid_mask = (
            enriched["sr_no"].notna()
            & (enriched["sr_no"].astype(str).str.strip() != "")
            & enriched["sr_title"].notna()  # SR DB에 실제로 존재하는 행만 포함
        )
        for _, row in enriched[valid_mask].drop_duplicates("sr_no").iterrows():
            no = str(row["sr_no"]).strip()
            if no:
                sr_info_by_no[no] = {
                    "sr_title":  safe_str(row.get("sr_title")),
                    "work_type": safe_str(row.get("work_type")),
                    "appr_date": fmt_date(row.get("appr_date")),
                    "close_date": fmt_date(row.get("close_date")),
                }

    # 그룹별 SR 정보 매핑 (JS에서 테이블 셀 업데이트용)
    groups = (
        db.query(DmlGroup)
        .filter_by(period_id=period.id, system_code=system_code)
        .all()
    )
    group_sr: dict[str, dict] = {}
    for g in groups:
        if g.sr_no and g.sr_no in sr_info_by_no:
            group_sr[str(g.id)] = sr_info_by_no[g.sr_no]

    return {
        "ok": True,
        "stats":    {"정상": ok_cnt, "비정상": ng_cnt, "판정불가": na_cnt},
        "group_sr": group_sr,
    }


EXCEL_HEADERS = [
    "명령어", "요청 시각", "접속계정", "사용자명",
    "SR번호", "SR제목", "작업구분", "작업승인일", "SR종료일", "검증결과", "모니터링결과",
]
NON_DML_MSG = "DML이 아님"


def export_excel(db: Session, year_month: str, system_code: str) -> bytes:
    """DML 로그 + SR 정보 + 검증결과(웹 화면과 같은 판정) → xlsx. 데이터가 없으면 빈 양식."""
    period = get_period(db, year_month)
    if not period:
        return excel.build("DML모니터링", EXCEL_HEADERS, [], status_col="검증결과")
    logs = (db.query(DmlLog).filter_by(period_id=period.id, system_code=system_code)
            .order_by(DmlLog.request_time).all())
    groups = db.query(DmlGroup).filter_by(period_id=period.id, system_code=system_code).all()
    grp_by_id = {g.id: g for g in groups}
    sr_info_map = sr.fetch_info_map(g.sr_no for g in groups)

    rows = []
    for l in logs:
        g = grp_by_id.get(l.group_id)
        base = [l.query_summary or "", fmt_datetime(l.request_time), l.conn_account or "", l.db_user or ""]
        if g is not None and not g.is_dml:
            rows.append(base + [NON_DML_MSG] * 5 + ["정상", NON_DML_MSG])
            continue
        sr_info = sr_info_map.get(g.sr_no) if (g is not None and g.sr_no) else None
        status  = _compute_ui_status(g, sr_info) if g is not None else "미적용"
        info    = sr_info or {}
        if status == "정상":
            monitor = "특이사항 없음"
        elif status == "비정상":
            monitor = (safe_str(g.dml_reason) if g is not None else "") or "사유 입력이 필요합니다"
        else:
            monitor = "SR번호 없음"
        rows.append(base + [
            (g.sr_no if g is not None else "") or "", info.get("sr_title", ""), info.get("work_type", ""),
            info.get("appr_date", ""), info.get("close_date", ""), status, monitor,
        ])
    return excel.build("DML모니터링", EXCEL_HEADERS, rows, status_col="검증결과")


