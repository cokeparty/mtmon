"""계정 역할(role) 의 옛 CHECK 제약 제거

운영 DB 에는 소스 밖에서 직접 만든 CHECK 제약이 account.app_user.role 에 걸려 있어
operator / reviewer / developer / viewer 4개 값만 허용했다.
→ administrator 지정, 역할관리에서 추가한 역할 부여가 모두 막힌다.

0006 부터 역할 값은 account.role 참조 제약(fk_app_user_role)으로 검사하므로
role 칼럼을 검사하는 CHECK 제약은 이름과 상관없이 모두 지운다 (없으면 아무것도 안 함).

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-22
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
DO $$
DECLARE c record;
BEGIN
    FOR c IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_attribute att
          ON att.attrelid = con.conrelid AND att.attnum = ANY (con.conkey)
        WHERE con.conrelid = 'account.app_user'::regclass
          AND con.contype = 'c'
          AND att.attname = 'role'
    LOOP
        RAISE NOTICE 'drop check constraint account.app_user.%', c.conname;
        EXECUTE format('ALTER TABLE account.app_user DROP CONSTRAINT %I', c.conname);
    END LOOP;
END $$;
""")


def downgrade() -> None:
    # 옛 제약은 이름 · 내용이 서버마다 달라 되살리지 않는다 (역할 검사는 fk_app_user_role 이 계속 담당)
    pass
