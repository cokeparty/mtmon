# core/periods.py
"""회차(year_month) 관련 공통 함수."""
import re
from datetime import date, timedelta

_YM_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def prev_month_ym(today: date | None = None) -> str:
    """월간 모니터링 기본 회차 = 전월("YYYY-MM").

    월간 모니터링은 당월이 아니라 전월을 대상으로 하므로, 각 화면의 기본 조회 회차도 전월이다.
    """
    d = today or date.today()
    first_of_this_month = d.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return last_of_prev_month.strftime("%Y-%m")


def is_valid_ym(ym: str | None) -> bool:
    """'YYYY-MM' 형식이고 실제로 있는 달인지 (2026-13 → False)."""
    return bool(ym) and bool(_YM_RE.match(ym))
