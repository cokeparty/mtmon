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

    # ── HR(Tibero) (부서이동자 — 퇴사자·부서이동자·IHR/PMS/조달구매 권한 조회) ──
    #    조달구매·PMS 는 Tibero 의 DB 링크로 조회하므로 접속은 이것 하나뿐
    TIBERO_DSN: str = ""                 # host:port/DB이름  (예: 10.100.1.130:8629/DXHR)
    TIBERO_USER: str = ""
    TIBERO_PASSWORD: str = ""
    TIBERO_JDBC_JAR: str = "lib/tibero7-jdbc.jar"   # 상대경로면 프로젝트 루트 기준
    JAVA_HOME: str = ""                  # java 가 PATH 에 없을 때만 (JRE 8 이상)

    # ── 메일 (SMTP) — 부서이동자 일간 결과 메일 ─────────────
    SMTP_HOST: str = ""                  # 비우면 메일 배치가 '설정 없음'으로 실패 처리
    SMTP_PORT: int = 25
    SMTP_HELO: str = ""                  # EHLO 에 쓸 도메인 (예: kmdev.poscodx.com, 비우면 서버 이름)
    SMTP_STARTTLS: bool = False
    SMTP_SSL: bool = False               # 465 포트 SSL 접속일 때만 True
    SMTP_USER: str = ""                  # 인증이 필요할 때만
    SMTP_PASSWORD: str = ""
    MAIL_FROM: str = ""                  # 발신자 (예: pe912821@poscodx.com)
    DEPART_DAILY_MAIL_TO: str = ""       # 받는 사람 — 쉼표(,) 또는 세미콜론(;)으로 여러 명
    DEPART_DAILY_MAIL_CC: str = ""
    APP_BASE_URL: str = ""               # 메일의 '화면에서 보기' 링크 (예: http://서버:8000, 비우면 링크 없음)

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
