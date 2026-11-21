"""
로깅 설정 — 모든 로그 파일은 여기서만 정의한다.

  {LOG_DIR}/app/application-YYYY-MM-DD.log  앱 동작 (INFO 이상, 모든 모듈)
  {LOG_DIR}/error/error-YYYY-MM-DD.log      에러만 (ERROR 이상, 트레이스백 포함)
  {LOG_DIR}/access/access-YYYY-MM-DD.log    모든 요청 (IP · 경로 · 상태 · 소요시간 · 사용자)
  {LOG_DIR}/audit/audit-YYYY-MM-DD.log      사용자 작업 (SR 입력 · 업로드 · 계정 변경 · 엑셀 다운로드 등)
  {LOG_DIR}/batch/batch-YYYY-MM-DD.log      배치 실행 중 발생한 모든 로그 (잡 이름 표시)

  * 파일명에 날짜를 넣어 바로 쓰고, 자정에 파일을 이름 바꾸지 않는다.
    → uvicorn 워커가 여러 개여도 서로 파일을 덮어쓰거나 잃어버리지 않는다.
    (기존 TimedRotatingFileHandler 는 워커마다 자정 롤오버를 해서 로그가 사라졌음)
  * 보관 기간이 지난 파일은 '로그 정리' 배치(batch/jobs.py)가 매일 삭제한다.

사용법 — 각 모듈에서는 이것만 쓴다:
    import logging
    logger = logging.getLogger(__name__)
"""
import contextvars
import logging
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from config import settings

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = Path(settings.LOG_DIR)
if not LOG_DIR.is_absolute():
    LOG_DIR = BASE_DIR / LOG_DIR

ACCESS_LOGGER = "access"
AUDIT_LOGGER  = "audit"

# 지금 실행 중인 배치잡 id — 배치 스레드 안에서만 값이 있다 (batch/runner.py 가 설정)
current_job: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_job", default=None)

_FMT = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
_MSG_FMT = logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S")
_BATCH_FMT = logging.Formatter("%(asctime)s [%(levelname)s] [%(job)s] %(name)s: %(message)s",
                               "%Y-%m-%d %H:%M:%S")

# 외부 라이브러리 중 INFO 가 너무 많은 것 (파일 변경 감지 · SSH 세부 · 스케줄러 내부)
_QUIET = ("watchfiles", "watchfiles.main", "paramiko", "paramiko.transport",
          "apscheduler", "alembic.runtime.migration", "httpx", "multipart")

_configured = False


class DailyFileHandler(logging.Handler):
    """{dir}/{name}-YYYY-MM-DD.log 에 바로 append. 날짜가 바뀌면 새 파일을 연다."""

    def __init__(self, subdir: str, name: str, level: int, fmt: logging.Formatter):
        super().__init__(level)
        self.dir = LOG_DIR / subdir
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name_prefix = name
        self.setFormatter(fmt)
        self._day: str | None = None
        self._fp = None

    def _stream(self):
        today = date.today().isoformat()
        if today != self._day:
            if self._fp:
                self._fp.close()
            self._fp = open(self.dir / f"{self.name_prefix}-{today}.log", "a", encoding="utf-8")
            self._day = today
        return self._fp

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self.lock:
                fp = self._stream()
                fp.write(msg + "\n")
                fp.flush()
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        with self.lock:
            if self._fp:
                self._fp.close()
                self._fp = None
        super().close()


class _BatchOnly(logging.Filter):
    """배치 스레드에서 나온 로그만 통과시키고, 잡 id 를 레코드에 붙인다."""

    def filter(self, record: logging.LogRecord) -> bool:
        job = current_job.get()
        if not job:
            return False
        record.job = job
        return True


def setup_logging() -> None:
    """앱 시작 시 1회 호출 (main.py, 배치 CLI)."""
    global _configured
    if _configured:
        return
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(DailyFileHandler("app",   "application", level,         _FMT))
    root.addHandler(DailyFileHandler("error", "error",       logging.ERROR, _FMT))
    batch = DailyFileHandler("batch", "batch", level, _BATCH_FMT)
    batch.addFilter(_BatchOnly())
    root.addHandler(batch)

    # 접속 · 감사 로그는 전용 파일에만 (app 로그와 중복 방지)
    for name, sub in ((ACCESS_LOGGER, "access"), (AUDIT_LOGGER, "audit")):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.addHandler(DailyFileHandler(sub, sub, logging.INFO, _MSG_FMT))
        lg.propagate = False

    for name in _QUIET:
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True


# ──────────────────────────────────────────────────────────
# 보관 기간 지난 로그 삭제 (배치 '로그 정리'에서 호출)
# ──────────────────────────────────────────────────────────
_DATED = re.compile(r"-(\d{4}-\d{2}-\d{2})\.log$")


def cleanup_old_logs() -> dict:
    retention = {
        "app":    settings.LOG_RETENTION_DAYS_APP,
        "access": settings.LOG_RETENTION_DAYS_ACCESS,
        "audit":  settings.LOG_RETENTION_DAYS_AUDIT,
        "batch":  settings.LOG_RETENTION_DAYS_BATCH,
        "error":  settings.LOG_RETENTION_DAYS_ERROR,
    }
    today = date.today()
    removed: dict[str, int] = {}
    for sub, days in retention.items():
        d = LOG_DIR / sub
        if not d.is_dir():
            continue
        limit = today - timedelta(days=days)
        n = 0
        for f in d.glob("*.log"):
            m = _DATED.search(f.name)
            if not m:
                continue
            try:
                if datetime.strptime(m.group(1), "%Y-%m-%d").date() < limit:
                    f.unlink()
                    n += 1
            except (ValueError, OSError):
                continue
        removed[sub] = n
    return removed


def elapsed_ms(start: float) -> float:
    return (time.perf_counter() - start) * 1000
