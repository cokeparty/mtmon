-- Migration: DDL 사유 및 편집 칼럼 추가
-- Date: 2026-06-29
-- 대상: ddl.ddl_log

ALTER TABLE ddl.ddl_log
  ADD COLUMN IF NOT EXISTS ddl_reason           VARCHAR(500),
  ADD COLUMN IF NOT EXISTS proc_change_approval VARCHAR(10)  DEFAULT 'O',
  ADD COLUMN IF NOT EXISTS user_test            VARCHAR(10)  DEFAULT 'O',
  ADD COLUMN IF NOT EXISTS pre_release_approval VARCHAR(10),
  ADD COLUMN IF NOT EXISTS developer            VARCHAR(100),
  ADD COLUMN IF NOT EXISTS releaser             VARCHAR(100) DEFAULT '이기헌',
  ADD COLUMN IF NOT EXISTS reviewer_name        VARCHAR(100) DEFAULT '노광환';

-- 기존 행 디폴트 채우기
UPDATE ddl.ddl_log
SET
  proc_change_approval = COALESCE(proc_change_approval, 'O'),
  user_test            = COALESCE(user_test,            'O'),
  releaser             = COALESCE(releaser,             '이기헌'),
  reviewer_name        = COALESCE(reviewer_name,        '노광환')
WHERE proc_change_approval IS NULL
   OR user_test            IS NULL
   OR releaser             IS NULL
   OR reviewer_name        IS NULL;
