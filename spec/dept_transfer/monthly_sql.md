1. PMS 쿼리
```sql
       SELECT  'PMS',to_char(dept_chg.revision_date, 'yyyy.mm.dd'),  grp.grp_ath_nm,userg.grp_ath_cd,
        emp.empno, emp.emp_nm, userg.ath_begin_de,userg.ath_end_de, dept_chg.to_deptnm, dept_chg.from_deptnm
           FROM proj.cm_user_rgt_grp userg,
            proj.cm_rgt_grp grp,
            proj.cm_emp emp,
            apps.cbo_sa_dept_chg_1m@prod_view dept_chg
          WHERE userg.grp_ath_cd = grp.grp_ath_cd
          AND userg.emp_id = emp.emp_id 
          AND (substr(userg.grp_ath_cd, 1, 3) = ANY (ARRAY['CM0', 'POM', 'PMS']))
          AND (userg.grp_ath_cd <> ALL (ARRAY['CM0001', 'PMS_AU10', 'POM_AU00'])) 
          AND emp.empno = dept_chg.empcd 
          AND nvl(userg.ath_end_de, to_char(sysdate, 'YYYYMMDD')) >= to_char(sysdate - 20, 'YYYYMM') || '01'
```

2. HR 쿼리
```sql 
select distinct 'ERP',to_char(dept_chg.lstbaldat,'yyyy.mm.dd') "부서변경일",h.deptnm "부서명", g.empcd "사번", g.hname "이름", dept_chg.from_deptnm "이전 부서명",
d.responsibility_name "추가권한명",to_char(a.START_DATE,'yyyy.mm.dd') "권한 시작일",to_char(a.end_date,'yyyy.mm.dd') "권한 종료일",to_char(last_use.last_use_dt,'yyyy.mm.dd') "최근 사용일"
FROM (select U.user_id user_id , u.user_name user_name,wura.RESPONSIBILITY_APPLICATION_ID,wura.RESPONSIBILITY_ID,
wura.start_date START_DATE , wura.end_date END_DATE , wura.creation_date CREATION_DATE
from fnd_user u , FND_USER_RESP_GROUPS_DIRECT wura
where wura.user_id = u.user_id
and u.start_date <= sysdate and nvl(u.end_date,sysdate) >= to_date('20260501','yyyymmdd') --or u.end_date between to_date('20210201','yyyymmdd') and to_date('20210228','yyyymmdd'))
)a,
FND_Application_tl c,FND_RESPONSIBILITY_tl d,FND_RESPONSIBILITY e, is_pe01 g,is_bm02 h,
(select b.user_id,a.responsibility_id,max(a.start_time) last_use_dt
from fnd_login_responsibilities a,fnd_logins b where a.login_id = b.login_id
group by b.user_id,a.responsibility_id) last_use,
(select a.lstbaldat,a.empcd,a.hname,a.deptcd to_deptcd,d.deptnm to_deptnm,b.deptcd from_deptcd,e.deptnm from_deptnm
from is_pe01_history a,is_pe01_history b,is_bm02 d,is_bm02 e
where a.lstbaldat between to_date('20260501','yyyymmdd') and to_date('20260531','yyyymmdd')
and a.emp_id = b.emp_id and b.revision_num < a.revision_num
and b.revision_num = (select max(c.revision_num)
from is_pe01_history c
where c.emp_id = b.emp_id and c.revision_num < a.revision_num)
and a.deptcd <> b.deptcd and a.deptcd = d.deptcd and b.deptcd = e.deptcd) dept_chg
where a.start_date <= sysdate -- and nvl(a.end_date,sysdate) >= sysdate
and (nvl(a.end_date,sysdate) >= sysdate or a.end_date >= to_date('20260501','yyyymmdd'))
and a.responsibility_id = d.responsibility_id and a.responsibility_application_id = d.application_id
and a.responsibility_id = e.responsibility_id and a.responsibility_application_id = e.application_id
and a.responsibility_application_id = c.application_id and e.start_date <= sysdate
and nvl(e.end_date,sysdate) >= sysdate and a.user_name = g.empcd and g.deptcd = h.deptcd
and e.responsibility_key not in (select resp_key from cbou.cbo_sa_resp_inst_t where gb_cd in ('A','E'))
and a.user_id = last_use.user_id(+) and a.RESPONSIBILITY_ID = last_use.responsibility_id(+) and g.empcd = dept_chg.empcd -- and a.START_DATE < dept_chg.lstbaldat
```

