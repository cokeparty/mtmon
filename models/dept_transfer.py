# models/dept_transfer.py  —  schema: dept_transfer
from sqlalchemy import (Column, BigInteger, String, Date,
                        TIMESTAMP, Index, UniqueConstraint, ForeignKey, func)
from db.database import Base


class DailyRecord(Base):
    """일간 부서이동자 조회 결과 — 7일 뷰 UPSERT."""
    __tablename__  = "daily_record"
    __table_args__ = (
        UniqueConstraint("record_type", "empno", "change_date", "role_key",
                         name="uq_daily_record"),
        Index("idx_daily_change_date", "change_date"),
        Index("idx_daily_empno",       "empno"),
        Index("idx_daily_action",      "action"),
        Index("idx_daily_rtype",       "record_type"),
        {"schema": "dept_transfer"},
    )

    id             = Column(BigInteger, primary_key=True)
    record_type    = Column(String(20),  nullable=False)   # 퇴직자|부서변경자|전자조달권한|PMS권한
    empno          = Column(String(20),  nullable=False)
    emp_name       = Column(String(50))
    change_date    = Column(Date,        nullable=False)
    dept_code      = Column(String(50))
    dept_name      = Column(String(100))
    prev_dept_code = Column(String(50))
    prev_dept_name = Column(String(100))
    role_code      = Column(String(50))
    role_key       = Column(String(50),  nullable=False, default="-")  # UPSERT key
    role_name      = Column(String(200))
    reg_date       = Column(Date)
    action         = Column(String(10))                    # 유지|회수|NULL
    sr_no          = Column(String(30))
    sr_title       = Column(String(300))
    sr_work_type   = Column(String(50))
    remark         = Column(String(500))
    processed_by   = Column(BigInteger)                    # auth.app_user.id
    processed_at   = Column(TIMESTAMP)
    first_seen     = Column(Date, nullable=False)
    last_seen      = Column(Date, nullable=False)
    created_at     = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at     = Column(TIMESTAMP, nullable=False,
                            server_default=func.now(), onupdate=func.now())


class MonthlyRecord(Base):
    """월간 부서이동자 모니터링 결과 — 월초 1회 적재."""
    __tablename__  = "monthly_record"
    __table_args__ = (
        UniqueConstraint("period_id", "system_code", "empno", "role_key",
                         name="uq_monthly_record"),
        Index("idx_monthly_period_sys", "period_id", "system_code"),
        Index("idx_monthly_empno",      "empno"),
        {"schema": "dept_transfer"},
    )

    id             = Column(BigInteger, primary_key=True)
    period_id      = Column(BigInteger,
                            ForeignKey("program_change.monitoring_period.id"),
                            nullable=False)
    system_code    = Column(String(20),  nullable=False)   # 공통|PMS|HR|EPRO
    empno          = Column(String(20),  nullable=False)
    emp_name       = Column(String(50))
    change_date    = Column(Date)
    dept_code      = Column(String(50))
    dept_name      = Column(String(100))
    prev_dept_code = Column(String(50))
    prev_dept_name = Column(String(100))
    role_code      = Column(String(50))
    role_key       = Column(String(50),  nullable=False, default="-")
    role_name      = Column(String(200))
    reg_date       = Column(Date)
    revoke_date    = Column(Date)                          # 권한회수일 reviewer 입력
    sr_no          = Column(String(30))
    sr_title       = Column(String(300))
    sr_work_type   = Column(String(50))
    remark         = Column(String(500))
    created_at     = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at     = Column(TIMESTAMP, nullable=False,
                            server_default=func.now(), onupdate=func.now())
