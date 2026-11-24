# services/depart/collector.py
"""
부서이동자 데이터 수집기 (HR(Tibero) → PostgreSQL)

HR(Tibero) DB 하나에만 접속한다. 조달구매(epro) · PMS(proj) 권한은
Tibero 의 DB 링크(@DXHRT_BPMT1)로 함께 조회한다.  (접속: services/depart/tibero.py)
쿼리 원본: _mine/신HR 일일모니터링 쿼리.md · 신HR 월간모니터링 쿼리.md

일간 (최근 7일 ~ 어제, 소급발령 포함) → depart.daily_record UPSERT
     퇴직자(임직원) · 퇴직자(협력) · 부서변경자 · HR권한(IHR) · 전자조달권한 · PMS권한
월간 (회차 월 1일 ~ 말일)            → depart.monthly_record UPSERT
     공통(부서이동자) · 퇴사자 · HR(IHR) · PMS · EPRO(전자조달)
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models.depart import DailyRecord, MonthlyRecord
from services.depart import tibero

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 공통 유틸
# ──────────────────────────────────────────────────────────────
def _parse_date(v):
    """문자열/None → date. 실패 시 None.
    지원 형식: YYYYMMDD · YYYY-MM-DD · YYYY.MM.DD · YYYY/MM/DD (뒤에 시각이 붙어도 됨), date/datetime
    """
    if not v:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    digits = s[:10].replace("-", "").replace(".", "").replace("/", "")
    try:
        return datetime.strptime(digits[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _month_range(ym: str) -> tuple[str, str]:
    """'2026-10' → ('20261001', '20261031') — 숫자로 다시 만들어 SQL 에 넣어도 안전"""
    y, m = (int(x) for x in ym.split("-"))
    return f"{y:04d}{m:02d}01", f"{y:04d}{m:02d}{calendar.monthrange(y, m)[1]:02d}"


# 조직명: 기준일 이전 마지막 이름 → 없으면 기준일 이후 첫 이름 → 없으면 fallback
def _org_nm(code: str, base_date: str, fallback: str) -> str:
    return f"""COALESCE(
         (SELECT MAX(o.ORG_NM) KEEP (DENSE_RANK LAST ORDER BY o.START_DATE)
            FROM POSDXHR.HOM_ORG_DTL_INFO o
           WHERE o.COMP_CODE = b.COMP_CODE AND o.ORG_CODE = {code}
             AND o.START_DATE <= {base_date}),
         (SELECT MIN(o.ORG_NM) KEEP (DENSE_RANK FIRST ORDER BY o.START_DATE)
            FROM POSDXHR.HOM_ORG_DTL_INFO o
           WHERE o.COMP_CODE = b.COMP_CODE AND o.ORG_CODE = {code}
             AND o.START_DATE > {base_date}),
         {fallback})"""


# 발령이력에 직전 부서코드·직전 종료일을 붙인 것 (확정 발령만)
_ASG_HIST = """
       (SELECT h.COMP_CODE, h.EMP_ID, h.ASG_HIST_ID, h.START_DATE, h.END_DATE, h.SNO
             , h.ASG_DATE, h.ASG_NO, h.ASG_TP, h.ASG_CAUSE, h.ASG_CONTENT
             , h.ORG_CODE, h.DUTY_CODE, h.GRADE_CODE, h.POSITION_CODE, h.CRE_DTM
             , LAG(h.ORG_CODE) OVER (PARTITION BY h.COMP_CODE, h.EMP_ID
                                     ORDER BY h.START_DATE, h.SNO, h.ASG_HIST_ID) AS PREV_ORG_CODE
             , LAG(h.END_DATE) OVER (PARTITION BY h.COMP_CODE, h.EMP_ID
                                     ORDER BY h.START_DATE, h.SNO, h.ASG_HIST_ID) AS PREV_END_DATE
          FROM POSDXHR.HPA_ASG_HIST h
         WHERE h.COMP_CODE    = 'dx'
           AND h.CONFIRM_FLAG = 'Y'
           AND REGEXP_LIKE(h.START_DATE, '^(19|20)[0-9]{6}$')
       ) b"""


def _dept_movers(fr: str, to: str, with_comp_join: bool = True) -> str:
    """부서이동자 (발령적용일 fr~to, 부서가 실제로 바뀐 건). fr·to 는 SQL 식."""
    comp = "\n   AND e.COMP_CODE = b.COMP_CODE" if with_comp_join else ""
    return f"""
