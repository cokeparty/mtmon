-- ============================================================
--  프로그램변경: 작업승인일/SR종료일 시간까지 보존 (DATE → TIMESTAMP)
--  - 화면은 날짜+시각 인라인 표시, 엑셀은 날짜 표시(셀 클릭 시 시각 노출).
--  - 기존 DATE 값은 00:00:00 으로 승격됨(데이터 손실 없음).
--  실행: psql "$DATABASE_URL" -f spec/mirgrations/20260806_pcl_approved_closed_timestamp.sql
-- ============================================================
ALTER TABLE program_change.program_change_log
    ALTER COLUMN sr_approved_at TYPE TIMESTAMP USING sr_approved_at::timestamp,
    ALTER COLUMN sr_closed_at   TYPE TIMESTAMP USING sr_closed_at::timestamp;
