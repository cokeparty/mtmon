"""기준 구조 (2026-11 운영 DB 구조, 옛 스키마 이름)

spec/*/ddl 과 spec/mirgrations/*.sql 을 합친 상태를 만든다.
모든 문장이 IF NOT EXISTS 형태라서
  - 빈 DB(개발계 신규)  → 전체 생성
  - 기존 운영 DB        → 이미 있는 건 건너뛰고, 빠진 컬럼만 추가
두 경우 모두 그대로 실행된다. 스키마 이름 변경은 다음 단계(0002)에서 한다.

Revision ID: 0001
Revises:
Create Date: 2026-11-21
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


SQL = r"""
-- ── 스키마 ────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS program_change;
CREATE SCHEMA IF NOT EXISTS auth;
CREATE SCHEMA IF NOT EXISTS dept_transfer;
CREATE SCHEMA IF NOT EXISTS dml;
CREATE SCHEMA IF NOT EXISTS ddl;

-- ── 공통 함수 ─────────────────────────────────────────────
CREATE OR REPLACE FUNCTION program_change.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION program_change.guard_closed_period()
RETURNS TRIGGER AS $$
DECLARE
    v_status VARCHAR(10);
    v_pid    BIGINT;
BEGIN
    v_pid := COALESCE(NEW.period_id, OLD.period_id);
    SELECT status INTO v_status FROM program_change.monitoring_period WHERE id = v_pid;
    IF v_status = 'closed' THEN
        RAISE EXCEPTION '마감된 회차(period_id=%)는 변경할 수 없습니다.', v_pid
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ── program_change ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS program_change.monitoring_period (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year_month CHAR(7)      NOT NULL UNIQUE,
    status     VARCHAR(10)  NOT NULL DEFAULT 'open',
    closed_at  TIMESTAMP,
    closed_by  VARCHAR(50),
    created_at TIMESTAMP    NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS program_change.server_config (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_code      VARCHAR(10)  NOT NULL UNIQUE,
    ssh_host         VARCHAR(100) NOT NULL,
    ssh_port         INTEGER      NOT NULL DEFAULT 22,
    ssh_user         VARCHAR(50)  NOT NULL,
    ssh_key_path     VARCHAR(300),
    ssh_password     VARCHAR(200),
    log_dir          VARCHAR(300) NOT NULL,
    log_pattern      VARCHAR(100) NOT NULL,
    include_path     VARCHAR(300) NOT NULL,
    include_flag     VARCHAR(50)  NOT NULL,
    nfs_ssh_host     VARCHAR(100),
    nfs_ssh_port     INTEGER      DEFAULT 22,
    nfs_ssh_user     VARCHAR(50),
    nfs_ssh_key_path VARCHAR(300),
    nfs_ssh_password VARCHAR(200),
    nfs_base_dir     VARCHAR(300),
    updated_at       TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS program_change.program_change_log (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_id   BIGINT       NOT NULL,
    system_code VARCHAR(10)  NOT NULL,
    log_month   SMALLINT,
    log_day     SMALLINT,
    log_time    TIME,
    deploy_time TIMESTAMP    NOT NULL,
    file_name   VARCHAR(255) NOT NULL,
    full_path   VARCHAR(500),
    deployer    VARCHAR(50),
    nfs_path    VARCHAR(700),
    nfs_mtime   TIMESTAMP,
    map_type    VARCHAR(30)  NOT NULL DEFAULT 'none',
    sr_no          VARCHAR(30),
    sr_title       VARCHAR(300),
    sr_work_type   VARCHAR(50),
    sr_approved_at TIMESTAMP,
    sr_closed_at   TIMESTAMP,
    sr_developer   VARCHAR(50),
    sr_reviewer    VARCHAR(50),
    approval_change_request VARCHAR(50),
    approval_user_test      VARCHAR(50),
    approval_pre_deploy     VARCHAR(50),
    result     VARCHAR(20) NOT NULL DEFAULT 'SR없음',
    normal_yn  VARCHAR(10) NOT NULL DEFAULT '이상',
    reason     VARCHAR(500),
    remark     VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT fk_pcl_period FOREIGN KEY (period_id) REFERENCES program_change.monitoring_period(id),
    CONSTRAINT uq_pcl_dedup  UNIQUE (period_id, system_code, deploy_time, file_name)
);
-- spec/mirgrations: transferer 추가, 승인일·종료일 DATE → TIMESTAMP
ALTER TABLE program_change.program_change_log ADD COLUMN IF NOT EXISTS transferer VARCHAR(50);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'program_change' AND table_name = 'program_change_log'
                  AND column_name = 'sr_approved_at' AND data_type = 'date') THEN
        ALTER TABLE program_change.program_change_log
            ALTER COLUMN sr_approved_at TYPE TIMESTAMP USING sr_approved_at::timestamp,
            ALTER COLUMN sr_closed_at   TYPE TIMESTAMP USING sr_closed_at::timestamp;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_pcl_period_system ON program_change.program_change_log (period_id, system_code);
CREATE INDEX IF NOT EXISTS idx_pcl_deploy_time   ON program_change.program_change_log (deploy_time);
CREATE INDEX IF NOT EXISTS idx_pcl_sr_no         ON program_change.program_change_log (sr_no);
CREATE INDEX IF NOT EXISTS idx_pcl_file_name     ON program_change.program_change_log (file_name);
CREATE INDEX IF NOT EXISTS idx_pcl_result        ON program_change.program_change_log (result);

-- ── auth ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auth.app_user (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login_id      VARCHAR(50)  NOT NULL,
    name          VARCHAR(50)  NOT NULL,
    password_hash VARCHAR(200) NOT NULL,
    email         VARCHAR(100),
    role          VARCHAR(20)  NOT NULL,
    active        BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_user_login UNIQUE (login_id)
);
ALTER TABLE auth.app_user ADD COLUMN IF NOT EXISTS email VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_user_role ON auth.app_user (role) WHERE active = TRUE;

-- ── dept_transfer ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dept_transfer.daily_record (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    record_type    VARCHAR(20)  NOT NULL,
    empno          VARCHAR(20)  NOT NULL,
    emp_name       VARCHAR(50),
    change_date    DATE         NOT NULL,
    dept_code      VARCHAR(50),
    dept_name      VARCHAR(100),
    prev_dept_name VARCHAR(100),
    role_code      VARCHAR(50),
    role_key       VARCHAR(50)  NOT NULL DEFAULT '-',
    role_name      VARCHAR(200),
    reg_date       DATE,
    action         VARCHAR(10),
    sr_no          VARCHAR(30),
    sr_title       VARCHAR(300),
    sr_work_type   VARCHAR(50),
    remark         VARCHAR(500),
    processed_by   BIGINT,
    processed_at   TIMESTAMP,
    first_seen     DATE         NOT NULL DEFAULT CURRENT_DATE,
    last_seen      DATE         NOT NULL DEFAULT CURRENT_DATE,
    created_at     TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at     TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_daily_record UNIQUE (record_type, empno, change_date, role_key)
);
ALTER TABLE dept_transfer.daily_record ADD COLUMN IF NOT EXISTS dept_code      VARCHAR(50);
ALTER TABLE dept_transfer.daily_record ADD COLUMN IF NOT EXISTS prev_dept_code VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_daily_change_date ON dept_transfer.daily_record (change_date);
CREATE INDEX IF NOT EXISTS idx_daily_empno       ON dept_transfer.daily_record (empno);
CREATE INDEX IF NOT EXISTS idx_daily_action      ON dept_transfer.daily_record (action);
CREATE INDEX IF NOT EXISTS idx_daily_rtype       ON dept_transfer.daily_record (record_type);

CREATE TABLE IF NOT EXISTS dept_transfer.monthly_record (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_id      BIGINT       NOT NULL,
    system_code    VARCHAR(20)  NOT NULL,
    empno          VARCHAR(20)  NOT NULL,
    emp_name       VARCHAR(50),
    change_date    DATE,
    dept_name      VARCHAR(100),
    prev_dept_name VARCHAR(100),
    role_code      VARCHAR(50),
    role_key       VARCHAR(50)  NOT NULL DEFAULT '-',
    role_name      VARCHAR(200),
    reg_date       DATE,
    revoke_date    DATE,
    sr_no          VARCHAR(30),
    sr_title       VARCHAR(300),
    sr_work_type   VARCHAR(50),
    remark         VARCHAR(500),
    created_at     TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at     TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT fk_monthly_period FOREIGN KEY (period_id) REFERENCES program_change.monitoring_period(id),
    CONSTRAINT uq_monthly_record UNIQUE (period_id, system_code, empno, role_key)
);
ALTER TABLE dept_transfer.monthly_record ADD COLUMN IF NOT EXISTS dept_code      VARCHAR(50);
ALTER TABLE dept_transfer.monthly_record ADD COLUMN IF NOT EXISTS prev_dept_code VARCHAR(50);
CREATE INDEX IF NOT EXISTS idx_monthly_period_sys ON dept_transfer.monthly_record (period_id, system_code);
CREATE INDEX IF NOT EXISTS idx_monthly_empno      ON dept_transfer.monthly_record (empno);

-- ── dml ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dml.db_user_developer_map (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_code  VARCHAR(10) NOT NULL,
    db_user      VARCHAR(50) NOT NULL,
    developer_id BIGINT      NOT NULL,
    CONSTRAINT uq_dbuser_map UNIQUE (system_code, db_user)
);

CREATE TABLE IF NOT EXISTS dml.dml_group (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_id    BIGINT       NOT NULL,
    system_code  VARCHAR(10)  NOT NULL,
    base_time    TIMESTAMP    NOT NULL,
    db_user      VARCHAR(50)  NOT NULL,
    conn_account VARCHAR(50)  NOT NULL,
    target_table VARCHAR(100) NOT NULL,
    developer_id BIGINT,
    row_count    INTEGER      NOT NULL DEFAULT 0,
    sr_no        VARCHAR(30),
    status       VARCHAR(10)  NOT NULL DEFAULT '미입력',
    created_at   TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at   TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT fk_dmlg_period FOREIGN KEY (period_id) REFERENCES program_change.monitoring_period(id)
);
ALTER TABLE dml.dml_group ADD COLUMN IF NOT EXISTS is_dml     BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE dml.dml_group ADD COLUMN IF NOT EXISTS dml_reason VARCHAR(500);
CREATE INDEX IF NOT EXISTS idx_dmlg_period_sys ON dml.dml_group (period_id, system_code);
CREATE INDEX IF NOT EXISTS idx_dmlg_developer  ON dml.dml_group (developer_id, status);
CREATE INDEX IF NOT EXISTS idx_dmlg_status     ON dml.dml_group (status);
CREATE INDEX IF NOT EXISTS idx_dmlg_base_time  ON dml.dml_group (base_time);

CREATE TABLE IF NOT EXISTS dml.dml_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_id     BIGINT       NOT NULL,
    system_code   VARCHAR(10)  NOT NULL,
    request_time  TIMESTAMP    NOT NULL,
    db_user       VARCHAR(50)  NOT NULL,
    conn_account  VARCHAR(50)  NOT NULL,
    target_table  VARCHAR(100) NOT NULL,
    query_summary TEXT,
    group_id      BIGINT,
    sr_no         VARCHAR(30),
    status        VARCHAR(10)  NOT NULL DEFAULT '미입력',
    created_at    TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT fk_dml_period FOREIGN KEY (period_id) REFERENCES program_change.monitoring_period(id),
    CONSTRAINT fk_dml_group  FOREIGN KEY (group_id)  REFERENCES dml.dml_group(id)
);
CREATE INDEX IF NOT EXISTS idx_dml_period_sys ON dml.dml_log (period_id, system_code);
CREATE INDEX IF NOT EXISTS idx_dml_request    ON dml.dml_log (request_time);
CREATE INDEX IF NOT EXISTS idx_dml_group      ON dml.dml_log (group_id);
CREATE INDEX IF NOT EXISTS idx_dml_grp_keys   ON dml.dml_log
    (period_id, system_code, db_user, conn_account, target_table, request_time);

