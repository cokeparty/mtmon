"""administrator(관리자) 역할

  - 항상 모든 페이지 수정 권한 (권한표 행 없이 코드에서 처리 — core/permissions.py ADMIN_ROLE)
  - 앱 화면에서는 보이지 않고 부여 · 수정 · 삭제할 수 없다
  - 계정에 주는 방법은 DB 직접 입력뿐:
        UPDATE account.app_user SET role = 'administrator' WHERE login_id = '아이디';

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
INSERT INTO account.role (code, name, description, sort_order)
VALUES ('administrator', '관리자', '모든 권한 (DB 에서만 부여)', 0)
ON CONFLICT (code) DO NOTHING;
""")


def downgrade() -> None:
    op.execute("""
UPDATE account.app_user SET role = 'operator' WHERE role = 'administrator';
DELETE FROM account.role WHERE code = 'administrator';
""")
