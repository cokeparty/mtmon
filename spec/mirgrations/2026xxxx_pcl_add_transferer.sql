-- ============================================================
--  프로그램변경: 이관자(transferer) 컬럼 추가
--  - 화면/엑셀에서 '이관자' 칼럼 편집·저장에 사용 (디폴트 표시값: 이기헌)
--  - 기존 결재 3컬럼(approval_*)은 그대로, NULL 이면 화면에서 디폴트 적용
--  실행: psql "$DATABASE_URL" -f scripts/migrations/2026xxxx_pcl_add_transferer.sql
-- ============================================================
ALTER TABLE program_change.program_change_log
    ADD COLUMN IF NOT EXISTS transferer VARCHAR(50);