-- ── ddl ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ddl.ddl_log (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    period_id     BIGINT        NOT NULL,
    system_code   VARCHAR(10)   NOT NULL,
    request_time  TIMESTAMP     NOT NULL,
    db_user       VARCHAR(50)   NOT NULL,
    conn_account  VARCHAR(50)   NOT NULL,
    target_object VARCHAR(150)  NOT NULL,
    ddl_type      VARCHAR(10)   NOT NULL,
    query_summary TEXT,
    is_abnormal   BOOLEAN       NOT NULL DEFAULT FALSE,
    sr_no         VARCHAR(30),
    status        VARCHAR(10)   NOT NULL DEFAULT '미입력',
    created_at    TIMESTAMP     NOT NULL DEFAULT now(),
    CONSTRAINT fk_ddl_period FOREIGN KEY (period_id) REFERENCES program_change.monitoring_period(id)
);
ALTER TABLE ddl.ddl_log
  ADD COLUMN IF NOT EXISTS ddl_reason           VARCHAR(500),
  ADD COLUMN IF NOT EXISTS proc_change_approval VARCHAR(10)  DEFAULT 'O',
  ADD COLUMN IF NOT EXISTS user_test            VARCHAR(10)  DEFAULT 'O',
  ADD COLUMN IF NOT EXISTS pre_release_approval VARCHAR(10),
  ADD COLUMN IF NOT EXISTS developer            VARCHAR(100),
  ADD COLUMN IF NOT EXISTS releaser             VARCHAR(100) DEFAULT '이기헌',
  ADD COLUMN IF NOT EXISTS reviewer_name        VARCHAR(100) DEFAULT '노광환';
