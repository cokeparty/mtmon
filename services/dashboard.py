# services/dashboard.py
"""
통합 대시보드 집계 로직.

프로그램변경 · 부서이동자 · DML · DDL 4개 모니터링의 KPI/상태를 한 화면용으로 모은다.
기존 서비스(get_manager_view / get_view / get_monthly_summary)와
program.view.row_ui_status 를 그대로 재사용하며, 모니터링별로 OperationalError를
독립적으로 처리해 일부 DB 장애가 전체 화면을 막지 않도록 한다.

엑셀 출력 등은 대시보드 범위 밖(조회 전용).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from models.common import MonitoringPeriod
from models.program import ProgramChangeLog
import services.dml.service as dml_service
import services.ddl.service as ddl_service
import services.depart.service as dt_service
from services.program.view import is_user_reason, row_ui_status as pc_ui_status

SYSTEMS = ["HR", "EPRO", "SR", "PMS"]

# 3색 상태 팔레트 (도넛/막대 공용)
STATUS_COLORS = {"정상": "#2f7d5b", "비정상": "#c58a1a", "미적용": "#c2412d"}


def _empty_module() -> dict[str, Any]:
    return {
        "total": 0,
        "progress": 0,
        "status": {"정상": 0, "비정상": 0, "미적용": 0},
        "by_system": {s: 0 for s in SYSTEMS},
        "no_reason": 0,          # 비정상인데 사유를 아직 안 쓴 건 (조치 필요)
        "done": 0,               # 처리 완료 = 정상 + 사유를 입력한 비정상
    }


def _fmt_time(v) -> str:
    if not v:
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return str(v)[:19]


# ──────────────────────────────────────────────────────────────
# 모니터링별 집계
# ──────────────────────────────────────────────────────────────
def _pc_summary(db: Session, ym: str) -> dict:
    out = _empty_module()
    try:
        period = db.query(MonitoringPeriod).filter_by(year_month=ym).first()
        if not period:
            return out
        ok_count = 0
        for s in SYSTEMS:
            rows = (
                db.query(ProgramChangeLog)
                .filter_by(period_id=period.id, system_code=s)
                .all()
            )
            out["by_system"][s] = len(rows)
            for r in rows:
                st = pc_ui_status(r)
                out["status"][st] = out["status"].get(st, 0) + 1
                out["total"] += 1
                if st == "정상":
                    ok_count += 1
                elif st == "비정상":
                    if is_user_reason(r.reason):
                        ok_count += 1
                    else:
                        out["no_reason"] += 1
        # 진행률 = (정상 + 비정상(사유 작성)) / 전체
        out["done"] = ok_count
        out["progress"] = round(ok_count / out["total"] * 100) if out["total"] else 0
    except OperationalError:
        pass
    return out


def _dml_summary(db: Session, ym: str) -> dict:
    out = _empty_module()
    try:
        ok_count = 0
        for s in SYSTEMS:
            data = dml_service.get_manager_view(db, ym, s)
            groups = data.get("groups", [])
            out["by_system"][s] = len(groups)
            out["total"] += len(groups)
            for g in groups:
                st = g.get("ui_status", "미적용")
                out["status"][st] = out["status"].get(st, 0) + 1
                if st == "정상":
                    ok_count += 1
                elif st == "비정상":
                    if g.get("reason"):
                        ok_count += 1
                    else:
                        out["no_reason"] += 1
        # 진행률 = (정상 + 비정상(사유 작성)) / 전체
        out["done"] = ok_count
        out["progress"] = round(ok_count / out["total"] * 100) if out["total"] else 0
    except OperationalError:
        pass
    return out


def _ddl_summary(db: Session, ym: str) -> dict:
    out = _empty_module()
    try:
        ok_count = 0
        for s in SYSTEMS:
            data = ddl_service.get_view(db, ym, s)
            logs = data.get("logs", [])
            out["by_system"][s] = len(logs)
            out["total"] += len(logs)
            for l in logs:
                st = l.get("ui_status", "미적용")
                out["status"][st] = out["status"].get(st, 0) + 1
                if st == "정상":
                    ok_count += 1
                elif st == "비정상":
                    if l.get("ddl_reason"):
                        ok_count += 1
                    else:
                        out["no_reason"] += 1
        # 진행률 = (정상 + 비정상(사유 작성)) / 전체
        out["done"] = ok_count
        out["progress"] = round(ok_count / out["total"] * 100) if out["total"] else 0
    except OperationalError:
        pass
    return out


def _dt_summary(db: Session, ym: str) -> dict:
    """부서이동자: 권한(HR/PMS/EPRO) 기준 total·미적용·진행률."""
    out = {
        "total": 0, "pending": 0, "applied": 0, "progress": 0, "done": 0, "no_reason": 0,
        "by_system": {s: 0 for s in SYSTEMS},
        "status": {"정상": 0, "비정상": 0, "미적용": 0},
    }
    try:
        kpi = dt_service.get_monthly_summary(db, ym)
        # 부서이동자 시스템 코드(EPRO=전자조달) → 대시보드 공통 코드 매핑
        for sc in ("HR", "PMS", "EPRO"):
            cell = kpi.get(sc, {})
            out["total"] += cell.get("total", 0)
            out["pending"] += cell.get("pending", 0)
            if sc in out["by_system"]:
                out["by_system"][sc] = cell.get("total", 0)
        out["applied"] = out["done"] = out["total"] - out["pending"]
        out["progress"] = kpi.get("progress", 0)
        out["status"]["정상"] = out["applied"]
        out["status"]["미적용"] = out["pending"]
    except OperationalError:
        pass
    return out


# ──────────────────────────────────────────────────────────────
# 도넛(conic-gradient) 문자열 생성
# ──────────────────────────────────────────────────────────────
def _conic_gradient(dist: dict) -> str:
    total = sum(dist.values())
    if not total:
        return "#eef0f3 0deg 360deg"
    parts, acc = [], 0.0
    for k in ("정상", "비정상", "미적용"):
        frac = dist[k] / total * 360
        parts.append(f"{STATUS_COLORS[k]} {acc:.1f}deg {acc + frac:.1f}deg")
        acc += frac
    return ", ".join(parts)


# ──────────────────────────────────────────────────────────────
# 메인 진입점
# ──────────────────────────────────────────────────────────────
def get_dashboard_data(db: Session, year_month: str) -> dict:
    pc  = _pc_summary(db, year_month)
    dml = _dml_summary(db, year_month)
    ddl = _ddl_summary(db, year_month)
    dt  = _dt_summary(db, year_month)

    # 통합 상태 분포 (PC·부서이동자·DML·DDL 합산)
    status_dist = {"정상": 0, "비정상": 0, "미적용": 0}
    for m in (pc, dt, dml, ddl):
        for k in status_dist:
            status_dist[k] += m["status"][k]
    sd_total = sum(status_dist.values())
    # 전체 처리율도 모니터링별과 같은 기준: (정상 + 사유를 입력한 비정상) / 전체
    done_total = sum(m["done"] for m in (pc, dt, dml, ddl))
    no_reason_total = sum(m["no_reason"] for m in (pc, dt, dml, ddl))
    status_pct = {
        k: (round(v / sd_total * 100) if sd_total else 0)
        for k, v in status_dist.items()
    }

    # 시스템별 현황
    by_system = []
    for s in SYSTEMS:
        by_system.append({
            "name": s,
            "program_change": pc["by_system"][s],
            "dept_transfer":  dt["by_system"][s],
            "dml": dml["by_system"][s],
            "ddl": ddl["by_system"][s],
        })
    by_system_max = max(
        [r["program_change"] + r["dept_transfer"] + r["dml"] + r["ddl"]
         for r in by_system] + [1]
    )

    return {
        "period": year_month,
        "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "kpi": {
            "program_change": {
                "total": pc["total"],
                "normal": pc["status"]["정상"],
                "abnormal": pc["status"]["비정상"],
                "pending": pc["status"]["미적용"],
                "no_reason": pc["no_reason"],
                "progress": pc["progress"],
            },
            "dept_transfer": {
                "total": dt["total"], "pending": dt["pending"],
                "applied": dt["applied"], "progress": dt["progress"],
            },
            "dml": {
                "total": dml["total"],
                "normal": dml["status"]["정상"],
                "pending": dml["status"]["미적용"],
                "abnormal": dml["status"]["비정상"],
                "no_reason": dml["no_reason"],
                "progress": dml["progress"],
            },
            "ddl": {
                "total": ddl["total"],
                "normal": ddl["status"]["정상"],
                "abnormal": ddl["status"]["비정상"],
                "pending": ddl["status"]["미적용"],
                "no_reason": ddl["no_reason"],
                "progress": ddl["progress"],
            },
        },
        "status_dist": status_dist,
        "status_pct": status_pct,
        "status_total": sd_total,
        "done_total": done_total,
        "no_reason_total": no_reason_total,
        "donut_gradient": _conic_gradient(status_dist),
        "by_system": by_system,
        "by_system_max": by_system_max,
    }
