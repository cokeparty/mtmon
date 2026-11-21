# services/dml_validation.py
# 하위 호환 shim — 실제 로직은 sr_validation.py 에 있음.
from services.sr_validation import (  # noqa: F401
    VALIDATION_OK,
    VALIDATION_NG,
    EMERGENCY_WORK_TYPES,
    judge_validation,
    enrich_and_validate,
)
