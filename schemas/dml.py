# schemas/dml.py
from pydantic import BaseModel


class ApplySrRequest(BaseModel):
    group_id: int
    sr_no: str


class ClearSrRequest(BaseModel):
    group_id: int


class SetDmlRequest(BaseModel):
    group_id: int
    is_dml: bool


class SetReasonRequest(BaseModel):
    group_id: int
    reason: str = ""


class BulkApplySrRequest(BaseModel):
    group_ids: list[int]
    sr_no: str
    skip_existing: bool = True
