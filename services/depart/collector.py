# services/depart_collector.py
"""
부서이동자 데이터 수집기 (Oracle → PostgreSQL)

일간: html_sql.md 기반 6개 쿼리 → depart.daily_record UPSERT
     1) 퇴직자(인사이력)  2) 퇴직자(ISG마스터)  3) 부서변경자
     4) HR(ERP) 추가권한  5) 전자조달 추가권한  6) PMS 추가권한
월간: select 파일 기반 4개 쿼리 → depart.monthly_record INSERT
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime

import psycopg2
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session
import oracledb

from config import settings
from models.depart import DailyRecord, MonthlyRecord

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# ★ thick 모드 초기화 : 이 파일이 import 될 때 딱 1회 실행됨
#   반드시 oracledb.connect() 가 호출되기 "전에" 실행되어야 함
# ─────────────────────────────────────────────
try:
    oracledb.init_oracle_client(lib_dir=settings.ORACLE_CLIENT_LIB_DIR)
    logger.info("Oracle thick 모드 초기화 완료")
except Exception as e:
    logger.warning("Oracle thick 모드 초기화 스킵/실패: %s", e)

# ──────────────────────────────────────────────────────────────
# EDB(EnterpriseDB EPAS) 연결
# EDB 서버 내 Oracle DBLINK(prod_view)를 통해 Oracle 테이블 조회.
# ──────────────────────────────────────────────────────────────
def _edb_connect():
    """EDB Postgres Advanced Server 접속.
    설정값 BPM_ORACLE_DSN 형식: host:port/dbname
    """
    host_port, dbname = settings.BPM_ORACLE_DSN.rsplit("/", 1)
    host, port = host_port.rsplit(":", 1)
    return psycopg2.connect(
        host=host,
        port=int(port),
        dbname=dbname,
        user=settings.BPM_ORACLE_USER,
        password=settings.BPM_ORACLE_PASSWORD,
        connect_timeout=10,
    )
# ──────────────────────────────────────────────────────────────
# ORACLE 연결
# ──────────────────────────────────────────────────────────────
def _oracle_connect():
    host_port, service = settings.ORACLE_DSN.rsplit("/", 1)
    host, port = host_port.rsplit(":", 1)
    dsn = oracledb.makedsn(host, int(port), service_name=service)
    return oracledb.connect(
        user=settings.ORACLE_USER,
        password=settings.ORACLE_PASSWORD,
        dsn=dsn,
    )

def _exec_edb(sql: str, params: dict | None = None) -> list[dict]:
    """EDB에 SQL 실행.
    params 가 None 또는 빈 dict 면 None 으로 전달 —
    psycopg2 가 SQL 내 % 문자를 파라미터로 해석하지 않도록 방지.
    """
    conn = _edb_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or None)
            cols = [c[0].lower() for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()

def _exec_oracle(sql: str, params: dict | None = None) -> list[dict]:
    conn = _oracle_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params or {})
            cols = [c[0].lower() for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()
# ──────────────────────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────────────────────
def _parse_date(v):
    """문자열/None을 date로 변환. 실패 시 None.

    지원 형식:
      - 'YYYY-MM-DD' (HR·EPRO: TO_CHAR 포맷)
      - 'YYYYMMDD'   (PMS: ath_begin_de/ath_end_de 원본 문자열)  ← 미포맷이라 과거 None 되던 버그
      - date/datetime 객체 (그대로 통과)
    """
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        from datetime import datetime as dt
        s = v.strip()
        for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
            try:
                return dt.strptime(s[:10] if "-" in s or "/" in s else s[:8], fmt).date()
            except Exception:
                continue
        return None
    return v


# ──────────────────────────────────────────────────────────────
# 일간 쿼리 (html_sql.md 기반 — 7일 뷰)
# ──────────────────────────────────────────────────────────────
# 오라클 직접접속해도되므로 @prod_view 제거
_Q_RESIGN_PE = """
SELECT a.revision_date AS change_date,
       a.empcd         AS empno,
       a.hname         AS emp_name,
       a.deptcd        AS dept_code,
       d.deptnm        AS dept_name,
       NULL            AS prev_dept_name
FROM   is_pe01_history a,
       is_bm02        d
WHERE  a.revision_date >= (SYSDATE - 7)
  AND  a.retdat IS NOT NULL
  AND  a.deptcd = d.deptcd
