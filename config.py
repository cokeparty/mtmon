"""
앱 설정 — 값은 모두 프로젝트 루트의 .env 파일에서 읽는다.

  * 이 파일에는 항목 이름과 설명만 두고, 서버마다 다른 값(접속 정보·비밀번호)은
    .env 에만 적는다. 소스 배포 시 .env 는 덮어쓰지 않는다.
  * 새 서버를 세팅할 때는 .env.example 을 .env 로 복사해서 값을 채운다.
  * 기본값이 없는 항목(= ...)이 .env 에 없으면 앱이 시작되지 않는다.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ── 실행 환경 ─────────────────────────────────────────
    APP_ENV: str = "dev"                 # dev | prod  (화면 상단 표시·로그 구분용)
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # ── 모니터링 DB (PostgreSQL) ──────────────────────────
    DATABASE_URL: str                    # postgresql+psycopg2://user:pass@host:5432/mtmon
    AUTO_MIGRATE: bool = True            # 앱 시작 시 DB 구조 변경(마이그레이션) 자동 적용

    # ── SR DB (PostgreSQL) ────────────────────────────────
    SR_DB_URL: str = ""
    EMERGENCY_GRACE_DAYS: int = 5        # 긴급변경 사후승인 허용 일수

    # ── Oracle (부서이동자 — 퇴직자·부서이동자·HR 조회) ───
    ORACLE_DSN: str = ""                 # host:port/service_name
    ORACLE_USER: str = ""
    ORACLE_PASSWORD: str = ""
    ORACLE_CLIENT_LIB_DIR: str = ""      # Instant Client 경로 (비우면 thin 모드)

    # ── BPM DB (부서이동자 — HR·EPRO·PMS 권한 조회) ──────
    BPM_ORACLE_DSN: str = ""             # host:port/dbname
    BPM_ORACLE_USER: str = ""
    BPM_ORACLE_PASSWORD: str = ""

    # ── 로그 ──────────────────────────────────────────────
    LOG_DIR: str = "logs"                # 상대경로면 프로젝트 루트 기준
    LOG_LEVEL: str = "INFO"              # INFO | DEBUG
    LOG_RETENTION_DAYS_APP: int = 31     # 보관 기간(일) — 지난 파일은 매일 새벽 정리 배치가 삭제
    LOG_RETENTION_DAYS_ACCESS: int = 365
    LOG_RETENTION_DAYS_AUDIT: int = 365
    LOG_RETENTION_DAYS_BATCH: int = 183
    LOG_RETENTION_DAYS_ERROR: int = 183

    # ── 배치 스케줄러 ────────────────────────────────────
    SCHEDULER_ENABLED: bool = True       # False 면 자동 실행만 멈춤(화면의 수동 실행은 가능)

    # ── 세션 / 보안 ──────────────────────────────────────
    SECRET_KEY: str                      # 세션 쿠키 서명 키 (서버마다 다른 긴 임의 문자열)
    SESSION_MAX_AGE: int = 60 * 60 * 8   # 초 (기본 8시간)
    HTTPS_ONLY: bool = False             # HTTPS 운영 시 True

    # ── 계정 ──────────────────────────────────────────────
    INITIAL_PASSWORD: str = ""           # 계정 생성·비밀번호 초기화 시 부여하는 값

    # ── 개발/임시 계정 (DB 없는 환경 전용, 운영은 비워둘 것) ──
    DEV_LOGIN_ID: str = ""
    DEV_LOGIN_PW: str = ""
    DEV_USER_NAME: str = "임시관리자"
    DEV_USER_ROLE: str = ""


settings = Settings()
