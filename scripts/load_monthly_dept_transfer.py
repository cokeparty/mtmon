"""
scripts/load_monthly_dept_transfer.py
부서이동자 월간 자동 적재 배치

실행:
  python -m scripts.load_monthly_dept_transfer            # 이번 달(YYYY-MM)
  python -m scripts.load_monthly_dept_transfer 2026-05    # 특정 회차 지정

크론(매월 1일 08:10):
  10 8 1 * * /opt/mtmon/scripts/run_dept_monthly.sh
종료코드:
  0 — 전체 성공
  1 — 치명적 오류 (DB 연결 불가 등 전체 실패)
  2 — 부분 성공 (일부 시스템 수집 실패, 나머지는 처리됨)
"""
import logging
import re
import sys
from datetime import datetime

from db.database import get_session
from services.dept_transfer_service import run_monthly_collect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _resolve_ym(argv: list[str]) -> str:
    """CLI 인자에서 회차(YYYY-MM)를 결정. 없으면 이번 달."""
    if len(argv) >= 2 and argv[1].strip():
        ym = argv[1].strip()
        if not re.fullmatch(r"\d{4}-\d{2}", ym):
            logger.error("회차 형식 오류: '%s' (YYYY-MM 형식이어야 함)", ym)
            sys.exit(1)
        return ym
    return datetime.now().strftime("%Y-%m")


def main():
    start = datetime.now()
    ym = _resolve_ym(sys.argv)
    logger.info("부서이동자 월간 수집 시작 — 회차 %s", ym)

    try:
        with get_session() as db:
            result = run_monthly_collect(db, ym)
    except Exception as e:
        logger.exception("치명적 오류 — 수집 전체 실패: %s", e)
        sys.exit(1)

    logger.info("UPSERT 합계: %d건 / 회차: %s", result["upserted"], result["year_month"])

    has_error = False
    for task in result.get("tasks", []):
        if task["ok"]:
            logger.info("  ✓ %-6s %d건", task["code"], task["count"])
        else:
            logger.error("  ✗ %-6s 실패: %s", task["code"], task["error"])
            has_error = True

    elapsed = (datetime.now() - start).total_seconds()
    logger.info("소요시간: %.1f초", elapsed)

    if has_error:
        logger.warning("일부 시스템 수집 실패 — 부분 수집 완료 (종료코드 2)")
        sys.exit(2)


if __name__ == "__main__":
    main()
