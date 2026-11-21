import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ════════════════════════════════════════════════════
    # DB 설정
    # ════════════════════════════════════════════════════
    DATABASE_URL: str = "postgresql+psycopg2://monu:!0umon%40@203.238.192.134:5432/month_mon" # 모니터링 DB
    SR_DB_URL: str = "postgresql+psycopg2://ssru:!0ussr%40%40@203.238.192.37:5432/ehr"        # SR DB
    EMERGENCY_GRACE_DAYS: int = 5
    
    # ════════════════════════════════════════════════════
    # Oracle DB (부서이동자 — 퇴직자, 부서이동자, HR 조회용)
    # ════════════════════════════════════════════════════
    ORACLE_DSN:      str = "203.241.0.121:1521/PROD"   # host:port/service_name
    ORACLE_USER:     str = "apps"
    ORACLE_PASSWORD: str = "pos0411"
    ORACLE_CLIENT_LIB_DIR:  str = "C:\Program Files\instantclient-basic-windows.x64-23.26.2.0.0\instantclient_23_0" # 개발PC(Windows)

    # ORACLE_CLIENT_LIB_DIR: str = "/opt/oracle/instantclient_23_26"  배포서버 (Linux)

    # ════════════════════════════════════════════════════
    # BPM DB (부서이동자 — (HR)·EPRO·PMS 조회용)
    # ════════════════════════════════════════════════════
    BPM_ORACLE_DSN:     str = "203.238.192.182:5444/bpm"
    BPM_ORACLE_USER:    str = "edbu"
    BPM_ORACLE_PASSWORD: str = "pos0411"
    
    # ════════════════════════════════════════════════════
    # 로그 레벨 (INFO / DEBUG)
    #   INFO  : 수집 결과 요약, 에러만 기록 (기본)
    #   DEBUG : SSH 명령 전문, 파싱 샘플 등 상세 기록
    #   변경 방법: .env 파일에 LOG_LEVEL=DEBUG 추가 또는 이 값을 직접 수정
    # ════════════════════════════════════════════════════
    LOG_LEVEL: str = "INFO"



    # ════════════════════════════════════════════════════
    # 세션 쿠키 기간, 쿠키 서명/위변조 방지
    # ════════════════════════════════════════════════════
    SECRET_KEY: str = "96afbc678f7eda73cb8c95b39adcc36914ea7715b0863bba1deddbb228ff62d8"
    SESSION_MAX_AGE: int = 60*60*9 # 8시간

    # ════════════════════════════════════════════════════
    # 계정 초기 비밀번호 (계정 생성 및 비밀번호 초기화 시 사용)
    # ════════════════════════════════════════════════════
    INITIAL_PASSWORD: str = "Mtmon12#"

    # ════════════════════════════════════════════════════
    # 개발/임시 계정 (DB 없는 환경에서 사용, 비워두면 비활성화)
    # ════════════════════════════════════════════════════
    DEV_LOGIN_ID:   str = ""
    DEV_LOGIN_PW:   str = ""
    DEV_USER_NAME:  str = "임시관리자"
    DEV_USER_ROLE:  str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
