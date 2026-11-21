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
-- 3) 최근 부서변경자 HR 추가권한 삭제 확인
-- ============================================================
SELECT DISTINCT
    TO_CHAR(dept_chg.revision_date, 'yyyy.mm.dd') AS 부서변경일,
    h.deptnm                                      AS 부서명,
    g.empcd                                       AS 사번,
    g.hname                                       AS 이름,
    dept_chg.from_deptnm                          AS 이전부서명,
    d.responsibility_name                         AS responsibility,
    TO_CHAR(a.start_date, 'yyyy.mm.dd')           AS 권한시작일,
    TO_CHAR(a.creation_date, 'yyyy.mm.dd')        AS 권한부여일,
    TO_CHAR(last_use.last_use_dt, 'yyyy.mm.dd')   AS 마지막권한사용일
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
-- 3-2) HR 뷰 원본내용(EDB에서 DBLINK로 접근하는 부분인데 직접 정의를 찾은게 위의 쿼리)
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

-- ============================================================
-- 6) 뷰 원본 - 위의 쿼리들은 아래의 뷰 정의에서 분리함
-- ============================================================
-- epro.cbo_sa_team_chg_list_v source

CREATE OR REPLACE VIEW epro.cbo_sa_team_chg_list_v
AS SELECT a.line_data
   FROM ( SELECT (((('<html><head><meta http-equiv="Content-Type" content="text/html; charset=EUC-KR"><title>::: 퇴직/부서변경자 현황표  :::</title></head>'::text || '<body><H2><u>퇴직/부서변경자 현황표</u></h2><br>기준일시 : '::text) || to_char(sysdate - 7, 'yyyy.mm.dd'::character varying)::text) || ' ~ '::text) || to_char(sysdate, 'yyyy.mm.dd'::character varying)::text) || '<br>담 당 자 : 이후재(SysAdmin)<br>'::text AS line_data,
            10 AS order_date
           FROM dual
        UNION ALL
         SELECT '<br>1)최근 퇴직자 현황(OS acl, DB접근제어 계정 삭제 확인 필요)<br><table width="100%" border="5" cellspacing="1" cellpadding="1"><tr><td>데이터 변경일</td><td>사번</td>'::text || '<td>이름</td><td>부서코드</td><td>부서명</td><td>퇴직일</td></tr>'::text AS line_data,
            20 AS order_date
           FROM dual
        UNION ALL
         SELECT ((((((((((('<tr><td>'::text || to_char(a_1.revision_date, 'yyyy.mm.dd'::character varying)::text) || '</td><td>'::text) || a_1.empcd::text) || '</td><td>'::text) || a_1.hname::text) || '</td><td>'::text) || a_1.deptcd::text) || '</td><td>'::text) || d.deptnm::text) || '</td><td>'::text) || to_char(a_1.retdat, 'yyyy.mm.dd'::character varying)::text) || '</td></tr>'::text,
            30 AS order_date
           FROM is_pe01_history @ prod_view(emp_id numeric, revision_num numeric, revision_date timestamp without time zone, revision_type character varying(3), org_id numeric, empcd character varying(8), hname character varying(50), jname character varying(20), ename character varying(50), juminno character varying(13), sexgb character varying(1), compycd character varying(10), deptcd character varying(10), jikjgcd character varying(30), jikckcd character varying(30), jikwicd character varying(30), jikgubcd character varying(30), jikmucd character varying(30), supervisor_id numeric, add_deptcd character varying(10), add_jikckcd character varying(30), work_type character varying(30), rf_cardno character varying(30), work_area character varying(30), igentgb character varying(30), jeajikgb character varying(30), regulargb character varying(30), fstigentdat timestamp without time zone, igentdat timestamp without time zone, retdat timestamp without time zone, releasedat timestamp without time zone, midjsdat timestamp without time zone, lstbaldat timestamp without time zone, advancedat timestamp without time zone, raisedat timestamp without time zone, dispatdat timestamp without time zone, comebackdat timestamp without time zone, tempordat timestamp without time zone, reinstdat timestamp without time zone, expense_type character varying(30), paydiv character varying(30), salary_step numeric, baseamt numeric, seizure character varying(1), interdependence character varying(1), medyn character varying(1), medigrade numeric, medino character varying(20), medidiv character varying(20), medifymd timestamp without time zone, meditymd timestamp without time zone, medetc character varying(80), natyn character varying(1), natgrade numeric, natfymd timestamp without time zone, nattymd timestamp without time zone, natetc character varying(80), emplyn character varying(1), emplfymd timestamp without time zone, empltymd timestamp without time zone, empletc character varying(80), nojoyn character varying(1), bankcd1 character varying(30), payacntno1 character varying(20), payname1 character varying(80), bankcd2 character varying(30), payacntno2 character varying(20), payname2 character varying(80), wife_subtr character varying(1), suppcnt_20 numeric, suppcnt_60 numeric, handicap_cnt numeric, respectcnt_65 numeric, respectcnt_70 numeric, birthdat timestamp without time zone, birdgb character varying(1), marrdat timestamp without time zone, relicd character varying(30), interest character varying(80), speciality character varying(80), specialgb character varying(30), bohuncd character varying(30), bohunno character varying(30), handicap_type character varying(80), handicap_class character varying(10), hometel character varying(50), handpon character varying(50), office_phone character varying(50), hojuname character varying(20), hojurel character varying(30), hojujob character varying(80), hunpost character varying(7), hunaddr1 character varying(200), hunaddr2 character varying(200), bonpost character varying(7), bonaddr1 character varying(200), bonaddr2 character varying(200), resigb character varying(30), car_license character varying(30), email character varying(50), territory_code character varying(2), stay_period_from timestamp without time zone, stay_period_to timestamp without time zone, height numeric, weight numeric, sight_l numeric, sight_r numeric, blingb character varying(30), booldgb character varying(10), health_status character varying(1), health_desc character varying(240), body_size character varying(30), pants_size character varying(30), shoes_size character varying(30), mil_group character varying(30), mil_no_cause character varying(30), mil_class character varying(30), mil_grade character varying(30), mil_specialty character varying(30), mil_no character varying(30), mil_dis character varying(30), mil_from timestamp without time zone, mil_to timestamp without time zone, mil_section character varying(30), hr_person_id numeric, hr_apply_date timestamp without time zone, erp_user_id numeric, last_update_date timestamp without time zone, last_updated_by numeric, creation_date timestamp without time zone, created_by numeric, last_update_login numeric, division character varying(10), cost_center character varying(30), jiknung character varying(30), transdat timestamp without time zone, product_type character varying(30), rf_seq numeric, secigentdat timestamp without time zone, convert character varying(40), jikrecord numeric, old_igentdat timestamp without time zone, igent_position character varying(40), school_career character varying(40), sub_origin character varying(40), jik_allowance character varying(40), check_year_cal character varying(2), check_product character varying(2), hearing_l numeric, hearing_r numeric, got numeric, gop numeric, gpt numeric, colesterol numeric, bohun_dat timestamp without time zone, bohun_sub character varying(30), bohun_rel character varying(20), high_press numeric, low_press numeric, std_retcal_dat timestamp without time zone, total_dec character varying(50), year_salary numeric, work_section character varying(10), handicap_dat timestamp without time zone, jikgubcd_amt numeric, weight_id character varying(30), silpost character varying(7), siladdr1 character varying(200), siladdr2 character varying(200), handicap_yn character varying(3), reduction character varying(1), suppcnt_6 numeric, mediamt numeric, long_mediamt numeric, redrate numeric, natamt numeric, bonarea character varying(30), marrgb character varying(30), car_type character varying(30), bohun_name character varying(30), bohun_org character varying(30), regulargb_changedate timestamp without time zone, confirm_jikgub character varying(30), jikgub_initialdate timestamp without time zone, original_deptcd character varying(30), rgl_time_pay numeric, rgl_pay numeric, edusysgb character varying(1), insurance_company character varying(30), insurance_effective_date timestamp without time zone, fax_num character varying(30), medi_payrate numeric, six_sigma character varying(30), igentcgb character varying(1), advancedat2 timestamp without time zone, forg_tax_excpetion character varying(1), empgrade numeric, empamt numeric, accyn character varying(1), accgrade numeric, accamt numeric, old_compycd character varying(10), ex_career numeric, append_womyn character varying(21), append_bringcnt numeric, append_brother_20 numeric, car_owner_flag character varying(1), car_owner_start_date timestamp without time zone, car_owner_end_date timestamp without time zone, year_salary_y numeric, pay_context1 character varying(3000), sort_deptcd character varying(10), regulargb2 character varying(30), contract_end_date timestamp without time zone, role_change_date timestamp without time zone, duty_change_date timestamp without time zone, last_jikgub character varying(30), base_salary numeric, base_salary_y numeric, achieve_salary numeric, achieve_salary_y numeric, group_igentdat timestamp without time zone, dc_yn character varying(1), dc_ent_date timestamp without time zone, group_igent_name character varying(100), achieve_salary_f numeric, project_code character varying(30), achieve_salary_t numeric, etc_context character varying(3000), bhs_work_chg_flag character varying(1), year_salary_bhs numeric, base_salary_bhs numeric, achieve_salary_bhs numeric, achieve_salary_bhs_f numeric, achieve_salary_bhs_t numeric, year_salary_bhs_y numeric, base_salary_bhs_y numeric, achieve_salary_bhs_y numeric, pmo_flag character varying(1), achieve_grade_pay numeric, achieve_grade_pay_rate numeric, work_place_code character varying(10), set_id numeric, p4_called_name_up_date timestamp without time zone, p5_assign_date timestamp without time zone, p6_assign_date timestamp without time zone, jikgubcd_p character varying(30), pay_1e_yn character varying(1), pay_1d_yn character varying(1), pay_7h_yn character varying(1), pay_sch_yn character varying(1), pay_well_yn character varying(1), pay_abil_yn character varying(1), pay_73_yn character varying(1), pay_lun_yn character varying(1)) a_1,
            is_bm02 @ prod_view(org_id numeric, compycd character varying(10), deptcd character varying(10), pre_deptcd character varying(10), deptnm character varying(50), teamnm character varying(50), deptgb character varying(30), charge_emp_id numeric, enabled_flag character varying(1), last_update_date timestamp without time zone, last_updated_by numeric, creation_date timestamp without time zone, created_by numeric, last_update_login numeric, start_date_active timestamp without time zone, end_date_active timestamp without time zone, display_num numeric, fdeptnm character varying(300), edeptnm character varying(300), cost_center character varying(30), dept_area character varying(30), hr_organization_id numeric, expense_type character varying(30), cc_flag character varying(1), peer_enabled character varying(1), description character varying(100), if_exception character varying(1), yuncha_exception character varying(1), sm_org_flag character varying(1), info_share_flag character varying(1), execution_org_flag character varying(1), pm_assign_empcd character varying(6), ap_except_flag character varying(1), ep_if_out_flag character varying(1), fdeptnm2 character varying(300), old_cost_center character varying(30)) d
          WHERE a_1.revision_date >= (sysdate - 7) AND a_1.retdat IS NOT NULL AND a_1.deptcd::text = d.deptcd::text
        UNION ALL
         SELECT ((((((((((('<tr><td>'::text || to_char(i.end_date_active, 'yyyy.mm.dd'::character varying)::text) || '</td><td>'::text) || i.sabun_cd::text) || '</td><td>'::text) || i.k_name::text) || '</td><td>'::text) || i.deptcode::text) || '</td><td>'::text) || i.deptname::text) || '</td><td>'::text) || to_char(i.end_date_active, 'yyyy.mm.dd'::character varying)::text) || '</td></tr>'::text,
            40 AS order_date
           FROM cbou.cbo_sa_isg_empmst @ prod_view(sabun_cd character varying(6), k_name character varying(50), deptcode character varying(10), deptname character varying(50), title character varying(30), positionname character varying(20), positioncode character varying(2), job character varying(100), mail character varying(40), hp_no character varying(20), office_no character varying(50), home_no character varying(20), fax_no character varying(20), passwd character varying(20), new_sabun_cd character varying(10), new_mail character varying(30), grade character varying(30), grade_code character varying(6), field_agent character varying(2), enable_flag character varying(1), start_date_active timestamp without time zone, end_date_active timestamp without time zone, created_by character varying(20), creation_date timestamp without time zone, updated_by character varying(20), last_updated_date timestamp without time zone, sort_deptcd character varying(10), company_code character varying(20), company_name character varying(100), pcm_use_flag character varying(1)) i
          WHERE i.enable_flag::text = 'Y'::text AND i.end_date_active >= (sysdate - 7) AND i.end_date_active < sysdate
        UNION ALL
         SELECT '</table>[End Of Lines]<br>'::text AS text,
            50 AS order_date
           FROM dual
        UNION ALL
         SELECT '<br>2)최근 부서변경자 현황(OS acl, DB접근제어 계정 삭제 확인 필요)<br><table width="100%" border="5" cellspacing="1" cellpadding="1"><tr><td>부서변경일</td><td>사번</td>'::text || '<td>이름</td><td>부서코드</td><td>부서명</td><td>이전부서코드</td><td>이전부서명</td></tr>'::text AS line_data,
            60 AS order_date
           FROM dual
        UNION ALL
         SELECT DISTINCT ((((((((((((('<tr><td>'::text || to_char(cbo_sa_dept_chg_7.revision_date, 'yyyy.mm.dd'::character varying)::text) || '</td><td>'::text) || cbo_sa_dept_chg_7.empcd::text) || '</td><td>'::text) || cbo_sa_dept_chg_7.hname::text) || '</td><td>'::text) || cbo_sa_dept_chg_7.to_deptcd::text) || '</td><td>'::text) || cbo_sa_dept_chg_7.to_deptnm::text) || '</td><td>'::text) || cbo_sa_dept_chg_7.from_deptcd::text) || '</td><td>'::text) || cbo_sa_dept_chg_7.from_deptnm::text) || '</td></tr>'::text AS line_data,
            70 AS order_date
           FROM apps.cbo_sa_dept_chg_7 @ prod_view(revision_date timestamp without time zone, empcd character varying(8), hname character varying(50), to_deptcd character varying(10), to_deptnm character varying(50), from_deptcd character varying(10), from_deptnm character varying(50))
        UNION ALL
         SELECT '</table>[End Of Lines]<br>'::text AS text,
            80 AS order_date
           FROM dual
        UNION ALL
         SELECT cbo_sa_team_chg_list_v_inf.line_data,
            cbo_sa_team_chg_list_v_inf.order_date
           FROM cbo_sa_team_chg_list_v_inf @ prod_view(line_data character varying(388), order_date numeric)
        UNION ALL
         SELECT '<br>4)최근 부서변경자 전자조달 추가권한 삭제 확인<br><table width="100%" border="5" cellspacing="1" cellpadding="1"><tr><td>부서변경일</td><td>부여권한</td>'::text || '<td>role_cd</td><td>사번</td><td>이름</td><td>권한 등록일</td><td>부서명</td><td>이전부서명</td></tr>'::text AS line_data,
            120 AS order_date
           FROM dual
        UNION ALL
         SELECT ((((((((((((((('<tr><td>'::text || to_char(dept_chg.revision_date, 'yyyy.mm.dd'::character varying)::text) || '</td><td>'::text) || b.role_nm::text) || '</td><td>'::text) || b.role_cd::text) || '</td><td>'::text) || c.usr_id::text) || '</td><td>'::text) || c.usr_nm::text) || '</td><td>'::text) || to_char(a_1.reg_dt, 'yyyy.mm.dd'::character varying)::text) || '</td><td>'::text) || dept_chg.to_deptnm::text) || '</td><td>'::text) || dept_chg.from_deptnm::text) || '</td></tr>'::text,
            130 AS order_date
           FROM esaaurp a_1,
            esaaurh b,
            esauser c,
            apps.cbo_sa_dept_chg_7 @ prod_view(revision_date timestamp without time zone, empcd character varying(8), hname character varying(50), to_deptcd character varying(10), to_deptnm character varying(50), from_deptcd character varying(10), from_deptnm character varying(50)) dept_chg
          WHERE b.sys_id::text = 'EMRO'::text AND a_1.usr_id::text = c.usr_id::text AND a_1.sts <> 'D'::bpchar AND b.sts <> 'D'::bpchar AND c.sts <> 'D'::bpchar AND c.usr_cls::text = 'B'::text AND nvl(c.use_yn::character varying, 'N'::character varying)::text = 'Y'::text AND a_1.sys_id::text = b.sys_id::text AND a_1.sys_id::text = c.sys_id::text AND a_1.role_cd::text = b.role_cd::text AND b.use_yn = 'Y'::bpchar AND b.role_cd::text <> 'PR001'::text AND a_1.usr_id::text = dept_chg.empcd::text
        UNION ALL
         SELECT '</table>[End Of Lines]<br>'::text AS text,
            140 AS order_date
           FROM dual
        UNION ALL
         SELECT '<br>5)최근 부서변경자 PMS 추가권한 삭제 확인<br><table width="100%" border="5" cellspacing="1" cellpadding="1"><tr><td>부서변경일</td><td>부여권한</td>'::text || '<td>role_cd</td><td>사번</td><td>이름</td><td>권한 등록일</td><td>부서명</td><td>이전부서명</td></tr>'::text AS line_data,
            150 AS order_date
           FROM dual
        UNION ALL
         SELECT ((((((((((((((('<tr><td>'::text || to_char(dept_chg.revision_date, 'yyyy.mm.dd'::character varying)::text) || '</td><td>'::text) || grp.grp_ath_nm::text) || '</td><td>'::text) || userg.grp_ath_cd::text) || '</td><td>'::text) || emp.empno::text) || '</td><td>'::text) || emp.emp_nm::text) || '</td><td>'::text) || userg.ath_begin_de::text) || '</td><td>'::text) || dept_chg.to_deptnm::text) || '</td><td>'::text) || dept_chg.from_deptnm::text) || '</td></tr>'::text,
            160 AS order_date
           FROM proj.cm_user_rgt_grp userg,
            proj.cm_rgt_grp grp,
            proj.cm_emp emp,
            apps.cbo_sa_dept_chg_7 @ prod_view(revision_date timestamp without time zone, empcd character varying(8), hname character varying(50), to_deptcd character varying(10), to_deptnm character varying(50), from_deptcd character varying(10), from_deptnm character varying(50)) dept_chg
          WHERE userg.grp_ath_cd::text = grp.grp_ath_cd::text AND userg.emp_id = emp.emp_id AND (substr(userg.grp_ath_cd::text, 1::numeric, 3::numeric) = ANY (ARRAY['CM0'::text, 'POM'::text, 'PMS'::text])) AND (userg.grp_ath_cd::text <> ALL (ARRAY['CM0001'::text, 'PMS_AU10'::text, 'POM_AU00'::text])) AND emp.empno::text = dept_chg.empcd::text AND nvl(userg.ath_end_de, to_char(sysdate, 'YYYYMMDD'::character varying))::text >= to_char(sysdate, 'YYYYMMDD'::character varying)::text
        UNION ALL
         SELECT '</table>[End Of Lines]<br>'::text AS text,
            170 AS order_date
           FROM dual
        UNION ALL
         SELECT '</body></html>'::text AS text,
            190 AS order_date
           FROM dual) a
  ORDER BY a.order_date;