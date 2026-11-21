# models/dml.py  —  schema: dml
import enum
from sqlalchemy import (Column, BigInteger, Integer, String, Text,
                        TIMESTAMP, Boolean, Index, ForeignKey, func, text)
from db.database import Base


class DmlStatus(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(10)."""
    미입력 = "미입력"
    적용됨 = "적용됨"


class DbUserDeveloperMap(Base):
    """db_user → 개발자 매핑 — DML 그룹 자동 분배용."""
    __tablename__  = "db_user_developer_map"
    __table_args__ = ({"schema": "dml"},)

    id           = Column(BigInteger, primary_key=True)
    system_code  = Column(String(10), nullable=False)
    db_user      = Column(String(50), nullable=False)
    developer_id = Column(BigInteger, nullable=False)


class DmlGroup(Base):
    """DML 그루핑 결과 — 개발자별 SR 입력 단위."""
    __tablename__  = "dml_group"
    __table_args__ = (
        Index("idx_dmlg_period_sys", "period_id", "system_code"),
        Index("idx_dmlg_developer",  "developer_id", "status"),
        Index("idx_dmlg_status",     "status"),
        Index("idx_dmlg_base_time",  "base_time"),
        {"schema": "dml"},
    )

    id           = Column(BigInteger, primary_key=True)
    period_id    = Column(BigInteger,
                          ForeignKey("program_change.monitoring_period.id"),
                          nullable=False)
    system_code  = Column(String(10),  nullable=False)
    base_time    = Column(TIMESTAMP,   nullable=False)
    db_user      = Column(String(50),  nullable=False)
    conn_account = Column(String(50),  nullable=False)
    target_table = Column(String(100), nullable=False)
    developer_id = Column(BigInteger)
    row_count    = Column(Integer, nullable=False, default=0)
    sr_no        = Column(String(30))
    status       = Column(String(10),  nullable=False, default="미입력")
    # DML여부 — 기본 True(DML). 개발자가 SR이 필요없는 비DML(예: DBSAFER 자체이력)로
    # 표시하면 False → 정상·적용완료로 처리.
    is_dml       = Column(Boolean, nullable=False, server_default=text("true"))
    # 비정상(SR 있으나 판정 이상) 행에 대한 개발자 소명 사유 — 비정상일 때만 사용. 최대 500자.
    dml_reason   = Column(String(500))
    created_at   = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at   = Column(TIMESTAMP, nullable=False,
                          server_default=func.now(), onupdate=func.now())


class DmlLog(Base):
    """DML 원본 로그 — DBSAFER CSV 적재."""
    __tablename__  = "dml_log"
    __table_args__ = (
        Index("idx_dml_period_sys", "period_id", "system_code"),
        Index("idx_dml_request",    "request_time"),
        Index("idx_dml_group",      "group_id"),
        Index("idx_dml_grp_keys",   "period_id", "system_code",
              "db_user", "conn_account", "target_table", "request_time"),
        {"schema": "dml"},
    )

    id            = Column(BigInteger, primary_key=True)
    period_id     = Column(BigInteger,
                           ForeignKey("program_change.monitoring_period.id"),
                           nullable=False)
    system_code   = Column(String(10),  nullable=False)
    request_time  = Column(TIMESTAMP,   nullable=False)
    db_user       = Column(String(50),  nullable=False)
    conn_account  = Column(String(50),  nullable=False)
    target_table  = Column(String(100), nullable=False)
    query_summary = Column(Text)
    group_id      = Column(BigInteger, ForeignKey("dml.dml_group.id"))
    sr_no         = Column(String(30))
    status        = Column(String(10), nullable=False, default="미입력")
    created_at    = Column(TIMESTAMP, nullable=False, server_default=func.now())
