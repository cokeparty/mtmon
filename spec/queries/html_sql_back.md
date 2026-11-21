-- ============================================================


     
-- 1) 최근 퇴직자 현황 (인사 이력 기준)


     
-- ============================================================


     
SELECT


     
a.revision_date          AS 데이터변경일,


     
a.empcd                  AS 사번,


     
a.hname                  AS 이름,


     
a.deptcd                 AS 부서코드,


     
d.deptnm                 AS 부서명,


     
a.retdat                 AS 퇴직일


     
FROM is_pe01_history@prod_view a,


     
is_bm02@prod_view         d


     
WHERE a.revision_date >= (SYSDATE - 7)


     
AND a.retdat IS NOT NULL


     
AND a.deptcd = d.deptcd


     
 


     
UNION ALL


     
-- ============================================================


     
-- 1-2) 최근 퇴직자 현황 (ISG 사원 마스터 기준)


     
-- ============================================================


     
SELECT


     
i.end_date_active        AS 데이터변경일,


     
i.sabun_cd               AS 사번,


     
i.k_name                 AS 이름,


     
i.deptcode               AS 부서코드,


     
i.deptname               AS 부서명,


     
i.end_date_active        AS 퇴직일


     
FROM cbou.cbo_sa_isg_empmst@prod_view i


     
WHERE i.enable_flag = 'Y'


     
AND i.end_date_active >= (SYSDATE - 7)


     
AND i.end_date_active < SYSDATE


     
 


     
UNION ALL


     
-- ============================================================


     
-- 2) 최근 부서변경자 현황


     
-- ============================================================


     
SELECT DISTINCT


     
revision_date            AS 부서변경일,


     
empcd                    AS 사번,


     
hname                    AS 이름,


     
to_deptcd                AS 부서코드,


     
to_deptnm                AS 부서명,


     
from_deptcd              AS 이전부서코드,


     
from_deptnm              AS 이전부서명


     
FROM apps.cbo_sa_dept_chg_7@prod_view


     
 


     
UNION ALL


     
-- ============================================================


     
SELECT DISTINCT


     
TO_CHAR(dept_chg.revision_date, 'yyyy.mm.dd') AS 부서변경일,


     
h.deptnm                                      AS 부서명,


     
g.empcd                                       AS 사번,


     
g.hname                                       AS 이름,


     
dept_chg.from_deptnm                          AS 이전부서명,


     
d.responsibility_name                         AS responsibility,


     
TO_CHAR(a.start_date, 'yyyy.mm.dd') AS 권한시작일,


     
TO_CHAR(a.creation_date, 'yyyy.mm.dd') AS 권한부여일,


     
TO_CHAR(last_use.last_use_dt, 'yyyy.mm.dd') AS 마지막권한사용일


     
FROM (


     
SELECT u.user_id, u.user_name,


     
wur.role_orig_system_id  AS responsibility_id,


     
fa.application_id        AS responsibility_application_id,


     
fsg.security_group_id    AS security_group_id,


     
wura.start_date          AS start_date,


     
wura.end_date            AS end_date,


     
wura.creation_date       AS creation_date


     
FROM fnd_user                    u,


     
wf_user_role_assignments_v  wura,


     
wf_user_roles               wur,


     
fnd_application             fa,


     
fnd_security_groups         fsg


     
WHERE wura.user_name = u.user_name


     
AND u.start_date <= SYSDATE


     
AND NVL(u.end_date, SYSDATE) >= SYSDATE


     
AND wur.role_orig_system = 'FND_RESP'


     
AND wur.partition_id = 2


     
AND wura.role_name = wur.role_name


     
AND wura.user_name = wur.user_name


     
AND fa.application_short_name =


     
REPLACE(SUBSTR(wura.role_name,


     
INSTR(wura.role_name, '|', 1, 1) + 1,


     
(INSTR(wura.role_name, '|', 1, 2)


     
- INSTR(wura.role_name, '|', 1, 1) - 1)),


     
'%col', ':')


     
AND fsg.security_group_key =


     
REPLACE(SUBSTR(wura.role_name,


     
INSTR(wura.role_name, '|', 1, 3) + 1),


     
'%col', ':')


     
) a,


     
fnd_application_tl       c,


     
fnd_responsibility_tl    d,


     
fnd_responsibility       e,


     
is_pe01                  g,


     
is_bm02                  h,


     
( SELECT b.user_id, a.responsibility_id,


     
MAX(a.start_time) AS last_use_dt


     
FROM fnd_login_responsibilities a,


     
fnd_logins                 b


     
WHERE a.login_id = b.login_id


     
GROUP BY b.user_id, a.responsibility_id


     
) last_use,


     
( SELECT a.revision_date, a.empcd, a.hname,


     
a.deptcd AS to_deptcd, d.deptnm AS to_deptnm,


     
b.deptcd AS from_deptcd, e.deptnm AS from_deptnm


     
FROM is_pe01_history a,


     
is_pe01_history b,


     
is_bm02 d,


     
is_bm02 e


     
WHERE a.revision_date >= SYSDATE - 7


     
AND a.emp_id = b.emp_id


     
AND b.revision_num < a.revision_num


     
AND b.revision_num = (SELECT MAX(c.revision_num)


     
FROM is_pe01_history c


     
WHERE c.emp_id = b.emp_id


     
AND c.revision_num < a.revision_num)


     
AND a.deptcd <> b.deptcd


     
AND a.deptcd = d.deptcd


     
AND b.deptcd = e.deptcd


     
) dept_chg


     
WHERE a.start_date <= SYSDATE


     
AND NVL(a.end_date, SYSDATE) >= SYSDATE


     
AND a.responsibility_id = d.responsibility_id


     
AND a.responsibility_application_id = d.application_id


     
AND a.responsibility_id = e.responsibility_id


     
AND a.responsibility_application_id = e.application_id


     
AND a.responsibility_application_id = c.application_id


     
AND e.start_date <= SYSDATE


     
AND NVL(e.end_date, SYSDATE) >= SYSDATE


     
AND a.user_name = g.empcd


     
AND g.deptcd = h.deptcd


     
AND e.responsibility_key NOT IN (SELECT resp_key


     
FROM cbou.cbo_sa_resp_inst_t


     
WHERE gb_cd IN ('A', 'E'))


     
AND a.user_id = last_use.user_id(+)


     
AND a.responsibility_id = last_use.responsibility_id(+)


     
AND g.empcd = dept_chg.empcd


     
ORDER BY 부서변경일, 사번;



     
-- ============================================================


     
SELECT line_data, order_date


     
FROM cbo_sa_team_chg_list_v_inf@prod_view


     
 


     
UNION ALL


     
-- ============================================================


     
-- 4) 최근 부서변경자 전자조달(EMRO) 추가권한 삭제 확인


     
-- ============================================================


     
SELECT


     
dept_chg.revision_date   AS 부서변경일,


     
b.role_nm                AS 부여권한,


     
b.role_cd                AS role_cd,


     
c.usr_id                 AS 사번,


     
c.usr_nm                 AS 이름,


     
a.reg_dt                 AS 권한등록일,


     
dept_chg.to_deptnm       AS 부서명,


     
dept_chg.from_deptnm     AS 이전부서명


     
FROM epro.esaaurp a,


     
epro.esaaurh b,


     
epro.esauser c,


     
apps.cbo_sa_dept_chg_7@prod_view dept_chg


     
WHERE b.sys_id = 'EMRO'


     
AND a.usr_id = c.usr_id


     
AND a.sts <> 'D'


     
AND b.sts <> 'D'


     
AND c.sts <> 'D'


     
AND c.usr_cls = 'B'


     
AND NVL(c.use_yn, 'N') = 'Y'


     
AND a.sys_id = b.sys_id


     
AND a.sys_id = c.sys_id


     
AND a.role_cd = b.role_cd


     
AND b.use_yn = 'Y'


     
AND b.role_cd <> 'PR001'


     
AND a.usr_id = dept_chg.empcd


     
 


     
UNION ALL


     
-- ============================================================


     
-- 5) 최근 부서변경자 PMS 추가권한 삭제 확인


     
-- ============================================================


     
SELECT


     
dept_chg.revision_date   AS 부서변경일,


     
grp.grp_ath_nm           AS 부여권한,


     
userg.grp_ath_cd         AS role_cd,


     
emp.empno                AS 사번,


     
emp.emp_nm               AS 이름,


     
userg.ath_begin_de       AS 권한등록일,


     
dept_chg.to_deptnm       AS 부서명,


     
dept_chg.from_deptnm     AS 이전부서명


     
FROM proj.cm_user_rgt_grp userg,


     
proj.cm_rgt_grp       grp,


     
proj.cm_emp           emp,


     
apps.cbo_sa_dept_chg_7@prod_view dept_chg


     
WHERE userg.grp_ath_cd = grp.grp_ath_cd


     
AND userg.emp_id = emp.emp_id


     
AND SUBSTR(userg.grp_ath_cd, 1, 3) IN ('CM0', 'POM', 'PMS')


     
AND userg.grp_ath_cd NOT IN ('CM0001', 'PMS_AU10', 'POM_AU00')


     
AND emp.empno = dept_chg.empcd


     
AND NVL(userg.ath_end_de, TO_CHAR(SYSDATE, 'YYYYMMDD'))


     
>= TO_CHAR(SYSDATE, 'YYYYMMDD');

