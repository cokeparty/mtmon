"""
scripts/load_daily_dept_transfer.py
부서이동자 일간 자동 적재 배치

실행: python -m scripts.load_daily_dept_transfer
크론: 10 8 * * *  cd /opt/mtmon && /opt/mtmon/venv/bin/python -m scripts.load_daily_dept_transfer >> /var/log/mtmon/dept_transfer_daily_log 2>&1

종료코드:
  0 — 전체 성공
  1 — 치명적 오류 (DB 연결 불가 등 전체 실패)
  2 — 부분 성공 (일부 태스크 실패, 나머지는 처리됨)
"""
import logging
import sys
from datetime import datetime

from db.database import get_session
from services.dept_transfer_collector import collect_daily

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    start = datetime.now()
    logger.info("부서이동자 일간 수집 시작")

    try:
        with get_session() as db:
            result = collect_daily(db)
    except Exception as e:
        logger.exception("치명적 오류 — 수집 전체 실패: %s", e)
        sys.exit(1)

    logger.info("UPSERT 합계: %d건 / 기준일: %s", result["upserted"], result["date"])

    has_error = False
    for task in result.get("tasks", []):
        if task["ok"]:
            logger.info("  ✓ %-12s %d건", task["type"], task["count"])
        else:
            logger.error("  ✗ %-12s 실패: %s", task["type"], task["error"])
            has_error = True

    elapsed = (datetime.now() - start).total_seconds()
    logger.info("소요시간: %.1f초", elapsed)

    if has_error:
        logger.warning("일부 태스크 실패 — 부분 수집 완료 (종료코드 2)")
        sys.exit(2)


if __name__ == "__main__":
    main()
