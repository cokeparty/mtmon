"""배치잡 — 앱(APScheduler) 안에서 실행. cron 사용 안 함.

  batch/jobs.py      잡 목록 (이름 · 일정 · 실행 함수) — 잡 추가/변경은 이 파일에서만
  batch/runner.py    실행기 — 실행 이력(common.batch_history) 기록, 에러 원인 보존
  batch/scheduler.py 스케줄러 — 앱 시작 시 잡 등록, 다중 워커 중복 실행 방지

수동 실행은 앱의 '배치관리' 화면에서만 한다 (명령줄 실행 기능은 두지 않는다).
"""
