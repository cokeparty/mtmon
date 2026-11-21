"""회차(monitoring_period) 조회 · 생성 — 모든 모듈이 이 함수만 사용한다."""
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from models.common import MonitoringPeriod, PeriodStatus


def get_period(db: Session, year_month: str) -> MonitoringPeriod | None:
    return db.query(MonitoringPeriod).filter_by(year_month=year_month).first()


def get_or_create_period(db: Session, year_month: str) -> MonitoringPeriod:
    """회차가 없으면 만든다(상태 open). commit 은 호출한 쪽에서.

    여러 작업(배치 · 화면 업로드)이 같은 회차를 동시에 만들어도 실패하지 않도록
    ON CONFLICT DO NOTHING 으로 만들고, 누가 만들었든 다시 조회해서 쓴다.
    """
    period = get_period(db, year_month)
    if period:
        return period
    db.execute(
        insert(MonitoringPeriod)
        .values(year_month=year_month, status=PeriodStatus.open)
        .on_conflict_do_nothing(index_elements=[MonitoringPeriod.year_month])
    )
    return db.query(MonitoringPeriod).filter_by(year_month=year_month).one()


def is_closed(period: MonitoringPeriod | None) -> bool:
    return period is not None and period.status == PeriodStatus.closed
