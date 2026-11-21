# schemas/dept_transfer.py
from typing import Optional
from pydantic import BaseModel


class DailyActionRequest(BaseModel):
    """reviewer 전용 — 일간 유지/회수 처리."""
    record_id: int
    action:    str                  # 유지 | 회수
    sr_no:     Optional[str] = None
    remark:    Optional[str] = None


class DailySrRequest(BaseModel):
    """operator·reviewer 공통 — 일간 SR 입력."""
    record_id: int
    sr_no:     str
    remark:    Optional[str] = None


class MonthlySrRequest(BaseModel):
    """operator·reviewer 공통 — 월간 SR 입력."""
    record_id: int
    sr_no:     str
    remark:    Optional[str] = None


