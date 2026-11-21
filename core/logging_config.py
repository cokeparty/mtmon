# core/logging_config.py
"""
애플리케이션 로깅 설정.

logs/ 폴더에 날짜별(자정 기준 일 단위 롤오버)로 3종 로그를 적재한다.
  logs/app/application.log      — 애플리케이션 로그 (INFO 이상)
  logs/access/access.log        — 접속 로그 (요청별, 사용자 IP 포함)
  logs/error/error.log          — 에러 로그 (ERROR 이상)

당일 로그는 베이스 파일(application.log 등)에 쌓이고, 자정에 직전 날짜 파일
(application-YYYY-MM-DD.log)로 롤오버된다. backupCount=0 → 자동 삭제하지 않음
(추후 다른 디스크로 옮길 예정이므로 보존).
"""
import logging
import logging.handlers
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def _resolve_level() -> int:
    """config.py 의 LOG_LEVEL 설정을 읽어 logging 상수로 변환."""
    try:
        from config import settings
        return getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    except Exception:
        return logging.INFO
LOG_DIR  = BASE_DIR / "logs"

ACCESS_LOGGER = "access"

_FMT = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_ACCESS_FMT = logging.Formatter(
    "%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_configured = False


def _dated_namer(default_name: str) -> str:
    """롤오버 파일명을 'name.log.2026-06-22' → 'name-2026-06-22.log' 형태로."""
    head, _, datepart = default_name.rpartition(".")
    if head.endswith(".log"):
        head = head[:-4]
    return f"{head}-{datepart}.log"


def _daily_handler(subdir: str, basename: str, level: int,
                   fmt: logging.Formatter) -> logging.Handler:
    d = LOG_DIR / subdir
    d.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.TimedRotatingFileHandler(
        filename=str(d / f"{basename}.log"),
        when="midnight", interval=1, backupCount=0, encoding="utf-8",
    )
    h.suffix = "%Y-%m-%d"
    h.namer  = _dated_namer
    h.setLevel(level)
    h.setFormatter(fmt)
    return h


def setup_logging() -> logging.Logger:
    """루트/접속 로거에 파일 핸들러를 1회 부착하고 access 로거를 반환."""
    global _configured
    if _configured:
        return logging.getLogger(ACCESS_LOGGER)

    LOG_DIR.mkdir(exist_ok=True)

    # 애플리케이션 + 에러 로그 → 루트 로거
    level = _resolve_level()
    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(_daily_handler("app",   "application", logging.INFO,  _FMT))
    root.addHandler(_daily_handler("error", "error",       logging.ERROR, _FMT))

    # 접속 로그 → 전용 로거 (루트로 전파하지 않아 app 로그와 중복 방지)
    access = logging.getLogger(ACCESS_LOGGER)
    access.setLevel(logging.INFO)
    access.addHandler(_daily_handler("access", "access", logging.INFO, _ACCESS_FMT))
    access.propagate = False

    _configured = True
    return access