"""
# 오라클 직접접속해도되므로 @prod_view 제거
_Q_RESIGN_ISG = """
SELECT i.end_date_active AS change_date,
       i.sabun_cd        AS empno,
       i.k_name          AS emp_name,
       i.deptcode        AS dept_code,
       i.deptname        AS dept_name,
       NULL              AS prev_dept_name
FROM   cbou.cbo_sa_isg_empmst i
WHERE  i.enable_flag     = 'Y'
  AND  i.end_date_active >= (SYSDATE - 7)
  AND  i.end_date_active < SYSDATE
"""
# 오라클 직접접속해도되므로 @prod_view 제거
_Q_DEPT_CHG = """
SELECT DISTINCT
       revision_date AS change_date,
       empcd         AS empno,
       hname         AS emp_name,
       to_deptcd     AS dept_code,
       to_deptnm     AS dept_name,
       from_deptcd   AS prev_dept_code,
       from_deptnm   AS prev_dept_name
FROM   apps.cbo_sa_dept_chg_7
"""

_Q_EPRO_ROLE = """
SELECT dept_chg.revision_date AS change_date,
       b.role_nm              AS role_name,
       b.role_cd              AS role_code,
       c.usr_id               AS empno,
       c.usr_nm               AS emp_name,
       a.reg_dt               AS reg_date,
       dept_chg.to_deptnm     AS dept_name,
       dept_chg.from_deptnm   AS prev_dept_name
FROM   epro.esaaurp a,
       epro.esaaurh b,
       epro.esauser c,
       apps.cbo_sa_dept_chg_7@prod_view dept_chg
WHERE  b.sys_id    = 'EMRO'
  AND  a.usr_id   = c.usr_id
  AND  a.sts      <> 'D'  AND b.sts <> 'D'  AND c.sts <> 'D'
  AND  c.usr_cls  = 'B'   AND NVL(c.use_yn,'N') = 'Y'
  AND  a.sys_id   = b.sys_id
  AND  a.sys_id   = c.sys_id
  AND  a.role_cd  = b.role_cd
  AND  b.use_yn   = 'Y'
  AND  b.role_cd <> 'PR001'
  AND  a.usr_id   = dept_chg.empcd
"""

_Q_HR_ROLE = """
SELECT DISTINCT
       dept_chg.revision_date                     AS change_date,
       g.empcd                                    AS empno,
       g.hname                                    AS emp_name,
       h.deptnm                                   AS dept_name,
       dept_chg.from_deptnm                       AS prev_dept_name,
       d.responsibility_name                      AS role_name,
       CAST(a.responsibility_id AS VARCHAR2(50))  AS role_code,
       a.start_date                               AS reg_date
FROM (
    SELECT u.user_id, u.user_name,
           wur.role_orig_system_id  AS responsibility_id,
           fa.application_id        AS responsibility_application_id,
           fsg.security_group_id    AS security_group_id,
           wura.start_date, wura.end_date, wura.creation_date
    FROM   fnd_user                   u,
           wf_user_role_assignments_v wura,
           wf_user_roles              wur,
           fnd_application            fa,
           fnd_security_groups        fsg
    WHERE  wura.user_name = u.user_name
      AND  u.start_date <= SYSDATE
      AND  NVL(u.end_date, SYSDATE) >= SYSDATE
      AND  wur.role_orig_system = 'FND_RESP'
      AND  wur.partition_id = 2
      AND  wura.role_name = wur.role_name
      AND  wura.user_name = wur.user_name
      AND  fa.application_short_name =
               REPLACE(SUBSTR(wura.role_name,
                   INSTR(wura.role_name,'|',1,1)+1,
                   INSTR(wura.role_name,'|',1,2)-INSTR(wura.role_name,'|',1,1)-1),
               '%col',':')
      AND  fsg.security_group_key =
               REPLACE(SUBSTR(wura.role_name,
                   INSTR(wura.role_name,'|',1,3)+1),
               '%col',':')
) a,
fnd_application_tl    c,
fnd_responsibility_tl d,
fnd_responsibility    e,
is_pe01               g,
is_bm02               h,
(SELECT b.user_id, a.responsibility_id, MAX(a.start_time) AS last_use_dt
 FROM   fnd_login_responsibilities a, fnd_logins b
 WHERE  a.login_id = b.login_id
 GROUP BY b.user_id, a.responsibility_id) last_use,
