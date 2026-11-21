# models/ddl.py  —  schema: ddl
import enum
from sqlalchemy import (Column, BigInteger, String, Text, Boolean,
                        TIMESTAMP, Index, ForeignKey, func)
from db.database import Base


class DdlType(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(10)."""
    CREATE   = "CREATE"
    ALTER    = "ALTER"
    DROP     = "DROP"
    TRUNCATE = "TRUNCATE"
    RENAME   = "RENAME"


class DdlLog(Base):
    """DDL 원본 로그 — DBSAFER CSV 적재 + SR 입력."""
    __tablename__  = "ddl_log"
    __table_args__ = (
        Index("idx_ddl_period_sys", "period_id", "system_code"),
        Index("idx_ddl_request",    "request_time"),
        Index("idx_ddl_type",       "ddl_type"),
        Index("idx_ddl_abnormal",   "is_abnormal"),
        Index("idx_ddl_status",     "status"),
        Index("idx_ddl_sr",         "sr_no"),
        {"schema": "ddl"},
    )

    id            = Column(BigInteger, primary_key=True)
    period_id     = Column(BigInteger,
                           ForeignKey("program_change.monitoring_period.id"),
                           nullable=False)
    system_code   = Column(String(10),  nullable=False)
    request_time  = Column(TIMESTAMP,   nullable=False)
    db_user       = Column(String(50),  nullable=False)
    conn_account  = Column(String(50),  nullable=False)
    target_object = Column(String(150), nullable=False)
    ddl_type      = Column(String(10),  nullable=False)
    query_summary = Column(Text)
    is_abnormal   = Column(Boolean, nullable=False, default=False)
    sr_no         = Column(String(30))
    status        = Column(String(10), nullable=False, default="미입력")
    created_at    = Column(TIMESTAMP, nullable=False, server_default=func.now())

    # 사유 / 6개 편집 칼럼
    ddl_reason            = Column(String(500))
    proc_change_approval  = Column(String(10),  default="O")
    user_test             = Column(String(10),  default="O")
    pre_release_approval  = Column(String(10))
    developer             = Column(String(100))
    releaser              = Column(String(100), default="이기헌")
    reviewer_name         = Column(String(100), default="노광환")