CREATE INDEX IF NOT EXISTS idx_ddl_period_sys ON ddl.ddl_log (period_id, system_code);
CREATE INDEX IF NOT EXISTS idx_ddl_request    ON ddl.ddl_log (request_time);
CREATE INDEX IF NOT EXISTS idx_ddl_type       ON ddl.ddl_log (ddl_type);
CREATE INDEX IF NOT EXISTS idx_ddl_abnormal   ON ddl.ddl_log (is_abnormal) WHERE is_abnormal = TRUE;
CREATE INDEX IF NOT EXISTS idx_ddl_status     ON ddl.ddl_log (status);
CREATE INDEX IF NOT EXISTS idx_ddl_sr         ON ddl.ddl_log (sr_no);

-- ── 트리거 (updated_at 자동 갱신 · 마감 회차 보호) ────────
DROP TRIGGER IF EXISTS trg_server_config_updated ON program_change.server_config;
CREATE TRIGGER trg_server_config_updated BEFORE UPDATE ON program_change.server_config
    FOR EACH ROW EXECUTE FUNCTION program_change.set_updated_at();
DROP TRIGGER IF EXISTS trg_pcl_updated_at ON program_change.program_change_log;
CREATE TRIGGER trg_pcl_updated_at BEFORE UPDATE ON program_change.program_change_log
    FOR EACH ROW EXECUTE FUNCTION program_change.set_updated_at();