(SELECT a.revision_date, a.empcd, a.hname,
        a.deptcd AS to_deptcd, d.deptnm AS to_deptnm,
        b.deptcd AS from_deptcd, e.deptnm AS from_deptnm
 FROM   is_pe01_history a, is_pe01_history b, is_bm02 d, is_bm02 e
 WHERE  a.revision_date >= SYSDATE - 7
   AND  a.emp_id = b.emp_id
   AND  b.revision_num < a.revision_num
   AND  b.revision_num = (SELECT MAX(c.revision_num) FROM is_pe01_history c
                           WHERE c.emp_id = b.emp_id AND c.revision_num < a.revision_num)
   AND  a.deptcd <> b.deptcd
   AND  a.deptcd = d.deptcd AND b.deptcd = e.deptcd) dept_chg
WHERE  a.start_date <= SYSDATE
  AND  NVL(a.end_date, SYSDATE) >= SYSDATE
  AND  a.responsibility_id = d.responsibility_id
  AND  a.responsibility_application_id = d.application_id
  AND  a.responsibility_id = e.responsibility_id
  AND  a.responsibility_application_id = e.application_id
  AND  a.responsibility_application_id = c.application_id
  AND  e.start_date <= SYSDATE AND NVL(e.end_date, SYSDATE) >= SYSDATE
  AND  a.user_name = g.empcd
  AND  g.deptcd = h.deptcd
  AND  e.responsibility_key NOT IN (SELECT resp_key FROM cbou.cbo_sa_resp_inst_t
                                     WHERE gb_cd IN ('A','E'))
  AND  a.user_id = last_use.user_id(+)
  AND  a.responsibility_id = last_use.responsibility_id(+)
  AND  g.empcd = dept_chg.empcd
"""

_Q_PMS_ROLE = """
SELECT dept_chg.revision_date  AS change_date,
       grp.grp_ath_nm          AS role_name,
       userg.grp_ath_cd        AS role_code,
       emp.empno               AS empno,
       emp.emp_nm              AS emp_name,
       userg.ath_begin_de      AS reg_date,
       dept_chg.to_deptnm      AS dept_name,
       dept_chg.from_deptnm    AS prev_dept_name
FROM   proj.cm_user_rgt_grp userg,
       proj.cm_rgt_grp       grp,
       proj.cm_emp            emp,
       apps.cbo_sa_dept_chg_7@prod_view dept_chg
WHERE  userg.grp_ath_cd = grp.grp_ath_cd
  AND  userg.emp_id     = emp.emp_id
  AND  SUBSTR(userg.grp_ath_cd, 1, 3) IN ('CM0','POM','PMS')
  AND  userg.grp_ath_cd NOT IN ('CM0001','PMS_AU10','POM_AU00')
  AND  emp.empno        = dept_chg.empcd
  AND  NVL(userg.ath_end_de, TO_CHAR(SYSDATE,'YYYYMMDD'))
       >= TO_CHAR(SYSDATE,'YYYYMMDD')
"""

# ──────────────────────────────────────────────────────────────
# 월간 쿼리 (select 파일 기반 — 날짜 파라미터)
# ──────────────────────────────────────────────────────────────
def _monthly_dept_list(ym: str) -> str:
    y, m = ym.split("-")
    start = f"{y}{m}01"
    import calendar
    end = f"{y}{m}{calendar.monthrange(int(y), int(m))[1]:02d}"
    return f"""
SELECT TO_CHAR(a.lstbaldat,'YYYY-MM-DD') AS change_date,
       a.empcd   AS empno,  a.hname AS emp_name,
       a.deptcd  AS dept_code, d.deptnm AS dept_name,
       b.deptcd  AS prev_dept_code, e.deptnm AS prev_dept_name
FROM   is_pe01_history a, is_pe01_history b, is_bm02 d, is_bm02 e
WHERE  a.lstbaldat BETWEEN TO_DATE('{start}','YYYYMMDD')
                       AND TO_DATE('{end}','YYYYMMDD')
  AND  a.emp_id  = b.emp_id
  AND  b.revision_num < a.revision_num
  AND  b.revision_num = (SELECT MAX(c.revision_num) FROM is_pe01_history c
                          WHERE c.emp_id = a.emp_id AND c.revision_num < a.revision_num)
  AND  a.deptcd <> b.deptcd
  AND  a.deptcd = d.deptcd  AND b.deptcd = e.deptcd