SELECT b.START_DATE              AS change_date
     , b.CRE_DTM                 AS cre_dtm
     , b.ASG_HIST_ID             AS asg_hist_id
     , e.EMP_NO                  AS empno
     , e.EMP_NM                  AS emp_name
     , b.PREV_ORG_CODE           AS prev_dept_code
     , {_org_nm('b.PREV_ORG_CODE', 'b.PREV_END_DATE', "'[미등록] ' || b.PREV_ORG_CODE")} AS prev_dept_name
     , b.ORG_CODE                AS dept_code
     , {_org_nm('b.ORG_CODE', 'b.START_DATE', "'[미등록] ' || b.ORG_CODE")} AS dept_name
  FROM {_ASG_HIST}
  JOIN POSDXHR.HPA_HR_BAS_INFO e
    ON e.EMP_ID = b.EMP_ID{comp}
 WHERE b.START_DATE BETWEEN {fr} AND {to}
   AND b.PREV_ORG_CODE IS NOT NULL
   AND b.ORG_CODE <> b.PREV_ORG_CODE"""


# 부서이동자 서브쿼리 (권한 쿼리에서 d 로 씀) — 이동 전후 부서명은 코드 대체(미등록 표시 없음)
def _movers_sub(fr: str, to: str) -> str:
    return f"""
       (SELECT b.ASG_HIST_ID, b.CRE_DTM, e.COMP_CODE, e.EMP_NO, b.START_DATE
             , {_org_nm('b.ORG_CODE', 'b.START_DATE', 'b.ORG_CODE')} AS TO_DEPTNM
             , {_org_nm('b.PREV_ORG_CODE', 'b.PREV_END_DATE', 'b.PREV_ORG_CODE')} AS FROM_DEPTNM
          FROM {_ASG_HIST}
          JOIN POSDXHR.HPA_HR_BAS_INFO e
            ON e.EMP_ID    = b.EMP_ID
           AND e.COMP_CODE = b.COMP_CODE
         WHERE b.PREV_ORG_CODE IS NOT NULL
           AND b.ORG_CODE <> b.PREV_ORG_CODE
           AND b.START_DATE BETWEEN {fr} AND {to}
       ) d"""


def _resign(emp_cond: str, isg_cond: str) -> str:
    """퇴사자 (임직원 + 협력직). emp_cond·isg_cond: 각 블록의 기간 조건"""
    return f"""
