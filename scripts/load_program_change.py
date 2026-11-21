"""
============================================================
 scripts/load_program_change.py
------------------------------------------------------------
 프로그램 변경 - 월초 배치 적재 스크립트 (크론 실행)

 동작:
   1) 인자 없으면 '전월' 회차 자동 산정 (YYYY-MM)
   2) 4개 시스템(HR/EPRO/SR/PMS) 순회
   3) collect_orchestrator.collect() 재사용
      (SFTP 로그 수집 → NFS 스캔 → SR 매핑 → SR DB → 판정 → 적재)
   4) 시스템별 통계 로그 출력, 실패는 건너뛰고 계속

 사용:
   python -m scripts.load_program_change            # 전월 자동
   python -m scripts.load_program_change 2026-01    # 특정 회차
   python -m scripts.load_program_change 2026-01 HR # 특정 회차+시스템

 크론(매월 1일 03:10):
   10 3 1 * * cd /opt/mtmon && /opt/mtmon/venv/bin/python -m scripts.load_program_change >> /var/log/mtmon/pcl_batch.log 2>&1
============================================================
"""
import sys
import logging
from datetime import date

from dateutil.relativedelta import relativedelta

from db.database import SessionLocal
from config import settings
from services import collect_orchestrator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("pcl_batch")

SYSTEMS = ["HR", "EPRO", "SR", "PMS"]


def prev_month_ym() -> str:
    """오늘 기준 전월을 'YYYY-MM' 으로."""
    d = date.today().replace(day=1) - relativedelta(months=1)
    return d.strftime("%Y-%m")


def parse_args(argv: list[str]) -> tuple[str, list[str]]:
    """argv → (year_month, systems)"""
    ym = argv[1] if len(argv) >= 2 else prev_month_ym()
    if len(ym) != 7 or ym[4] != "-":
        raise SystemExit(f"회차 형식 오류(YYYY-MM): {ym}")
    systems = [argv[2]] if len(argv) >= 3 else SYSTEMS
    for s in systems:
        if s not in SYSTEMS:
            raise SystemExit(f"알 수 없는 시스템: {s}")
    return ym, systems


def run(year_month: str, systems: list[str]) -> int:
    """적재 실행. 반환값 = 실패한 시스템 수(종료코드용)."""
    fail = 0
    db = SessionLocal()
    try:
        for sys_code in systems:
            try:
                stats = collect_orchestrator.collect(
                    db, sys_code, year_month, settings.SR_DB_URL
                )
                log.info(
                    "[%s/%s] parsed=%s inserted=%s dup=%s "
                    "none=%s conflict=%s abnormal=%s normal=%s",
                    year_month, sys_code,
                    stats.get("parsed_lines"), stats.get("inserted"),
                    stats.get("skipped_dup"), stats.get("count_none"),
                    stats.get("count_conflict"), stats.get("count_abnormal"),
                    stats.get("count_normal"),
                )
            except PermissionError as e:
                # 마감(closed) 회차 → 적재 불가. 배치에서는 경고만.
                fail += 1
                log.warning("[%s/%s] 마감 회차 - 건너뜀: %s", year_month, sys_code, e)
            except Exception as e:  # noqa: BLE001  (배치는 한 시스템 실패에 전체 중단 금지)
                fail += 1
                log.exception("[%s/%s] 적재 실패: %s", year_month, sys_code, e)
        db.commit()
    finally:
        db.close()
    return fail


def main():
    ym, systems = parse_args(sys.argv)
    log.info("프로그램 변경 배치 시작: 회차=%s, 대상=%s", ym, systems)
    fail = run(ym, systems)
    log.info("배치 종료: 실패 %d개", fail)
    sys.exit(1 if fail else 0)   # 실패 있으면 비정상 종료(모니터링 감지용)


if __name__ == "__main__":
    main()