"""


def _monthly_pms(ym: str) -> str:
    return f"""
SELECT 'PMS' AS system_code,
       TO_CHAR(dept_chg.revision_date,'YYYY-MM-DD') AS change_date,
       grp.grp_ath_nm  AS role_name,
       userg.grp_ath_cd AS role_code,
       emp.empno        AS empno,
       emp.emp_nm       AS emp_name,
       userg.ath_begin_de AS reg_date,
       userg.ath_end_de   AS revoke_date,
       dept_chg.to_deptnm   AS dept_name,
       dept_chg.from_deptnm AS prev_dept_name
FROM   proj.cm_user_rgt_grp userg,
       proj.cm_rgt_grp   grp,
       proj.cm_emp        emp,
       apps.cbo_sa_dept_chg_1m@prod_view dept_chg
WHERE  userg.grp_ath_cd = grp.grp_ath_cd
  AND  userg.emp_id     = emp.emp_id
  AND  SUBSTR(userg.grp_ath_cd,1,3) = ANY(ARRAY['CM0','POM','PMS'])
  AND  userg.grp_ath_cd <> ALL(ARRAY['CM0001','PMS_AU10','POM_AU00'])
  AND  emp.empno = dept_chg.empcd
  AND  NVL(userg.ath_end_de, TO_CHAR(SYSDATE,'YYYYMMDD'))
       >= TO_CHAR(SYSDATE-20,'YYYYMM') || '01'
"""


def _monthly_hr(ym: str) -> str:
    y, m = ym.split("-")
    start = f"{y}{m}01"
    import calendar
    end = f"{y}{m}{calendar.monthrange(int(y), int(m))[1]:02d}"
    return f"""
SELECT DISTINCT 'HR' AS system_code,
       TO_CHAR(dept_chg.lstbaldat,'YYYY-MM-DD') AS change_date,
       h.deptnm  AS dept_name,
       g.empcd   AS empno, g.hname AS emp_name,
       dept_chg.from_deptnm AS prev_dept_name,
       d.responsibility_name AS role_name,
       CAST(a.responsibility_id AS VARCHAR2(50)) AS role_code,
       TO_CHAR(a.START_DATE,'YYYY-MM-DD') AS reg_date,
       TO_CHAR(a.end_date,'YYYY-MM-DD')   AS revoke_date
FROM  (SELECT u.user_id,u.user_name,wura.RESPONSIBILITY_APPLICATION_ID,
              wura.RESPONSIBILITY_ID,wura.start_date,wura.end_date
       FROM   fnd_user u, FND_USER_RESP_GROUPS_DIRECT wura
       WHERE  wura.user_id = u.user_id
         AND  u.start_date <= SYSDATE
         AND  NVL(u.end_date,SYSDATE) >= TO_DATE('{start}','YYYYMMDD')) a,
       FND_Application_tl c, FND_RESPONSIBILITY_tl d, FND_RESPONSIBILITY e,
       is_pe01 g, is_bm02 h,
       (SELECT b.user_id,a.responsibility_id,MAX(a.start_time) last_use_dt
        FROM   fnd_login_responsibilities a, fnd_logins b
        WHERE  a.login_id = b.login_id
        GROUP BY b.user_id,a.responsibility_id) last_use,
       (SELECT a.lstbaldat,a.empcd,a.hname,a.deptcd to_deptcd,d.deptnm to_deptnm,
               b.deptcd from_deptcd,e.deptnm from_deptnm
        FROM   is_pe01_history a,is_pe01_history b,is_bm02 d,is_bm02 e
        WHERE  a.lstbaldat BETWEEN TO_DATE('{start}','YYYYMMDD')
                               AND TO_DATE('{end}','YYYYMMDD')
          AND  a.emp_id=b.emp_id AND b.revision_num < a.revision_num
          AND  b.revision_num=(SELECT MAX(c.revision_num) FROM is_pe01_history c
                                WHERE c.emp_id=b.emp_id AND c.revision_num < a.revision_num)
          AND  a.deptcd<>b.deptcd AND a.deptcd=d.deptcd AND b.deptcd=e.deptcd) dept_chg
