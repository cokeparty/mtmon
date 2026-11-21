"""
SR DB 조회 — SR DB 에 접속하는 곳은 이 파일 하나뿐이다.

  fetch(sr_no)            SR 1건 → SrMeta (없으면 None, 조회 실패 시 예외)
  fetch_safe(sr_no)       위와 같지만 조회 실패 시 None (화면 입력용)
  fetch_info_map(sr_nos)  여러 건 → {sr_no: {sr_title, work_type, appr_date, close_date}} (날짜는 YYYY-MM-DD)
  existing_set(sr_nos)    SR DB 에 있는 SR번호 집합 (조회 실패 시 None)
  fetch_many_df(sr_nos)   여러 건 → DataFrame (검증용)
"""
import psycopg2
import psycopg2.extras
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from sqlalchemy.engine import make_url

SR_SQL = """
SELECT 
    sr_no AS "SR번호", 
    request_subject AS "SR제목",
    CASE 
        WHEN work_cd = 'W01' THEN '시스템개선'
        WHEN work_cd = 'W04' THEN '데이터변경'
        WHEN work_cd = 'W02' THEN '긴급변경_사후'
        WHEN work_cd = 'W09' THEN '데이터긴급변경'
        WHEN work_cd = 'W05' THEN '권한신청'
        WHEN work_cd = 'W06' THEN '데이터추출'
    END AS "작업구분",
    CASE 
        WHEN work_cd IN ('W01', 'W02') THEN release_ok_confirm_date
        WHEN work_cd IN ('W04', 'W09', 'W05') THEN work_appr_date
        WHEN work_cd = 'W06' THEN work_req_date
    END AS "작업승인일",
    CASE 
        WHEN work_cd IN ('W06', 'W05') THEN work_conf_date
        ELSE sr_close_date                                              
    END AS "SR종료일",
    work_req_date           AS "작업요청일(데이터추출)",
    work_conf_date          AS "작업완료일(데이터추출, 권한신청)",
    work_appr_date          AS "변경승인일",
    apply_appr_date         AS "반영승인일",
    release_ok_confirm_date AS "자원이행확인일",
    sr_close_date           AS "SR종료일(원본)"
FROM sr_master
WHERE sr_no = %s;
"""
# 다건용 (신규) — DML 파이프라인이 사용. WHERE 절만 ANY로 교체.
SR_SQL_MANY = SR_SQL.replace("WHERE sr_no = %s;", "WHERE sr_no = ANY(%s);")

@dataclass
class SrMeta:
    sr_no: str
    sr_title: Optional[str]
    sr_work_type: Optional[str]
    # SR DB 원본이 timestamp 면 시각까지 보존(원본이 date 면 00:00:00).
    sr_approved_at: Optional[datetime]
    sr_closed_at: Optional[datetime]
    sr_developer: Optional[str]
    sr_reviewer: Optional[str]


class SrDbClient:
    def __init__(self, db_url: str, connect_timeout: int = 3):
        u = make_url(db_url)
        self._connect_kwargs = {
            "host": u.host,
            "port": u.port or 5432,
            "dbname": u.database,
            "user": u.username,
            "password": str(u.password) if u.password else None,
            "connect_timeout": connect_timeout,
        }

    def fetch(self, sr_no: str) -> Optional[SrMeta]:
        """sr_no 단건 조회 → SrMeta (없으면 None)"""
        if not sr_no:
            return None
        conn = psycopg2.connect(**self._connect_kwargs)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(SR_SQL, (sr_no,))
                row = cur.fetchone()
                if row is None:
                    return None
                return SrMeta(
                    sr_no=str(row["SR번호"]),
                    sr_title=row["SR제목"],
                    sr_work_type=row["작업구분"],
                    sr_approved_at=row["작업승인일"],
                    sr_closed_at=row["SR종료일"],
                    sr_developer=None,
                    sr_reviewer=None,
                )
        finally:
            conn.close()
    # ── DML 파이프라인 전용 추가 메서드 ──
    def fetch_many_df(self, sr_nos: list[str]):
        """여러 sr_no를 1회 쿼리로 조회 → DataFrame (DML enrich용)."""
        import pandas as pd
        clean = sorted({str(s).strip() for s in sr_nos if s and str(s).strip()})
        if not clean:
            return pd.DataFrame(columns=["SR번호", "SR제목", "작업구분", "작업승인일", "SR종료일"])
        conn = psycopg2.connect(**self._connect_kwargs)
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(SR_SQL_MANY, (clean,))
                rows = cur.fetchall()
        finally:
            conn.close()
        return pd.DataFrame(rows)

# ──────────────────────────────────────────────────────────────
# 모듈 공용 함수 — 접속 정보는 .env 의 SR_DB_URL
# ──────────────────────────────────────────────────────────────
import logging

logger = logging.getLogger(__name__)


def client() -> SrDbClient:
    from config import settings
    if not settings.SR_DB_URL:
        raise RuntimeError("SR_DB_URL 이 설정되지 않았습니다 (.env)")
    return SrDbClient(settings.SR_DB_URL)


def fetch(sr_no: str) -> Optional[SrMeta]:
    return client().fetch(sr_no)


def fetch_safe(sr_no: str) -> Optional[SrMeta]:
    try:
        return fetch(sr_no)
    except Exception as e:
        logger.warning("SR DB 조회 실패 sr_no=%s: %s", sr_no, e)
        return None


def fetch_many_df(sr_nos: list[str]):
    return client().fetch_many_df(sr_nos)


def fetch_info_map(sr_nos) -> dict[str, dict]:
    from services.common.fmt import fmt_date, safe_str
    nos = [s for s in set(sr_nos) if s]
    if not nos:
        return {}
    try:
        df = fetch_many_df(nos)
    except Exception as e:
        logger.warning("SR DB 조회 실패 (%d건): %s", len(nos), e)
        return {}
    out: dict[str, dict] = {}
    for _, row in df.iterrows():
        no = str(row.get("SR번호", "")).strip()
        if no:
            out[no] = {
                "sr_title":   safe_str(row.get("SR제목")),
                "work_type":  safe_str(row.get("작업구분")),
                "appr_date":  fmt_date(row.get("작업승인일")),
                "close_date": fmt_date(row.get("SR종료일")),
            }
    return out


def existing_set(sr_nos) -> Optional[set]:
    nos = [s for s in set(sr_nos) if s]
    if not nos:
        return set()
    try:
        df = fetch_many_df(nos)
    except Exception as e:
        logger.warning("SR DB 조회 실패 (%d건): %s", len(nos), e)
        return None
    return set() if df.empty else set(df["SR번호"].astype(str).str.strip())
