# models/common.py  —  schema: common (모듈 공통: 회차 · 수집 서버 설정 · 배치)
import enum
from sqlalchemy import (Column, BigInteger, Integer, String, Text, Boolean,
                        TIMESTAMP, Index, func)
from db.database import Base


class PeriodStatus(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(10)."""
    open   = "open"
    closed = "closed"


class SystemCode(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(10)."""
    HR   = "HR"
    EPRO = "EPRO"
    SR   = "SR"
    PMS  = "PMS"


class MonitoringPeriod(Base):
    """월 회차 — 모든 모듈이 period_id 로 참조."""
    __tablename__  = "monitoring_period"
    __table_args__ = {"schema": "common"}

    id         = Column(BigInteger, primary_key=True)
    year_month = Column(String(7),  nullable=False, unique=True)   # 'YYYY-MM'
    status     = Column(String(10), nullable=False, default="open")
    closed_at  = Column(TIMESTAMP)
    closed_by  = Column(String(50))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())


class ServerConfig(Base):
    """시스템별 로그 수집(A서버 xferlog) · NFS(B서버) 접속 설정."""
    __tablename__  = "server_config"
    __table_args__ = {"schema": "common"}

    id           = Column(BigInteger, primary_key=True)
    system_code  = Column(String(10), nullable=False, unique=True)

    # A 서버 (xferlog)
    ssh_host     = Column(String(100), nullable=False)
    ssh_port     = Column(Integer,     nullable=False, default=22)
    ssh_user     = Column(String(50),  nullable=False)
    ssh_key_path = Column(String(300))
    ssh_password = Column(String(200))
    log_dir      = Column(String(300), nullable=False)
    log_pattern  = Column(String(100), nullable=False)
    include_path = Column(String(300), nullable=False)
    include_flag = Column(String(50),  nullable=False)

    # B 서버 (NFS)
    nfs_ssh_host     = Column(String(100))
    nfs_ssh_port     = Column(Integer, default=22)
    nfs_ssh_user     = Column(String(50))
    nfs_ssh_key_path = Column(String(300))
    nfs_ssh_password = Column(String(200))
    nfs_base_dir     = Column(String(300))

    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())


class BatchJob(Base):
    """배치잡 목록 — 코드(batch/jobs.py)에 정의된 잡을 앱 시작 시 동기화. 화면에서 생성·변경 안 함."""
    __tablename__  = "batch_job"
    __table_args__ = {"schema": "common"}

    job_id      = Column(String(50),  primary_key=True)
    name        = Column(String(100), nullable=False)
    description = Column(String(500))
    schedule    = Column(String(50),  nullable=False)   # cron 식 (분 시 일 월 요일)
    schedule_desc = Column(String(100))                 # 사람이 읽는 설명 (예: 매월 1일 03:10)
    active      = Column(Boolean, nullable=False, default=True)   # 코드에서 빠진 잡은 False
    updated_at  = Column(TIMESTAMP, nullable=False, server_default=func.now())


class BatchHistory(Base):
    """배치잡 실행 이력 — 1회 실행 = 1행. 실패 시 에러 원인과 트레이스백 보존."""
    __tablename__  = "batch_history"
    __table_args__ = (
        Index("idx_bh_job_started", "job_id", "started_at"),
        # 다중 워커가 같은 예약 시각에 동시에 깨어나도 1개만 실행되도록 (수동 실행은 scheduled_at=NULL)
        Index("uq_bh_job_scheduled", "job_id", "scheduled_at", unique=True,
              postgresql_where="scheduled_at IS NOT NULL"),
        {"schema": "common"},
    )

    id            = Column(BigInteger, primary_key=True)
    job_id        = Column(String(50), nullable=False)
    trigger_type  = Column(String(10), nullable=False)    # schedule | manual
    triggered_by  = Column(String(50))                    # 수동 실행자 이름
    params        = Column(String(200))                   # 예: 회차 2026-10
    scheduled_at  = Column(TIMESTAMP)                     # 예약 실행 시각 (수동은 NULL)
    started_at    = Column(TIMESTAMP, nullable=False, server_default=func.now())
    finished_at   = Column(TIMESTAMP)
    status        = Column(String(10), nullable=False, default="running")  # running|success|partial|failed
    summary       = Column(String(1000))                  # 처리 결과 요약 (건수 등)
    error_type    = Column(String(100))                   # 예외 종류 (예: OperationalError)
    error_message = Column(Text)                          # 에러 원인 (사람이 읽는 메시지)
    error_detail  = Column(Text)                          # 트레이스백 전문
    host          = Column(String(100))                   # 실행 서버:프로세스
