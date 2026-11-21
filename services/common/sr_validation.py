# services/sr_validation.py
"""
SR 검증 공용 모듈 — DML·DDL 양쪽에서 공유.
judge_validation : 행 단위 정상/비정상 판정
enrich_and_validate : DataFrame + SR DB → 검증 결과 열 추가
"""
import pandas as pd
from datetime import timedelta

from config import settings

VALIDATION_OK = "정상"
VALIDATION_NG = "비정상"
EMERGENCY_WORK_TYPES = ("데이터긴급변경", "긴급변경_사후")


def judge_validation(req_dt, appr_dt, close_dt, work_type):
    """
    단일 행 판정.
    - req_dt 없음 → None (판정불가)
    - 작업승인일 있고 실행일 >= 승인일 → 정상  (긴급변경 포함)
    - 긴급변경 타입 → SR종료일이 실행일 + GRACE_DAYS 이내면 정상
    - 일반 SR에서 승인일 없거나 실행일 < 승인일 → 비정상/None
    """
    if pd.isna(req_dt):
        return None
    # 작업승인일 있고 실행일이 승인일 이후 → 정상 (긴급변경 포함)
    if appr_dt is not None and not pd.isna(appr_dt) and req_dt >= appr_dt:
        return VALIDATION_OK
    if work_type in EMERGENCY_WORK_TYPES:
        if close_dt is None or pd.isna(close_dt):
            return VALIDATION_NG
        return (VALIDATION_OK
                if close_dt <= req_dt + timedelta(days=settings.EMERGENCY_GRACE_DAYS)
                else VALIDATION_NG)
    if appr_dt is None or pd.isna(appr_dt):
        return None
    return VALIDATION_NG


def enrich_and_validate(rows: pd.DataFrame, sr_client=None) -> pd.DataFrame:
    """parser rows + SR DB → SR 머지 + 행단위 검증. sr_client 를 안 주면 .env 의 SR DB 사용."""
    if sr_client is None:
        from services.common import sr
        sr_client = sr.client()
    rows = rows.copy()
    sr_df = sr_client.fetch_many_df(rows["sr_no"].dropna().unique().tolist())

    sr_df = sr_df.rename(columns={
        "SR번호": "sr_no", "SR제목": "sr_title", "작업구분": "work_type",
        "작업승인일": "appr_date", "SR종료일": "close_date",
    })[["sr_no", "sr_title", "work_type", "appr_date", "close_date"]]
    sr_df["sr_no"] = sr_df["sr_no"].astype(str).str.strip()
    for c in ["appr_date", "close_date"]:
        sr_df[c] = pd.to_datetime(sr_df[c], errors="coerce")

    rows["sr_no"] = rows["sr_no"].astype(object)
    merged = rows.merge(sr_df, on="sr_no", how="left")
    if "req_time" in merged.columns:
        merged["req_time"] = pd.to_datetime(merged["req_time"], errors="coerce")

    def _judge(r):
        if not r.get("sr_no") or pd.isna(r.get("work_type")):
            return None
        return judge_validation(r.get("req_time"), r.get("appr_date"),
                                r.get("close_date"), r.get("work_type"))

    merged["validation"] = merged.apply(_judge, axis=1)
    return merged
