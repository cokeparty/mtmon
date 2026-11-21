# /opt/mtmon/scripts/run_dept_monthly.sh
#!/usr/bin/env bash
set -uo pipefail
cd /opt/mtmon

PREV_YM=$(date -d "$(date +%Y-%m-01) -1 day" +%Y%m)

PREV_YM_DASH=$(date -d "$(date +%Y-%m-01) -1 day" +%Y-%m)

LOG_DIR=/data/mtmon/logs/batch
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/dept_transfer_monthly-${PREV_YM}.log"

{
  echo "[START] $(date '+%F %T')  target=${PREV_YM}"
  /opt/mtmon/venv/bin/python -m scripts.load_monthly_dept_transfer "${PREV_YM_DASH}"
  rc=$?
  echo "[EXIT] rc=$rc"
} >> "$LOG" 2>&1
exit $rc
