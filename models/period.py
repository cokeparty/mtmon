import enum
from sqlalchemy import Column, BigInteger, String, TIMESTAMP, func
from db.database import Base


class PeriodStatus(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(10)."""
    open   = "open"
    closed = "closed"


class MonitoringPeriod(Base):
    __tablename__  = "monitoring_period"
    __table_args__ = {"schema": "program_change"}

    id         = Column(BigInteger, primary_key=True)
    year_month = Column(String(7),  nullable=False, unique=True)   # 'YYYY-MM'
    status     = Column(String(10), nullable=False, default="open")
    closed_at  = Column(TIMESTAMP)
    closed_by  = Column(String(50))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
