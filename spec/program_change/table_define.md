순번	화면/엑셀 헤더	DB 컬럼	비고
1	월	log_month	xferlog
2	일	log_day	xferlog
3	시간	log_time	xferlog
4	파일명	file_name	basename(매핑 키)
5	경로	full_path	xferlog
6	이관자	deployer	xferlog
7	SR번호	sr_no	NFS 매핑 결과
8	SR제목	sr_title	SR DB
9	작업구분	sr_work_type	SR DB
10	작업승인일	sr_approved_at	SR DB
11	개발자	sr_developer	SR DB
12	검토수행자	sr_reviewer	SR DB
13	프로그램 변경요청·승인	approval_change_request	항상 빈칸(NULL)
14	사용자테스트	approval_user_test	항상 빈칸(NULL)
15	이관전 승인	approval_pre_deploy	항상 빈칸(NULL)
16	모니터링결과	result	정상/SR없음/경고/이상
17	정상여부	normal_yn	정상/이상