import enum
from sqlalchemy import (Column, BigInteger, SmallInteger, String, Date, Time,
                        TIMESTAMP, ForeignKey, UniqueConstraint, func)
from db.database import Base


class MapType(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(30)."""
    none             = "none"
    single           = "single"
    session_anchor   = "session_anchor"
    check            = "check"
    date_resolved    = "date_resolved"     # 파일명 충돌 → SR번호 내장 날짜로 자동선택
    time_resolved    = "time_resolved"     # deprecated
    reverse_resolved = "reverse_resolved"  # deprecated


class PclResult(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(20)."""
    정상   = "정상"
    SR없음 = "SR없음"
    경고   = "경고"
    이상   = "이상"


class PclNormalYn(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(10)."""
    정상 = "정상"
    이상 = "이상"


class ProgramChangeLog(Base):
    __tablename__  = "program_change_log"
    __table_args__ = (
        UniqueConstraint("period_id", "system_code", "deploy_time", "file_name",
                         name="uq_pcl_dedup"),
        {"schema": "program"},
    )

    id          = Column(BigInteger, primary_key=True)
    period_id   = Column(BigInteger,
                         ForeignKey("common.monitoring_period.id"),
                         nullable=False)
    system_code = Column(String(10), nullable=False)

    # ① xferlog 원본
    log_month   = Column(SmallInteger)
    log_day     = Column(SmallInteger)
    log_time    = Column(Time)
    deploy_time = Column(TIMESTAMP,   nullable=False)
    file_name   = Column(String(255), nullable=False)
    full_path   = Column(String(500))
    deployer    = Column(String(50))

    # ② NFS 매핑
    nfs_path  = Column(String(700))
    nfs_mtime = Column(TIMESTAMP)
    map_type  = Column(String(30), nullable=False, default="none")

    # ③ SR DB 스냅샷
    sr_no          = Column(String(30))
    sr_title       = Column(String(300))
    sr_work_type   = Column(String(50))
    # ★ 시간까지 보존(작업승인일/SR종료일). 화면·엑셀에서 시각 노출용.
    sr_approved_at = Column(TIMESTAMP)
    sr_closed_at   = Column(TIMESTAMP)
    sr_developer   = Column(String(50))
    sr_reviewer    = Column(String(50))

    # ④ 결재/담당 편집 컬럼 (화면에서 편집·저장, 빈 값이면 디폴트 적용)
    approval_change_request = Column(String(50))   # 프로그램 변경요청·승인 (디폴트 O)
    approval_user_test      = Column(String(50))   # 사용자테스트 (디폴트 O)
    approval_pre_deploy     = Column(String(50))   # 이관전 승인 (디폴트 O/X)
    transferer              = Column(String(50))   # 이관자 (디폴트 이기헌)

    # ⑤ 판정
    result    = Column(String(20), nullable=False, default="SR없음")
    normal_yn = Column(String(10), nullable=False, default="이상")
    reason    = Column(String(500))

    # ⑥ 운영
    remark     = Column(String(500))
    created_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
    updated_at = Column(TIMESTAMP, nullable=False,
                        server_default=func.now(), onupdate=func.now())
