"""배치잡 목록 · 실행 이력 테이블

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-21
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS common.batch_job (
    job_id        VARCHAR(50)  PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    description   VARCHAR(500),
    schedule      VARCHAR(50)  NOT NULL,
    schedule_desc VARCHAR(100),
    active        BOOLEAN      NOT NULL DEFAULT TRUE,
    updated_at    TIMESTAMP    NOT NULL DEFAULT now()
);
COMMENT ON TABLE common.batch_job IS '배치잡 목록 (코드 정의를 앱 시작 시 동기화)';

CREATE TABLE IF NOT EXISTS common.batch_history (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id        VARCHAR(50)  NOT NULL,
    trigger_type  VARCHAR(10)  NOT NULL,
    triggered_by  VARCHAR(50),
    params        VARCHAR(200),
    scheduled_at  TIMESTAMP,
    started_at    TIMESTAMP    NOT NULL DEFAULT now(),
    finished_at   TIMESTAMP,
    status        VARCHAR(10)  NOT NULL DEFAULT 'running',
    summary       VARCHAR(1000),
    error_type    VARCHAR(100),
    error_message TEXT,
    error_detail  TEXT,
    host          VARCHAR(100)
);
CREATE INDEX IF NOT EXISTS idx_bh_job_started ON common.batch_history (job_id, started_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_bh_job_scheduled ON common.batch_history (job_id, scheduled_at)
    WHERE scheduled_at IS NOT NULL;
COMMENT ON TABLE  common.batch_history              IS '배치잡 실행 이력';
COMMENT ON COLUMN common.batch_history.trigger_type IS 'schedule=자동, manual=화면에서 실행';
COMMENT ON COLUMN common.batch_history.status       IS 'running|success|partial|failed';
COMMENT ON COLUMN common.batch_history.error_detail IS '트레이스백 전문';
""")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS common.batch_history")
    op.execute("DROP TABLE IF EXISTS common.batch_job")
