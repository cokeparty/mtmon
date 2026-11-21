"""배포 이력 테이블 (deploy.deploy_history)

운영계에만 따로 만들어 쓰던 테이블(배포 도구가 기록)을 프로그램의 DB 구조 이력에 포함한다.
운영계에는 이미 있으므로 IF NOT EXISTS — 기존 테이블/데이터는 건드리지 않는다.
앱 코드(모델)에서는 아직 사용하지 않는다 → migrations/env.py 의 자동 비교 대상(APP_SCHEMAS)에서도 제외.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-21
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
CREATE SCHEMA IF NOT EXISTS deploy;

CREATE TABLE IF NOT EXISTS deploy.deploy_history (
    id                 BIGSERIAL PRIMARY KEY,
    batch_id           VARCHAR(36)  NOT NULL,
    action             VARCHAR(10)  NOT NULL DEFAULT '배포',
    sr_no              VARCHAR(30)  NOT NULL,
    system_code        VARCHAR(10),
    site_name          VARCHAR(100),
    protocol           VARCHAR(10),
    host               VARCHAR(100),
    port               INTEGER,
    login_user         VARCHAR(50),
    remote_path        VARCHAR(700) NOT NULL,
    remote_dir         VARCHAR(500),
    file_name          VARCHAR(255) NOT NULL,
    local_path         VARCHAR(700),
    local_size         BIGINT,
    local_sha256       CHAR(64),
    existed_before     BOOLEAN,
    before_size        BIGINT,
    before_mtime       TIMESTAMP,
    backup_path        VARCHAR(700),
    server_backup_path VARCHAR(700),
    remote_size        BIGINT,
    remote_sha256      CHAR(64),
    verify_ok          BOOLEAN      NOT NULL DEFAULT FALSE,
    verify_method      VARCHAR(20),
    status             VARCHAR(20)  NOT NULL,
    error_msg          TEXT,
    started_at         TIMESTAMP,
    deployed_at        TIMESTAMP,
    finished_at        TIMESTAMP,
    client_host        VARCHAR(100),
    os_user            VARCHAR(50),
    created_at         TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_deploy_history_created ON deploy.deploy_history (created_at);
CREATE INDEX IF NOT EXISTS ix_deploy_history_match   ON deploy.deploy_history (system_code, file_name, deployed_at);
CREATE INDEX IF NOT EXISTS ix_deploy_history_sr      ON deploy.deploy_history (sr_no);
COMMENT ON TABLE deploy.deploy_history IS '배포 이력 (파일 업로드 배포 도구가 기록)';
""")


def downgrade() -> None:
    # 운영 데이터가 있는 테이블이므로 자동 삭제하지 않는다.
    pass
