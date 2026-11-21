"""APScheduler — 앱 프로세스 안에서 배치잡을 일정대로 실행.

  * 워커가 여러 개면 워커마다 스케줄러가 돌지만, 실행 직전 이력 테이블의
    (job_id, scheduled_at) 유일 제약으로 한 워커만 실제로 실행한다.
  * 앱이 꺼져 있던 동안 지나간 일정은 1시간 이내면 켜질 때 1번 실행한다(misfire_grace_time).
  * SCHEDULER_ENABLED=false 이면 자동 실행만 멈추고, 화면의 수동 실행은 그대로 된다.
"""
import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from batch.jobs import JOBS, JOB_MAP
from batch.runner import mark_interrupted, run_job
from config import settings
from db.database import SessionLocal
from models.common import BatchJob

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def sync_job_table() -> None:
    """코드의 잡 목록을 common.batch_job 에 반영 (코드에서 빠진 잡은 active=False)."""
    db = SessionLocal()
    try:
        rows = {r.job_id: r for r in db.query(BatchJob).all()}
        for j in JOBS:
            r = rows.get(j.job_id) or BatchJob(job_id=j.job_id)
            r.name, r.description = j.name, j.description
            r.schedule, r.schedule_desc, r.active = j.cron, j.schedule_desc, True
            r.updated_at = datetime.now()
            db.add(r)
        for job_id, r in rows.items():
            if job_id not in JOB_MAP and r.active:
                r.active = False
        db.commit()
    finally:
        db.close()


def _scheduled_run(job_id: str) -> None:
    # 예약 시각을 분 단위로 맞춰 워커 간 같은 값이 되도록 (중복 실행 방지 키)
    scheduled_at = datetime.now().replace(second=0, microsecond=0)
    run_job(job_id, trigger="schedule", scheduled_at=scheduled_at)


def start() -> None:
    global _scheduler
    sync_job_table()
    n = mark_interrupted()
    if n:
        logger.warning("중단된 배치 이력 %d건을 실패로 정리", n)
    if not settings.SCHEDULER_ENABLED:
        logger.info("배치 스케줄러 꺼짐 (SCHEDULER_ENABLED=false) — 수동 실행만 가능")
        return
    _scheduler = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1,
                                                   "misfire_grace_time": 3600})
    for j in JOBS:
        _scheduler.add_job(_scheduled_run, CronTrigger.from_crontab(j.cron),
                           args=[j.job_id], id=j.job_id, name=j.name)
    _scheduler.start()
    logger.info("배치 스케줄러 시작 — %s",
                ", ".join(f"{j.name}({j.schedule_desc})" for j in JOBS))


def shutdown() -> None:
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)


def next_run_times() -> dict[str, datetime | None]:
    if not _scheduler:
        return {}
    return {j.id: j.next_run_time for j in _scheduler.get_jobs()}


def is_running() -> bool:
    return bool(_scheduler and _scheduler.running)
