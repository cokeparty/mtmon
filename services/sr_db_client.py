"""
============================================================
 services/sr_db_client.py
------------------------------------------------------------
 [수정 내역]
 2026-06-01  버그 수정 3건
   1) SrDbClient.__init__(db_url) 추가
      - 기존 코드가 settings.SR_DB_HOST 등 존재하지 않는 속성을 참조해
        AttributeError 발생 → collect_orchestrator 가 전달하는 db_url을
        make_url()로 파싱하여 psycopg2 연결 인자로 변환
   2) fetch() 시그니처 변경: list[str] → str (단건 조회)
      - collect_orchestrator 호출부가 sr_no 1건씩 전달하는 실제 패턴에 맞게 수정
   3) 반환 타입 변경: dict[str,dict] → Optional[SrMeta] 데이터클래스
      - collect_orchestrator 에서 sr_meta.sr_title 등 속성으로 접근하므로
        dict 반환 시 AttributeError 발생 → dataclass 반환으로 수정
============================================================
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
    def fetch_many_df(self, sr_nos: list[str]) -> "pd.DataFrame":
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