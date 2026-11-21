"""앱 시작 시 DB 구조 변경(마이그레이션) 자동 적용.

  * migrations/versions/ 에 있는 변경 중 아직 적용되지 않은 것만 순서대로 실행한다.
  * uvicorn 워커가 여러 개여도 PostgreSQL advisory lock 으로 한 워커만 실행하고,
    나머지는 끝날 때까지 기다렸다가 '이미 최신'으로 넘어간다.
  * 실패하면 앱을 띄우지 않는다(구조가 안 맞는 상태로 화면이 열리는 것 방지).
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text

from db.database import engine

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
_LOCK_KEY = 74_1001   # 마이그레이션 전용 advisory lock 번호 (임의 고정값)


def _alembic_config() -> Config:
    cfg = Config()   # alembic.ini 를 읽지 않음 (Windows 인코딩 문제 회피, 필요한 값만 지정)
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    return cfg


def upgrade_to_head() -> None:
    cfg = _alembic_config()
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _LOCK_KEY})
        try:
            current = MigrationContext.configure(conn).get_current_revision()
            if current == head:
                logger.info("DB 구조 최신 상태 (버전 %s)", current)
                return
            logger.info("DB 구조 변경 적용 시작: %s → %s", current or "(없음)", head)
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
            conn.commit()
            logger.info("DB 구조 변경 적용 완료 (버전 %s)", head)
        except Exception:
            conn.rollback()
            logger.exception("DB 구조 변경 실패 — 앱을 시작하지 않습니다")
            raise
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _LOCK_KEY})
            conn.commit()