3. 전자조달 쿼리
```sql
 SELECT '전자조달',to_char(dept_chg.revision_date, 'yyyy.mm.dd') "부서변경일",b.role_nm "권한명"
         , b.role_cd "권한코드", c.usr_id "사번",c.usr_nm "이름",to_char(a_1.reg_dt, 'YYYY.MM.DD') "권한등록일",
        null "권한회수일",dept_chg.to_deptnm "부서명",dept_chg.from_deptnm "이전부서명"
           FROM esaaurp a_1,esaaurh b,esauser c,apps.cbo_sa_dept_chg_1m@prod_view dept_chg
          WHERE b.sys_id = 'EMRO' AND a_1.usr_id = c.usr_id AND a_1.sts <> 'D'
          AND b.sts <> 'D'  AND c.sts <> 'D' AND c.usr_cls = 'B'  AND nvl(c.use_yn, 'N') = 'Y'
          AND a_1.sys_id = b.sys_id AND a_1.sys_id = c.sys_id AND a_1.role_cd = b.role_cd
          AND b.use_yn = 'Y' AND b.role_cd <> 'PR001'  AND a_1.usr_id = dept_chg.empcd
union
SELECT '전자조달',to_char(dept_chg.revision_date, 'yyyy.mm.dd') "부서변경일",b.role_nm "권한명"
         , b.role_cd "권한코드", c.usr_id "사번",c.usr_nm "이름",decode(a_1.MODE,'A',to_char(a_1.reg_dt, 'YYYY.MM.DD'),null) "권한등록일",
        decode(a_1.MODE,'R',to_char(a_1.reg_dt, 'YYYY.MM.DD'),null) "권한회수일",dept_chg.to_deptnm "부서명",dept_chg.from_deptnm "이전부서명"
           FROM esaaurp_l a_1, esaaurh b,esauser c, apps.cbo_sa_dept_chg_1m@prod_view dept_chg
          WHERE b.sys_id = 'EMRO' AND a_1.usr_id = c.usr_id 
         -- AND a_1.sts <> 'D'
          AND b.sts <> 'D'  AND c.sts <> 'D'  AND c.usr_cls = 'B'  AND nvl(c.use_yn, 'N') = 'Y'
          AND a_1.sys_id = b.sys_id AND a_1.sys_id = c.sys_id AND a_1.role_cd = b.role_cd  AND b.use_yn = 'Y'
          AND b.role_cd <> 'PR001'  AND a_1.usr_id = dept_chg.empcd  and to_char(a_1.reg_dt,'YYYYMM') >= '202605';
```

4. 부서이동자 쿼리
```sql
select to_char(a.lstbaldat,'yyyy.mm.dd') "부서변경일", a.empcd "사번", a.hname "이름", a.deptcd "신규 부서코드",
       d.deptnm "신규 부서명" ,b.deptcd "이전 부서코드" ,e.deptnm  "이전 부서명"
from is_pe01_history a,is_pe01_history b,is_bm02 d,is_bm02 e
where a.lstbaldat between to_date('20260501','yyyymmdd') and to_date('20260531','yyyymmdd')
and a.emp_id = b.emp_id
and b.revision_num < a.revision_num
and b.revision_num = (select max(c.revision_num) from is_pe01_history c where c.emp_id = a.emp_id and c.revision_num < a.revision_num)
and a.deptcd <> b.deptcd
and a.deptcd = d.deptcd
and b.deptcd = e.deptcd
```