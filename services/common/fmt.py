"""표시용 값 변환 — pandas NaN/NaT 와 None 을 모두 빈 문자열로 처리."""
import pandas as pd


def _empty(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


def safe_str(v) -> str:
    """None / NaN → "" (NaN 은 truthy 라 `or ""` 로는 걸러지지 않는다)."""
    if _empty(v):
        return ""
    s = str(v)
    return "" if s == "nan" else s


def fmt_date(v) -> str:
    """날짜/Timestamp → YYYY-MM-DD."""
    if _empty(v):
        return ""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    s = str(v)
    return s[:10] if len(s) >= 10 else s


def fmt_datetime(v) -> str:
    """날짜/Timestamp → YYYY-MM-DD HH:MM:SS."""
    if _empty(v):
        return ""
    return v.strftime("%Y-%m-%d %H:%M:%S") if hasattr(v, "strftime") else str(v)


def key_time(v):
    """비교용 시각 — pandas Timestamp · datetime 을 초 단위 datetime 으로 맞춘다 (None 은 그대로)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "to_pydatetime"):
        v = v.to_pydatetime()
    return v.replace(microsecond=0) if hasattr(v, "replace") else v
