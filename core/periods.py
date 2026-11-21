# core/periods.py
"""회차(year_month) 계산 공용 헬퍼."""
from datetime import date, timedelta


def prev_month_ym(today: date | None = None) -> str:
    """월간 모니터링 기본 회차 = 전월("YYYY-MM").

    월간 모니터링은 당월이 아니라 전월을 대상으로 하므로, 각 화면의 기본 조회 회차로 사용한다.
    """
    d = today or date.today()
    first_of_this_month = d.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return last_of_prev_month.strftime("%Y-%m")
