# schemas/ddl.py
from pydantic import BaseModel


class DdlApplySrRequest(BaseModel):
    log_id: int
    sr_no:  str


class DdlClearSrRequest(BaseModel):
    log_id: int


class DdlSaveReasonRequest(BaseModel):
    log_id: int
    reason: str = ""


class DdlSaveFieldsRequest(BaseModel):
    log_id: int
    fields: dict
