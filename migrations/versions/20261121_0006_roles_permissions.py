"""역할 · 페이지 권한 테이블, 마지막 접속일, DDL 위험 표시 제거

  account.role             역할 (운영자·검토자·개발자·조회자 + 화면에서 추가한 역할)
  account.role_permission  역할별 페이지 권한 (level 1=조회, 2=수정 / 행이 없으면 접속 불가)
  account.app_user.last_login_at  마지막 로그인 시각
  account.app_user.role → account.role.code 참조 (사용 중인 역할은 삭제 불가)
  ddl.ddl_log.is_abnormal  삭제 (DROP/TRUNCATE 위험 표시는 쓰지 않음)

기본 권한은 개편 전 동작과 최대한 같게 넣는다. 운영자는 모든 페이지 수정 권한.
이후에는 화면(역할관리)에서 바꾼다.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PAGES = ["dashboard", "program", "depart_daily", "depart_monthly", "dml_developer",
         "dml_manager", "ddl", "batch", "account", "role"]

# (역할코드, 이름, 순서, {페이지: 레벨})
DEFAULTS = [
    ("operator",  "운영자", 1, {p: 2 for p in PAGES}),
    ("reviewer",  "검토자", 2, {"dashboard": 1, "program": 2, "depart_daily": 2, "depart_monthly": 2,
                               "dml_developer": 2, "dml_manager": 2, "ddl": 2, "batch": 1}),
    ("developer", "개발자", 3, {"dashboard": 1, "program": 1, "depart_daily": 1, "depart_monthly": 1,
                               "dml_developer": 2, "dml_manager": 1, "ddl": 1}),
    ("viewer",    "조회자", 4, {"dashboard": 1, "program": 1, "depart_daily": 1, "depart_monthly": 1,
                               "dml_developer": 1, "dml_manager": 1, "ddl": 1}),
]


def upgrade() -> None:
    op.execute("""
CREATE TABLE IF NOT EXISTS account.role (
    code        VARCHAR(20)  PRIMARY KEY,
    name        VARCHAR(50)  NOT NULL UNIQUE,
    description VARCHAR(200),
    sort_order  INTEGER      NOT NULL DEFAULT 100,
    created_at  TIMESTAMP    NOT NULL DEFAULT now()
);
COMMENT ON TABLE account.role IS '역할';

CREATE TABLE IF NOT EXISTS account.role_permission (
    role_code  VARCHAR(20) NOT NULL REFERENCES account.role(code) ON UPDATE CASCADE ON DELETE CASCADE,
    page_code  VARCHAR(30) NOT NULL,
    level      SMALLINT    NOT NULL CHECK (level IN (1, 2)),
    PRIMARY KEY (role_code, page_code)
);
COMMENT ON TABLE account.role_permission IS '역할별 페이지 권한 (1=조회, 2=수정, 행 없음=접속 불가)';
""")
    for code, name, order, perms in DEFAULTS:
        op.execute(f"INSERT INTO account.role (code, name, sort_order) VALUES ('{code}', '{name}', {order}) "
                   "ON CONFLICT (code) DO NOTHING")
        for page, level in perms.items():
            op.execute("INSERT INTO account.role_permission (role_code, page_code, level) "
                       f"VALUES ('{code}', '{page}', {level}) ON CONFLICT DO NOTHING")

    # 기존 계정에 위 4개 외의 역할값이 있으면 역할로 등록(권한 없음)해서 참조 제약이 걸리게 한다
    op.execute("""
INSERT INTO account.role (code, name)
SELECT DISTINCT u.role, u.role FROM account.app_user u
WHERE NOT EXISTS (SELECT 1 FROM account.role r WHERE r.code = u.role)
ON CONFLICT DO NOTHING;

ALTER TABLE account.app_user
    ADD CONSTRAINT fk_app_user_role FOREIGN KEY (role)
    REFERENCES account.role(code) ON UPDATE CASCADE;

ALTER TABLE account.app_user ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMP;
COMMENT ON COLUMN account.app_user.last_login_at IS '마지막 로그인 시각';

DROP INDEX IF EXISTS ddl.idx_ddl_abnormal;
ALTER TABLE ddl.ddl_log DROP COLUMN IF EXISTS is_abnormal;
""")


def downgrade() -> None:
    op.execute("""
ALTER TABLE ddl.ddl_log ADD COLUMN IF NOT EXISTS is_abnormal BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE ddl.ddl_log SET is_abnormal = ddl_type IN ('DROP', 'TRUNCATE');
CREATE INDEX IF NOT EXISTS idx_ddl_abnormal ON ddl.ddl_log (is_abnormal);
ALTER TABLE account.app_user DROP COLUMN IF EXISTS last_login_at;
ALTER TABLE account.app_user DROP CONSTRAINT IF EXISTS fk_app_user_role;
DROP TABLE IF EXISTS account.role_permission;
DROP TABLE IF EXISTS account.role;
""")