WHERE  a.start_date <= SYSDATE
  AND  (NVL(a.end_date,SYSDATE) >= SYSDATE OR a.end_date >= TO_DATE('{start}','YYYYMMDD'))
  AND  a.responsibility_id = d.responsibility_id
  AND  a.responsibility_application_id = d.application_id
  AND  a.responsibility_id = e.responsibility_id
  AND  a.responsibility_application_id = e.application_id
  AND  a.responsibility_application_id = c.application_id
  AND  e.start_date <= SYSDATE AND NVL(e.end_date,SYSDATE) >= SYSDATE
  AND  a.user_name = g.empcd AND g.deptcd = h.deptcd
  AND  e.responsibility_key NOT IN (SELECT resp_key FROM cbou.cbo_sa_resp_inst_t
                                     WHERE gb_cd IN ('A','E'))
  AND  a.user_id = last_use.user_id(+)
  AND  a.RESPONSIBILITY_ID = last_use.responsibility_id(+)
  AND  g.empcd = dept_chg.empcd
"""


def _monthly_epro(ym: str) -> str:
    y, m = ym.split("-")
    return f"""
SELECT '전자조달' AS system_code,
       TO_CHAR(dept_chg.revision_date,'YYYY-MM-DD') AS change_date,
       b.role_nm  AS role_name,
       b.role_cd  AS role_code,
       c.usr_id   AS empno, c.usr_nm AS emp_name,
       TO_CHAR(a_1.reg_dt,'YYYY-MM-DD') AS reg_date,
       NULL AS revoke_date,
       dept_chg.to_deptnm   AS dept_name,
       dept_chg.from_deptnm AS prev_dept_name
FROM   epro.esaaurp a_1, epro.esaaurh b, epro.esauser c,
       apps.cbo_sa_dept_chg_1m@prod_view dept_chg
WHERE  b.sys_id='EMRO' AND a_1.usr_id=c.usr_id AND a_1.sts<>'D'
  AND  b.sts<>'D' AND c.sts<>'D' AND c.usr_cls='B' AND NVL(c.use_yn,'N')='Y'
  AND  a_1.sys_id=b.sys_id AND a_1.sys_id=c.sys_id AND a_1.role_cd=b.role_cd
  AND  b.use_yn='Y' AND b.role_cd<>'PR001' AND a_1.usr_id=dept_chg.empcd
UNION
SELECT '전자조달',TO_CHAR(dept_chg.revision_date,'YYYY-MM-DD'),
       b.role_nm, b.role_cd, c.usr_id, c.usr_nm,
       DECODE(a_1.MODE,'A',TO_CHAR(a_1.reg_dt,'YYYY-MM-DD'),NULL),
       DECODE(a_1.MODE,'R',TO_CHAR(a_1.reg_dt,'YYYY-MM-DD'),NULL),
       dept_chg.to_deptnm, dept_chg.from_deptnm
FROM   epro.esaaurp_l a_1, epro.esaaurh b, epro.esauser c,
       apps.cbo_sa_dept_chg_1m@prod_view dept_chg
WHERE  b.sys_id='EMRO' AND a_1.usr_id=c.usr_id
  AND  b.sts<>'D' AND c.sts<>'D' AND c.usr_cls='B' AND NVL(c.use_yn,'N')='Y'
  AND  a_1.sys_id=b.sys_id AND a_1.sys_id=c.sys_id AND a_1.role_cd=b.role_cd
  AND  b.use_yn='Y' AND b.role_cd<>'PR001' AND a_1.usr_id=dept_chg.empcd
  AND  TO_CHAR(a_1.reg_dt,'YYYYMM') >= '{y}{m}'
