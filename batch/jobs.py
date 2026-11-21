"""배치잡 목록.

각 잡 함수는 (db, params) 를 받아 JobResult 를 돌려준다.
  - 일부만 실패하면 status="partial" 과 실패 원인을 errors 에 담는다.
  - 전체 실패는 예외를 그대로 던진다 → runner 가 failed 로 기록하고 원인을 남긴다.
일정은 cron 식(분 시 일 월 요일)이다. 서버 시간대 기준.
"""
from dataclasses import dataclass, field
from typing import Callable

from sqlalchemy.orm import Session

from core.periods import prev_month_ym


@dataclass
class JobResult:
    status: str = "success"                 # success | partial
    summary: str = ""                       # 화면 · 이력에 보일 처리 결과 요약
    errors: list[str] = field(default_factory=list)   # 부분 실패 원인
    data: dict = field(default_factory=dict)          # 화면 버튼 응답용 원본 결과


@dataclass
class JobDef:
    job_id: str
    name: str
    description: str
    cron: str
    schedule_desc: str
    func: Callable[[Session, dict], JobResult]
    default_params: Callable[[], dict] = dict
    param_label: Callable[[dict], str] = lambda p: ""


# ──────────────────────────────────────────────────────────
# 잡 함수
# ──────────────────────────────────────────────────────────
PCL_SYSTEMS = ["HR", "EPRO", "SR", "PMS"]


def run_program_monthly(db: Session, params: dict) -> JobResult:
    """프로그램변경: FTP 로그 수집 → NFS 매핑 → SR DB 조회 → 판정 → 적재 (PCL_SYSTEMS 의 시스템별)."""
    from services.program import collector

    ym = params["year_month"]
    systems = params.get("systems") or PCL_SYSTEMS
    results, errors, parts = [], [], []
    for sc in systems:
        try:
            stats = collector.collect(db, sc, ym)
            db.commit()
            results.append({"ok": True, "system_code": sc, "stats": stats})
            parts.append(f"{sc} {stats.get('inserted', 0)}건")
        except PermissionError as e:          # 마감 회차
            db.rollback()
            results.append({"ok": False, "system_code": sc, "error": str(e), "closed": True})
            errors.append(f"{sc}: 마감 회차라 건너뜀 — {e}")
        except Exception as e:                # 한 시스템 실패로 전체를 멈추지 않음
            db.rollback()
            results.append({"ok": False, "system_code": sc, "error": str(e)})
            errors.append(f"{sc}: {type(e).__name__}: {e}")
    if len(errors) == len(systems):
        raise RuntimeError("모든 시스템 수집 실패\n" + "\n".join(errors))
    total = sum(int((r.get("stats") or {}).get("inserted", 0) or 0) for r in results)
    return JobResult(
        status="partial" if errors else "success",
        summary=f"회차 {ym} 적재 {total}건 ({', '.join(parts) or '-'})",
        errors=errors,
        data={"year_month": ym, "total_inserted": total,
              "partial_error": bool(errors), "results": results},
    )


def run_depart_daily(db: Session, params: dict) -> JobResult:
    """부서이동자 일간: Oracle·BPM 6개 쿼리 → depart.daily_record UPSERT."""
    from services.depart.collector import collect_daily

    result = collect_daily(db)
    tasks = result.get("tasks", [])
    errors = [f"{t['type']}: {t.get('error')}" for t in tasks if not t["ok"]]
    if tasks and len(errors) == len(tasks):
        raise RuntimeError("모든 조회 실패\n" + "\n".join(errors))
    ok = ", ".join(f"{t['type']} {t['count']}건" for t in tasks if t["ok"])
    return JobResult(
        status="partial" if errors else "success",
        summary=f"기준일 {result.get('date')} UPSERT {result.get('upserted', 0)}건 ({ok or '-'})",
        errors=errors,
        data=result,
    )


def run_depart_monthly(db: Session, params: dict) -> JobResult:
    """부서이동자 월간: 4개 쿼리 → depart.monthly_record 적재 + 일간 SR 자동 매핑."""
    from services.depart.service import run_monthly_collect

    ym = params["year_month"]
    result = run_monthly_collect(db, ym)
    db.commit()
    tasks = result.get("tasks", [])
    errors = [f"{t['code']}: {t.get('error')}" for t in tasks if not t.get("ok")]
    if tasks and len(errors) == len(tasks):
        raise RuntimeError("모든 시스템 수집 실패\n" + "\n".join(errors))
    ok = ", ".join(f"{t['code']} {t.get('count', 0)}건" for t in tasks if t.get("ok"))
    return JobResult(
        status="partial" if errors else "success",
        summary=f"회차 {ym} UPSERT {result.get('upserted', 0)}건 ({ok or '-'})",
        errors=errors,
        data=result,
    )


def run_log_cleanup(db: Session, params: dict) -> JobResult:
    """보관 기간이 지난 로그 파일 삭제 (기간은 .env LOG_RETENTION_DAYS_*)."""
    from core.logging_config import cleanup_old_logs

    removed = cleanup_old_logs()
    total = sum(removed.values())
    detail = ", ".join(f"{k} {v}" for k, v in removed.items() if v)
    return JobResult(summary=f"삭제 {total}개" + (f" ({detail})" if detail else ""), data=removed)


def _prev_month() -> dict:
    return {"year_month": prev_month_ym()}


def _ym_label(p: dict) -> str:
    return f"회차 {p['year_month']}" if p.get("year_month") else ""


# ──────────────────────────────────────────────────────────
# 잡 목록 — 여기만 고치면 화면 · 스케줄러 · DB 목록에 모두 반영됨
# ──────────────────────────────────────────────────────────
JOBS: list[JobDef] = [
    JobDef("program_monthly", "프로그램변경 월간 수집",
           "전월 회차의 이관 로그를 대상 시스템별로 수집해 SR 매핑·판정 후 적재",
           "10 3 1 * *", "매월 1일 03:10", run_program_monthly, _prev_month, _ym_label),
    JobDef("depart_daily", "부서이동자 일간 수집",
           "퇴직자·부서변경자와 시스템별 추가 권한을 조회해 일간 목록에 반영",
           "10 8 * * *", "매일 08:10", run_depart_daily),
    JobDef("depart_monthly", "부서이동자 월간 수집",
           "전월 회차의 부서이동자·권한 현황을 적재하고 일간 SR 입력값을 자동 매핑",
           "10 8 1 * *", "매월 1일 08:10", run_depart_monthly, _prev_month, _ym_label),
    JobDef("log_cleanup", "로그 정리",
           "보관 기간이 지난 로그 파일 삭제 (app 1개월 · access/audit 1년 · batch/error 6개월)",
           "30 0 * * *", "매일 00:30", run_log_cleanup),
]

JOB_MAP: dict[str, JobDef] = {j.job_id: j for j in JOBS}
