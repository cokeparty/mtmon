"""스키마 이름 변경 + 공통 스키마 분리

  program_change → program   (프로그램변경)
  dept_transfer  → depart    (부서이동자)
  auth           → account   (계정관리)
  dml, ddl       → 그대로
  monitoring_period · server_config · 공통 함수 → common (모듈 공통)

테이블을 옮기는 것이라 데이터·시퀀스·트리거·FK 는 그대로 유지된다.
※ 스키마 이름 변경은 스키마 소유자 권한이 필요하다(앱 접속 계정이 소유자여야 함).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _guard_fn(period_table: str) -> str:
    return f"""
CREATE OR REPLACE FUNCTION {period_table.split('.')[0]}.guard_closed_period()
RETURNS TRIGGER AS $$
DECLARE
    v_status VARCHAR(10);
    v_pid    BIGINT;
BEGIN
    v_pid := COALESCE(NEW.period_id, OLD.period_id);
    SELECT status INTO v_status FROM {period_table} WHERE id = v_pid;
    IF v_status = 'closed' THEN
        RAISE EXCEPTION '마감된 회차(period_id=%)는 변경할 수 없습니다.', v_pid
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS common")
    op.execute("ALTER TABLE program_change.monitoring_period SET SCHEMA common")
    op.execute("ALTER TABLE program_change.server_config     SET SCHEMA common")
    op.execute("ALTER FUNCTION program_change.set_updated_at()      SET SCHEMA common")
    op.execute("ALTER FUNCTION program_change.guard_closed_period() SET SCHEMA common")
    # 함수 본문 안의 테이블 경로를 새 위치로 교체
    op.execute(_guard_fn("common.monitoring_period"))

    op.execute("ALTER SCHEMA program_change RENAME TO program")
    op.execute("ALTER SCHEMA dept_transfer  RENAME TO depart")
    op.execute("ALTER SCHEMA auth           RENAME TO account")


def downgrade() -> None:
    op.execute("ALTER SCHEMA account RENAME TO auth")
    op.execute("ALTER SCHEMA depart  RENAME TO dept_transfer")
    op.execute("ALTER SCHEMA program RENAME TO program_change")
    op.execute("ALTER FUNCTION common.guard_closed_period() SET SCHEMA program_change")
    op.execute("ALTER FUNCTION common.set_updated_at()      SET SCHEMA program_change")
    op.execute(_guard_fn("program_change.monitoring_period"))
    op.execute("ALTER TABLE common.server_config     SET SCHEMA program_change")
    op.execute("ALTER TABLE common.monitoring_period SET SCHEMA program_change")