DROP TRIGGER IF EXISTS trg_guard_pcl ON program_change.program_change_log;
CREATE TRIGGER trg_guard_pcl BEFORE INSERT OR UPDATE OR DELETE ON program_change.program_change_log
    FOR EACH ROW EXECUTE FUNCTION program_change.guard_closed_period();

DROP TRIGGER IF EXISTS trg_daily_updated ON dept_transfer.daily_record;
CREATE TRIGGER trg_daily_updated BEFORE UPDATE ON dept_transfer.daily_record
    FOR EACH ROW EXECUTE FUNCTION program_change.set_updated_at();
DROP TRIGGER IF EXISTS trg_monthly_updated ON dept_transfer.monthly_record;
CREATE TRIGGER trg_monthly_updated BEFORE UPDATE ON dept_transfer.monthly_record
    FOR EACH ROW EXECUTE FUNCTION program_change.set_updated_at();
DROP TRIGGER IF EXISTS trg_guard_monthly ON dept_transfer.monthly_record;
CREATE TRIGGER trg_guard_monthly BEFORE INSERT OR UPDATE OR DELETE ON dept_transfer.monthly_record
    FOR EACH ROW EXECUTE FUNCTION program_change.guard_closed_period();

DROP TRIGGER IF EXISTS trg_dml_group_updated ON dml.dml_group;
CREATE TRIGGER trg_dml_group_updated BEFORE UPDATE ON dml.dml_group
    FOR EACH ROW EXECUTE FUNCTION program_change.set_updated_at();
DROP TRIGGER IF EXISTS trg_guard_dml_log ON dml.dml_log;
CREATE TRIGGER trg_guard_dml_log BEFORE INSERT OR UPDATE OR DELETE ON dml.dml_log
    FOR EACH ROW EXECUTE FUNCTION program_change.guard_closed_period();
DROP TRIGGER IF EXISTS trg_guard_dml_group ON dml.dml_group;
CREATE TRIGGER trg_guard_dml_group BEFORE INSERT OR UPDATE OR DELETE ON dml.dml_group
    FOR EACH ROW EXECUTE FUNCTION program_change.guard_closed_period();

DROP TRIGGER IF EXISTS trg_guard_ddl ON ddl.ddl_log;
CREATE TRIGGER trg_guard_ddl BEFORE INSERT OR UPDATE OR DELETE ON ddl.ddl_log
    FOR EACH ROW EXECUTE FUNCTION program_change.guard_closed_period();
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    raise RuntimeError("기준 구조(0001)는 되돌릴 수 없습니다.")