SELECT t.GUBUN AS gubun, t.EMP_NO AS empno, t.EMP_NM AS emp_name
     , t.ORG_CODE AS dept_code, t.ORG_NM AS dept_name, t.RETIRE_DATE AS change_date
  FROM (
        /* 임직원 퇴직자 */
        SELECT N'임직원' AS GUBUN, e.EMP_NO, e.EMP_NM, e.ORG_CODE
             , COALESCE(
                 (SELECT MAX(o.ORG_NM) KEEP (DENSE_RANK LAST ORDER BY o.START_DATE)
                    FROM POSDXHR.HOM_ORG_DTL_INFO o
                   WHERE o.COMP_CODE = e.COMP_CODE AND o.ORG_CODE = e.ORG_CODE
                     AND o.START_DATE <= e.RETIRE_DATE),
                 (SELECT MIN(o.ORG_NM) KEEP (DENSE_RANK FIRST ORDER BY o.START_DATE)
                    FROM POSDXHR.HOM_ORG_DTL_INFO o
                   WHERE o.COMP_CODE = e.COMP_CODE AND o.ORG_CODE = e.ORG_CODE
                     AND o.START_DATE > e.RETIRE_DATE),
                 N'[미등록] ' || e.ORG_CODE) AS ORG_NM
             , e.RETIRE_DATE
          FROM POSDXHR.HPA_HR_BAS_INFO e
         WHERE e.COMP_CODE = 'dx'
           AND e.INOFFC_STAT_CODE = '90'
           AND REGEXP_LIKE(e.RETIRE_DATE, '^(19|20)[0-9]{{6}}$'){emp_cond}
        UNION ALL
        /* 협력직 퇴직자 (계약종료일, 없으면 최종수정일) */
        SELECT N'협력직', c.SABUN_CD, c.K_NAME, c.DEPTCODE, c.DEPTNAME
             , TO_NCHAR(NVL(c.END_DATE_ACTIVE, c.LAST_UPDATED_DATE), 'YYYYMMDD')
          FROM POSDXHR.CBO_SA_ISG_EMPMST c
         WHERE {isg_cond}
       ) t"""


# ── 권한 보유자 (r) ──────────────────────────────────────────
_PMS_HOLDERS = """
       (SELECT /*+ NO_MERGE */
               userg."grp_ath_cd"   AS GRP_ATH_CD
             , grp."grp_ath_nm"     AS GRP_ATH_NM
             , emp."empno"          AS EMPNO
             , emp."emp_nm"         AS EMP_NM
             , userg."ath_begin_de" AS ATH_BEGIN_DE
             , userg."ath_end_de"   AS ATH_END_DE
          FROM "proj"."cm_user_rgt_grp"@DXHRT_BPMT1 userg
             , "proj"."cm_rgt_grp"@DXHRT_BPMT1      grp
             , "proj"."cm_emp"@DXHRT_BPMT1          emp
         WHERE userg."grp_ath_cd" = grp."grp_ath_cd"
           AND userg."emp_id"     = emp."emp_id"
           AND (   userg."grp_ath_cd" LIKE 'CM0%'
                OR userg."grp_ath_cd" LIKE 'POM%'
                OR userg."grp_ath_cd" LIKE 'PMS%')
           AND userg."grp_ath_cd" NOT IN ('CM0001', 'PMS_AU10', 'POM_AU00')
       ) r"""

_IHR_HOLDERS = """
       (SELECT HABU.COMP_CODE         AS COMP_CODE
             , HABU.AUTH_GRP_CODE     AS GRP_ATH_CD
             , HAG.AUTH_GRP_KOR_NM    AS GRP_ATH_NM
             , USR.EMP_NO             AS EMPNO
             , USR.USR_NM             AS EMP_NM
             , HABU.START_DATE        AS ATH_BEGIN_DE
             , HABU.END_DATE          AS ATH_END_DE
          FROM POSDXHR.HSY_AUTH_BY_USR HABU
             , POSDXHR.HSY_AUTH_GRP    HAG
             , POSDXHR.HSY_USR         USR
         WHERE HABU.COMP_CODE     = HAG.COMP_CODE
           AND HABU.AUTH_GRP_CODE = HAG.AUTH_GRP_CODE
           AND USR.COMP_CODE      = HABU.COMP_CODE
           AND USR.USR_ID         = HABU.USR_ID
           AND HABU.COMP_CODE     = 'dx'
           AND HABU.AUTH_GRP_CODE NOT IN ('private', 'mobile_general')   /* 기본권한 제외 */
       ) r"""


def _epro_holders(hist_cond: str, union: str = "UNION ALL") -> str:
    """전자조달 현재 권한 + 권한 이력(mode A=부여, R=회수). hist_cond: 이력 쪽 추가 조건"""
    return f"""
       (SELECT /*+ NO_MERGE */
               b."role_nm"                          AS ROLE_NM
             , b."role_cd"                          AS ROLE_CD
             , c."usr_id"                           AS USR_ID
             , c."usr_nm"                           AS USR_NM
             , TO_CHAR(a."reg_dt", 'YYYYMMDD')      AS ATH_REG_DE
             , CAST(NULL AS VARCHAR2(10))           AS ATH_RTRV_DE
             , 'N'                                  AS HIST_YN
             , CAST(NULL AS DATE)                   AS HIST_REG_DT
          FROM "epro"."esaaurp"@DXHRT_BPMT1 a
             , "epro"."esaaurh"@DXHRT_BPMT1 b
             , "epro"."esauser"@DXHRT_BPMT1 c
         WHERE b."sys_id"  = 'EMRO'
           AND a."sys_id"  = b."sys_id"  AND a."role_cd" = b."role_cd"
           AND a."sys_id"  = c."sys_id"  AND a."usr_id"  = c."usr_id"
           AND a."sts" <> 'D' AND b."sts" <> 'D' AND c."sts" <> 'D'
           AND c."usr_cls" = 'B'
           AND NVL(c."use_yn", 'N') = 'Y'
           AND b."use_yn"  = 'Y'
           AND b."role_cd" <> 'PR001'
        {union}
        SELECT b."role_nm"
             , b."role_cd"
             , c."usr_id"
             , c."usr_nm"
             , DECODE(a."mode", 'A', TO_CHAR(a."reg_dt", 'YYYYMMDD'))
             , DECODE(a."mode", 'R', TO_CHAR(a."reg_dt", 'YYYYMMDD'))
             , 'Y'
             , a."reg_dt"
          FROM "epro"."esaaurp_l"@DXHRT_BPMT1 a
             , "epro"."esaaurh"@DXHRT_BPMT1   b
             , "epro"."esauser"@DXHRT_BPMT1   c
         WHERE b."sys_id"  = 'EMRO'
           AND a."sys_id"  = b."sys_id"  AND a."role_cd" = b."role_cd"
           AND a."sys_id"  = c."sys_id"  AND a."usr_id"  = c."usr_id"
           AND b."sts" <> 'D' AND c."sts" <> 'D'
           AND c."usr_cls" = 'B'
           AND NVL(c."use_yn", 'N') = 'Y'
           AND b."use_yn"  = 'Y'
           AND b."role_cd" <> 'PR001'{hist_cond}
       ) r"""


_GRP_COLS = """
SELECT d.START_DATE   AS change_date
     , r.GRP_ATH_NM   AS role_name
     , r.GRP_ATH_CD   AS role_code
     , r.EMPNO        AS empno
     , r.EMP_NM       AS emp_name
     , r.ATH_BEGIN_DE AS reg_date
     , r.ATH_END_DE   AS revoke_date
     , d.TO_DEPTNM    AS dept_name
     , d.FROM_DEPTNM  AS prev_dept_name"""

_EPRO_COLS = """
SELECT DISTINCT
       d.START_DATE   AS change_date
     , r.ROLE_NM      AS role_name
     , r.ROLE_CD      AS role_code
     , r.USR_ID       AS empno
     , r.USR_NM       AS emp_name
     , r.ATH_REG_DE   AS reg_date
     , r.ATH_RTRV_DE  AS revoke_date
     , d.TO_DEPTNM    AS dept_name
     , d.FROM_DEPTNM  AS prev_dept_name"""


# ──────────────────────────────────────────────────────────────
# 일간 쿼리 — 발령적용일 7일 전 ~ 어제 (소급발령 포함), 권한은 오늘 유효한 것
# ──────────────────────────────────────────────────────────────
_D_FR, _D_TO = "TO_CHAR(SYSDATE - 7, 'YYYYMMDD')", "TO_CHAR(SYSDATE - 1, 'YYYYMMDD')"
_TODAY = "TO_CHAR(SYSDATE, 'YYYYMMDD')"

_Q_DAILY_RESIGN = _resign(
    emp_cond=f"\n           AND e.RETIRE_DATE BETWEEN {_D_FR} AND {_D_TO}",
    isg_cond="""(   (    c.END_DATE_ACTIVE >= TRUNC(SYSDATE) - 7              -- 계약종료 7일 이내
                    AND c.END_DATE_ACTIVE <  TRUNC(SYSDATE))
                OR (    c.END_DATE_ACTIVE IS NULL                            -- 종료일 없이 사용중지
                    AND c.ENABLE_FLAG = 'N'
                    AND c.LAST_UPDATED_DATE >= TRUNC(SYSDATE) - 7
                    AND c.LAST_UPDATED_DATE <  TRUNC(SYSDATE)))
           AND NOT EXISTS (                                                  -- 재계약으로 재직 중이면 제외
                   SELECT 1
                     FROM POSDXHR.CBO_SA_ISG_EMPMST x
                    WHERE x.SABUN_CD    = c.SABUN_CD
                      AND x.ROWID      <> c.ROWID
                      AND x.ENABLE_FLAG = 'Y'
                      AND (x.END_DATE_ACTIVE IS NULL OR x.END_DATE_ACTIVE >= TRUNC(SYSDATE)))""",
) + "\n ORDER BY t.RETIRE_DATE, t.GUBUN, t.EMP_NO"

_Q_DAILY_DEPT = _dept_movers(_D_FR, _D_TO) + "\n ORDER BY b.START_DATE, e.EMP_NO"

_Q_DAILY_PMS = f"""{_GRP_COLS}
  FROM {_PMS_HOLDERS}
     , {_movers_sub(_D_FR, _D_TO)}
 WHERE r.EMPNO = d.EMP_NO
   AND (r.ATH_END_DE   IS NULL OR r.ATH_END_DE   >= {_TODAY})   -- 오늘 유효한 권한
   AND (r.ATH_BEGIN_DE IS NULL OR r.ATH_BEGIN_DE <= {_TODAY})
 ORDER BY 1, 4, 3"""

_Q_DAILY_IHR = f"""{_GRP_COLS}
  FROM {_IHR_HOLDERS}
     , {_movers_sub(_D_FR, _D_TO)}
 WHERE r.EMPNO     = d.EMP_NO
   AND r.COMP_CODE = d.COMP_CODE
   AND (r.ATH_END_DE   IS NULL OR r.ATH_END_DE   >= {_TODAY})   -- 오늘 유효한 권한
   AND (r.ATH_BEGIN_DE IS NULL OR r.ATH_BEGIN_DE <= {_TODAY})
 ORDER BY 1, 4, 3"""

_Q_DAILY_EPRO = f"""{_EPRO_COLS}
  FROM {_epro_holders(chr(10) + '           AND a."reg_dt" >= TRUNC(SYSDATE) - 7            -- 최근 7일 이력', 'UNION')}
     , {_movers_sub(_D_FR, _D_TO)}
 WHERE r.USR_ID = d.EMP_NO
 ORDER BY 1, 4, 3"""


# ──────────────────────────────────────────────────────────────
# 월간 쿼리 — 회차 월 1일 ~ 말일
# ──────────────────────────────────────────────────────────────
def _monthly_dept(ym: str) -> str:
    fr, to = _month_range(ym)
    return _dept_movers(f"'{fr}'", f"'{to}'", with_comp_join=False) + "\n ORDER BY b.START_DATE, e.EMP_NO"


def _monthly_resign(ym: str) -> str:
    fr, to = _month_range(ym)
    return _resign(
        emp_cond="",
        isg_cond="""c.END_DATE_ACTIVE < TRUNC(SYSDATE) + 1                   -- 종료일 지난 건 (Y/N 무관)
            OR (c.END_DATE_ACTIVE IS NULL AND c.ENABLE_FLAG = 'N')      -- 종료일 없이 사용중지된 건""",
    ) + f"\n WHERE t.RETIRE_DATE BETWEEN '{fr}' AND '{to}'\n ORDER BY t.RETIRE_DATE, t.GUBUN, t.EMP_NO"


# 권한 회수 확인 기준: 오늘 - 20일 이 속한 달의 1일 이후까지 유효했던 권한
_M_VALID = "TO_CHAR(SYSDATE - 20, 'YYYYMM') || '01'"


def _monthly_pms(ym: str) -> str:
    fr, to = _month_range(ym)
    return f"""{_GRP_COLS}
  FROM {_PMS_HOLDERS}
     , {_movers_sub(f"'{fr}'", f"'{to}'")}
 WHERE r.EMPNO = d.EMP_NO
   AND (r.ATH_END_DE IS NULL OR r.ATH_END_DE >= {_M_VALID})
 ORDER BY 1, 4, 3"""


def _monthly_ihr(ym: str) -> str:
    fr, to = _month_range(ym)
    return f"""{_GRP_COLS}
  FROM {_IHR_HOLDERS}
     , {_movers_sub(f"'{fr}'", f"'{to}'")}
 WHERE r.EMPNO     = d.EMP_NO
   AND r.COMP_CODE = d.COMP_CODE
   AND (r.ATH_END_DE IS NULL OR r.ATH_END_DE >= {_M_VALID})
 ORDER BY 1, 4, 3"""


def _monthly_epro(ym: str) -> str:
    fr, to = _month_range(ym)
    return f"""{_EPRO_COLS}
  FROM {_epro_holders('')}
     , {_movers_sub(f"'{fr}'", f"'{to}'")}
 WHERE r.USR_ID = d.EMP_NO
   AND (r.HIST_YN = 'N' OR r.HIST_REG_DT >= TO_DATE('{fr}', 'YYYYMMDD'))   -- 권한이력: 회차 시작일 이후
 ORDER BY 1, 4, 3"""


# ──────────────────────────────────────────────────────────────
# 일간 수집 (UPSERT)
# ──────────────────────────────────────────────────────────────
def _resign_type(r: dict) -> str:
    return "퇴직자(협력)" if (r.get("gubun") or "").strip() == "협력직" else "퇴직자"


def collect_daily(db: Session) -> dict:
    today = date.today()
    logger.info("일간 수집 시작 date=%s", today)

    # (이름, SQL, 행 → record_type)
    tasks = [
        ("퇴직자",      _Q_DAILY_RESIGN, _resign_type),
        ("부서변경자",  _Q_DAILY_DEPT,   lambda r: "부서변경자"),
        ("HR권한",      _Q_DAILY_IHR,    lambda r: "HR권한"),
        ("전자조달권한", _Q_DAILY_EPRO,  lambda r: "전자조달권한"),
        ("PMS권한",     _Q_DAILY_PMS,    lambda r: "PMS권한"),
    ]

    total_upserted = 0
    task_results: list[dict] = []

    for name, sql, rtype in tasks:
        try:
            rows = tibero.query(sql)
            for r in rows:
                _upsert_daily(db, rtype(r), r, today)
                total_upserted += 1
            task_results.append({"type": name, "ok": True, "count": len(rows)})
            logger.info("  [%s] %d건 수집 완료", name, len(rows))
        except Exception as e:
            db.rollback()
            task_results.append({"type": name, "ok": False, "error": str(e)})
            logger.warning("  [%s] 수집 실패: %s", name, e)
        else:
            db.commit()

    logger.info("일간 수집 완료 — 총 %d건 UPSERT", total_upserted)
    return {"upserted": total_upserted, "date": str(today), "tasks": task_results}


def _upsert_daily(db: Session, record_type: str, r: dict, today: date):
    change_date = _parse_date(r.get("change_date"))
    if not change_date:
        logger.warning("  [%s] 날짜 없는 행 건너뜀: %s", record_type, r)
        return
    role_code = r.get("role_code") or None
    values = {
        "record_type":    record_type,
        "empno":          str(r.get("empno") or ""),
        "emp_name":       r.get("emp_name"),
        "change_date":    change_date,
        "dept_code":      r.get("dept_code"),
        "dept_name":      r.get("dept_name"),
        "prev_dept_code": r.get("prev_dept_code"),
        "prev_dept_name": r.get("prev_dept_name"),
        "role_code":      role_code,
        "role_key":       role_code or "-",
        "role_name":      r.get("role_name"),
        "reg_date":       _parse_date(r.get("reg_date")),
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
# 월간 수집 (UPSERT — 사용자가 입력한 SR·비고는 보존)
# ──────────────────────────────────────────────────────────────
def collect_monthly(db: Session, period_id: int, year_month: str) -> dict:
    logger.info("월간 수집 시작 year_month=%s period_id=%s", year_month, period_id)
    tasks = [
        ("공통",   _monthly_dept(year_month)),
        ("퇴사자", _monthly_resign(year_month)),
        ("HR",     _monthly_ihr(year_month)),
        ("PMS",    _monthly_pms(year_month)),
        ("EPRO",   _monthly_epro(year_month)),
    ]

    total = 0
    task_results: list[dict] = []
    for system_code, sql in tasks:
        try:
            rows = tibero.query(sql)
            if system_code == "퇴사자":       # 구분(임직원/협력직)은 권한 칸에 담아 화면에 표시
                for r in rows:
                    r["role_code"] = r["role_name"] = (r.get("gubun") or "").strip() or None
            n = _bulk_upsert_monthly(db, period_id, system_code, rows)
            db.commit()
            total += n
            task_results.append({"code": system_code, "ok": True, "count": n})
            logger.info("  [%s] %d건 수집 완료", system_code, n)
        except Exception as e:
            db.rollback()
            task_results.append({"code": system_code, "ok": False, "error": str(e)})
            logger.warning("  [%s] 수집 실패: %s", system_code, e)

    synced = _sync_sr_from_daily(db, period_id, year_month)
    if synced:
        db.commit()
        logger.info("일간→월간 SR 자동매핑 %d건", synced)

    logger.info("월간 수집 완료 — 총 %d건 UPSERT", total)
    return {"upserted": total, "year_month": year_month, "tasks": task_results, "sr_synced": synced}


def _monthly_values(period_id: int, system_code: str, r: dict) -> dict:
    role_code = r.get("role_code") or None
    return {
        "period_id":      period_id,
        "system_code":    system_code,
        "empno":          str(r.get("empno") or ""),
        "emp_name":       r.get("emp_name"),
        "change_date":    _parse_date(r.get("change_date")),
        "dept_code":      r.get("dept_code"),
        "dept_name":      r.get("dept_name"),
        "prev_dept_code": r.get("prev_dept_code"),
        "prev_dept_name": r.get("prev_dept_name"),
        "role_code":      role_code,
        "role_key":       role_code or "-",
        "role_name":      r.get("role_name"),
        "reg_date":       _parse_date(r.get("reg_date")),
        "revoke_date":    _no_end(_parse_date(r.get("revoke_date"))),
    }


def _no_end(d):
    """종료일 9999-12-31 은 '종료 없음' → 회수일 없음"""
    return None if d and d.year >= 9999 else d


def _bulk_upsert_monthly(db: Session, period_id: int, system_code: str, rows: list[dict]) -> int:
    """월간 레코드 일괄 UPSERT.
    ON CONFLICT DO UPDATE 는 한 명령에서 같은 키를 두 번 건드릴 수 없으므로
    (period_id, system_code, empno, role_key) 기준으로 미리 합친다.
    같은 키가 여러 행이면 빈 값만 뒤 행 값으로 채운다
    (예: 전자조달 현재 권한 행의 등록일 + 권한 이력 행의 회수일).
    """
    deduped: dict[tuple, dict] = {}
    for r in rows:
        v = _monthly_values(period_id, system_code, r)
        key = (v["period_id"], v["system_code"], v["empno"], v["role_key"])
        if key in deduped:
            cur = deduped[key]
            for k, val in v.items():
                if cur.get(k) is None and val is not None:
                    cur[k] = val
        else:
            deduped[key] = v

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
            # sr_no / sr_title / remark 는 사용자 입력값 보존
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
    """
    year, month = map(int, year_month.split("-"))
    start = date(year, month, 1)
    end   = date(year, month, calendar.monthrange(year, month)[1])

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
        monthly = (
            db.query(MonthlyRecord)
            .filter_by(period_id=period_id, system_code=_RTYPE_TO_SYSTEM[d.record_type],
                       empno=d.empno, role_key=d.role_key)
            .first()
        )
        if monthly and not monthly.sr_no:
            monthly.sr_no        = d.sr_no
            monthly.sr_title     = d.sr_title
            monthly.sr_work_type = d.sr_work_type
            synced += 1
    return synced