"""


# ──────────────────────────────────────────────────────────────
# 일간 수집 (UPSERT)
# ──────────────────────────────────────────────────────────────
def collect_daily(db: Session) -> dict:
    today = date.today()
    logger.info("일간 수집 시작 date=%s", today)

    tasks = [
        ("퇴직자",      _Q_RESIGN_PE, _exec_oracle),
        ("퇴직자(협력)", _Q_RESIGN_ISG, _exec_oracle),
        ("부서변경자",  _Q_DEPT_CHG, _exec_oracle),
        ("HR권한",      _Q_HR_ROLE, _exec_oracle),
        ("전자조달권한", _Q_EPRO_ROLE, _exec_edb),
        ("PMS권한",     _Q_PMS_ROLE, _exec_edb),
    ]

    total_upserted = 0
    task_results: list[dict] = []

    for record_type, sql, exec_fn in tasks:
        try:
            rows = exec_fn(sql)
            for r in rows:
                _upsert_daily(db, record_type, r, today)
                total_upserted += 1
            task_results.append({"type": record_type, "ok": True, "count": len(rows)})
            logger.info("  [%s] %d건 수집 완료", record_type, len(rows))
        except Exception as e:
            task_results.append({"type": record_type, "ok": False, "error": str(e)})
            logger.warning("  [%s] 수집 실패: %s", record_type, e)

    db.commit()
    logger.info("일간 수집 완료 — 총 %d건 UPSERT", total_upserted)
    return {"upserted": total_upserted, "date": str(today), "tasks": task_results}


def _upsert_daily(db: Session, record_type: str, r: dict, today: date):
    role_code = r.get("role_code") or None
    role_key  = role_code if role_code else "-"

    change_date = r.get("change_date")
    if isinstance(change_date, str):
        from datetime import datetime as dt
        change_date = dt.strptime(change_date[:10], "%Y-%m-%d").date()

    values = {
        "record_type":    record_type,
        "empno":          str(r.get("empno", "") or ""),
        "emp_name":       r.get("emp_name"),
        "change_date":    change_date,
        "dept_code":      r.get("dept_code"),
        "dept_name":      r.get("dept_name"),
        "prev_dept_code": r.get("prev_dept_code"),
        "prev_dept_name": r.get("prev_dept_name"),
        "role_code":      role_code,
        "role_key":       role_key,
        "role_name":      r.get("role_name"),
        "reg_date":       r.get("reg_date"),
        "first_seen":     today,
        "last_seen":      today,
    }

    stmt = pg_insert(DailyRecord).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_daily_record",
        set_={"last_seen": today},   # 처리 상태(action·sr_no) 보존, last_seen만 갱신
    )
    db.execute(stmt)


# ──────────────────────────────────────────────────────────────
# 월간 수집 (UPSERT)
# ──────────────────────────────────────────────────────────────
def collect_monthly(db: Session, period_id: int, year_month: str) -> dict:
    logger.info("월간 수집 시작 year_month=%s period_id=%s", year_month, period_id)

    # ── 기존 DELETE 후 재적재 → UPSERT 로 변경 ─────────────────────────
    # [수정] 과거에는 적재 전 해당 회차 레코드를 전부 삭제(delete)한 뒤 다시
    #   INSERT 했기 때문에, 사용자가 입력한 sr_no/sr_title/remark 가
    #   월간 조회를 다시 실행할 때마다 사라졌음.
    #   일간(collect_daily)과 동일하게 DELETE 없이 _bulk_upsert_monthly 의
    #   on_conflict_do_update 로만 갱신하여 사용자 입력값을 보존한다.
    tasks = [
        ("공통", _monthly_dept_list(year_month), _exec_oracle),
        ("HR",   _monthly_hr(year_month), _exec_oracle),
        ("PMS",  _monthly_pms(year_month), _exec_edb),
        ("EPRO", _monthly_epro(year_month), _exec_edb),
    ]

    total = 0
    task_results: list[dict] = []

    for system_code, sql, exec_fn in tasks:
        try:
            rows = exec_fn(sql)
            n = _bulk_upsert_monthly(db, period_id, system_code, rows)
            total += n
            task_results.append({"code": system_code, "ok": True, "count": n})
            logger.info("  [%s] %d건 수집 완료", system_code, n)

        except Exception as e:
            task_results.append({"code": system_code, "ok": False, "error": str(e)})
            logger.warning("  [%s] 수집 실패: %s", system_code, e)

    db.commit()

    synced = _sync_sr_from_daily(db, period_id, year_month)
    if synced:
        db.commit()
        logger.info("일간→월간 SR 자동매핑 %d건", synced)

    logger.info("월간 수집 완료 — 총 %d건 UPSERT", total)
    return {"upserted": total, "year_month": year_month, "tasks": task_results, "sr_synced": synced}


def _monthly_values(period_id: int, system_code: str, r: dict) -> dict:
    role_code = r.get("role_code") or None
    role_key  = role_code if role_code else "-"
    return {
        "period_id":      period_id,
        "system_code":    system_code,
        "empno":          str(r.get("empno", "") or ""),
        "emp_name":       r.get("emp_name"),
        "change_date":    _parse_date(r.get("change_date")),
        "dept_code":      r.get("dept_code"),
        "dept_name":      r.get("dept_name"),
        "prev_dept_code": r.get("prev_dept_code"),
        "prev_dept_name": r.get("prev_dept_name"),
        "role_code":      role_code,
        "role_key":       role_key,
        "role_name":      r.get("role_name"),
        "reg_date":       _parse_date(r.get("reg_date")),
        "revoke_date":    _parse_date(r.get("revoke_date")),
    }


def _bulk_upsert_monthly(db: Session, period_id: int, system_code: str, rows: list[dict]) -> int:
    """월간 레코드 일괄 UPSERT.

    [성능 개선] 기존에는 행마다 별도 INSERT…ON CONFLICT 를 실행(행당 1 round-trip)해
    수천 건 적재 시 매우 느렸음. 한 태스크의 전체 행을 단일 statement 로 묶어 처리한다.
    단, ON CONFLICT DO UPDATE 는 한 명령에서 같은 충돌키를 두 번 건드릴 수 없으므로
    (period_id, system_code, empno, role_key) 기준으로 사전 dedup(마지막 행 우선)한다.
    """
    deduped: dict[tuple, dict] = {}
    for r in rows:
        v = _monthly_values(period_id, system_code, r)
        key = (v["period_id"], v["system_code"], v["empno"], v["role_key"])
        deduped[key] = v  # 동일 키는 마지막 값으로 덮어씀 (행별 UPSERT와 동일 효과)

    values = list(deduped.values())
    if not values:
        return 0

    stmt = pg_insert(MonthlyRecord).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_monthly_record",
        set_={
            "emp_name":       stmt.excluded.emp_name,
            "change_date":    stmt.excluded.change_date,
            "dept_code":      stmt.excluded.dept_code,
            "dept_name":      stmt.excluded.dept_name,
            "prev_dept_code": stmt.excluded.prev_dept_code,
            "prev_dept_name": stmt.excluded.prev_dept_name,
            "role_code":      stmt.excluded.role_code,
            "role_name":      stmt.excluded.role_name,
            "reg_date":       stmt.excluded.reg_date,
            "revoke_date":    stmt.excluded.revoke_date,
            # 키 컬럼(period_id, system_code, empno, role_key)은 갱신 대상에서 제외
            # sr_no/sr_title/remark는 사용자 입력값 보존
        },
    )
    db.execute(stmt)
    return len(values)


# ──────────────────────────────────────────────────────────────
# 일간 SR → 월간 자동 매핑
# ──────────────────────────────────────────────────────────────
_RTYPE_TO_SYSTEM: dict[str, str] = {
    "HR권한":       "HR",
    "전자조달권한": "EPRO",
    "PMS권한":      "PMS",
}


def _sync_sr_from_daily(db: Session, period_id: int, year_month: str) -> int:
    """일간 화면에서 입력된 SR 번호를 월간 레코드에 자동 복사.

    empno + role_key 가 일치하고 월간 레코드의 sr_no 가 비어 있을 때만 덮어쓴다.
    이미 수동 입력된 월간 SR 은 그대로 보존된다.
    """
    year, month = map(int, year_month.split("-"))
    _, last_day = calendar.monthrange(year, month)
    start = date(year, month, 1)
    end   = date(year, month, last_day)

    daily_rows = (
        db.query(DailyRecord)
        .filter(
            DailyRecord.record_type.in_(list(_RTYPE_TO_SYSTEM.keys())),
            DailyRecord.sr_no.isnot(None),
            DailyRecord.last_seen >= start,
            DailyRecord.last_seen <= end,
        )
        .all()
    )

    synced = 0
    for d in daily_rows:
        system_code = _RTYPE_TO_SYSTEM[d.record_type]
        monthly = (
            db.query(MonthlyRecord)
            .filter_by(
                period_id=period_id,
                system_code=system_code,
                empno=d.empno,
                role_key=d.role_key,
            )
            .first()
        )
        if monthly and not monthly.sr_no:
            monthly.sr_no        = d.sr_no
            monthly.sr_title     = d.sr_title
            monthly.sr_work_type = d.sr_work_type
            synced += 1

    return synced