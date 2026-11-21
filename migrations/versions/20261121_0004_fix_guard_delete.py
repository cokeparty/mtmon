"""마감 보호 트리거가 DELETE 를 조용히 무시하던 버그 수정

BEFORE DELETE 트리거에서 NEW 는 NULL 이라 RETURN NEW 이면 삭제가 취소된다(오류 없이 0건).
→ 열린 회차의 삭제(CSV 재업로드 시 기존 행 삭제 등)가 되지 않아 중복이 쌓였다.
수정: RETURN COALESCE(NEW, OLD)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-21
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def _guard_fn(ret: str) -> str:
    return f"""
CREATE OR REPLACE FUNCTION common.guard_closed_period()
RETURNS TRIGGER AS $$
DECLARE
    v_status VARCHAR(10);
    v_pid    BIGINT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_pid := OLD.period_id;
    ELSE
        v_pid := NEW.period_id;
    END IF;
    SELECT status INTO v_status FROM common.monitoring_period WHERE id = v_pid;
    IF v_status = 'closed' THEN
        RAISE EXCEPTION '마감된 회차(period_id=%)는 변경할 수 없습니다.', v_pid
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN {ret};
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    op.execute(_guard_fn("COALESCE(NEW, OLD)"))


def downgrade() -> None:
    op.execute(_guard_fn("NEW"))
