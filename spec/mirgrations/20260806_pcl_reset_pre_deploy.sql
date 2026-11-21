-- ============================================================
--  프로그램변경: '이관전 승인' 고정값 리셋 (버그 P-5)
--  배경:
--    기존 배치가 approval_pre_deploy 컬럼에 O/X 확정값을 저장 → 화면/엑셀이
--    저장값을 우선(_pick)하여, 나중에 SR을 올바르게 입력해도 재계산되지 않음.
--  조치:
--    기존 행의 approval_pre_deploy 를 NULL 로 리셋한다. 이후로는 저장값이 없으면
--    현재 작업승인일 vs 이관일(날짜 기준, 당일이면 O)로 라이브 계산되어 self-healing.
--    (수정 후 배치는 이 컬럼을 더 이상 채우지 않음.)
--  주의: 과거에 수동으로 지정한 O/X 가 있었다면 함께 초기화됨(해당 컬럼은 통상 수동지정 없음).
--  실행: psql "$DATABASE_URL" -f spec/mirgrations/20260806_pcl_reset_pre_deploy.sql
-- ============================================================
UPDATE program_change.program_change_log
    SET approval_pre_deploy = NULL
    WHERE approval_pre_deploy IS NOT NULL;
