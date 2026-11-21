
테이블	역할	관계
monitoring_period	월 회차 (open/closed)	1 : N → program_change_log
server_config	시스템별 A서버(SSH)·B서버(NFS) 접속 설정	system_code로 program_change_log와 논리 연결
program_change_log	변경 리스트 본문 (17컬럼 + 매핑/판정 메타)	period_id FK → monitoring_period
program_change_log 컬럼 그룹

① xferlog 원본: log_month, log_day, log_time, deploy_time, file_name, full_path, deployer
② NFS 매핑 결과: nfs_path, nfs_mtime, map_type
③ SR DB 스냅샷: sr_no, sr_title, sr_work_type, sr_approved_at, sr_closed_at, sr_developer, sr_reviewer
④ 결재 3컬럼: approval_change_request, approval_user_test, approval_pre_deploy → 컬럼 존재, 값은 항상 NULL(빈값)
⑤ 판정: result, normal_yn, reason
⑥ 운영: remark, created_at, updated_at