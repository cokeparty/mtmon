"""배치 실행기 — 잡 1회 실행 = 실행 이력 1행.

  * 시작 시 이력에 running 행을 만들고, 끝나면 success / partial / failed 로 갱신한다.
  * 실패하면 예외 종류 · 원인 메시지 · 트레이스백 전문을 이력에 남긴다.
  * 예약 실행은 (job_id, scheduled_at) 유일 제약으로 다중 워커 중 1개만 실행된다.
  * 실행 중 나온 모든 로그는 logs/batch/batch-날짜.log 에도 [잡id] 와 함께 남는다.
"""
import logging
import os
import socket
import traceback
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError

from batch.jobs import JOB_MAP, JobResult
from core.logging_config import current_job
from core.periods import is_valid_ym
from db.database import SessionLocal
from models.common import BatchHistory

logger = logging.getLogger(__name__)

_HOST = f"{socket.gethostname()}:{os.getpid()}"
STALE_AFTER = timedelta(hours=6)   # 이보다 오래 running 인 행은 서버 중단으로 끊긴 것으로 본다


class JobAlreadyRunning(Exception):
    pass


def _open_history(job_id, trigger, by, params_text, scheduled_at) -> int | None:
    """running 행 생성. 같은 예약 시각을 다른 워커가 이미 잡았으면 None."""
    db = SessionLocal()
    try:
        if trigger == "manual":
            running = (db.query(BatchHistory)
                       .filter(BatchHistory.job_id == job_id,
                               BatchHistory.status == "running",
                               BatchHistory.started_at > datetime.now() - STALE_AFTER)
                       .first())
            if running:
                raise JobAlreadyRunning(
                    f"이미 실행 중입니다 (시작 {running.started_at:%Y-%m-%d %H:%M:%S})")
        h = BatchHistory(job_id=job_id, trigger_type=trigger, triggered_by=by,
                         params=params_text or None, scheduled_at=scheduled_at,
                         started_at=datetime.now(), status="running", host=_HOST)
        db.add(h)
        db.commit()
        return h.id
    except IntegrityError:
        db.rollback()
        return None
    finally:
        db.close()


def _close_history(hid: int, **values) -> None:
    db = SessionLocal()
    try:
        db.query(BatchHistory).filter(BatchHistory.id == hid).update(
            {**values, "finished_at": datetime.now()})
        db.commit()
    finally:
        db.close()


def run_job(job_id: str, trigger: str = "manual", by: str | None = None,
            params: dict | None = None, scheduled_at: datetime | None = None) -> dict:
    """잡 실행. 반환: {"history_id", "status", "summary", "error", "data"}.

    예약 실행이 다른 워커와 겹치면 status="skipped".
    수동 실행인데 같은 잡이 실행 중이면 JobAlreadyRunning.
    """
    job = JOB_MAP[job_id]
    p = {**job.default_params(), **{k: v for k, v in (params or {}).items() if v}}
    if "year_month" in p and not is_valid_ym(p["year_month"]):
        raise ValueError(f"회차 형식이 올바르지 않습니다: {p['year_month']} (예: 2026-10)")
    label = job.param_label(p)

    hid = _open_history(job_id, trigger, by, label, scheduled_at)
    if hid is None:
        return {"history_id": None, "status": "skipped", "summary": "다른 워커가 실행",
                "error": None, "data": {}}

    token = current_job.set(job_id)
    logger.info("배치 시작 — %s (%s) %s 실행자=%s", job.name, trigger, label, by or "스케줄러")
    start = datetime.now()
    db = SessionLocal()
    try:
        res: JobResult = job.func(db, p)
        db.commit()
        err = "\n".join(res.errors) or None
        _close_history(hid, status=res.status, summary=res.summary[:1000],
                       error_message=err, error_type="부분 실패" if err else None)
        log = logger.warning if res.status == "partial" else logger.info
        log("배치 종료 — %s %s (%.1f초) %s%s", job.name, res.status,
            (datetime.now() - start).total_seconds(), res.summary,
            f"\n실패 내역:\n{err}" if err else "")
        return {"history_id": hid, "status": res.status, "summary": res.summary,
                "error": err, "data": res.data}
    except Exception as e:
        db.rollback()
        logger.exception("배치 실패 — %s: %s", job.name, e)
        _close_history(hid, status="failed", summary=None,
                       error_type=type(e).__name__[:100],
                       error_message=str(e) or type(e).__name__,
                       error_detail=traceback.format_exc())
        return {"history_id": hid, "status": "failed", "summary": "",
                "error": f"{type(e).__name__}: {e}", "data": {}}
    finally:
        db.close()
        current_job.reset(token)


def mark_interrupted() -> int:
    """서버가 꺼지면서 running 으로 남은 오래된 행을 failed 로 정리 (앱 시작 시)."""
    db = SessionLocal()
    try:
        n = (db.query(BatchHistory)
             .filter(BatchHistory.status == "running",
                     BatchHistory.started_at < datetime.now() - STALE_AFTER)
             .update({"status": "failed", "finished_at": datetime.now(),
                      "error_type": "Interrupted",
                      "error_message": "서버 재시작 등으로 실행이 중단되었습니다."}))
        db.commit()
        return n
    finally:
        db.close()
