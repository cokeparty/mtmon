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
    work_req_date as"작업요청일(데이터추출)",
	work_conf_date as "작업완료일(데이터추출, 권한신청)",
	work_appr_date as "변경승인일",
	apply_appr_date as "반영승인일",
    release_ok_confirm_date as "자원이행확인일",
    sr_close_date as "SR종료일(원본)"
FROM sr_master;