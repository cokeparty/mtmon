"""Alembic 실행 환경 — 접속 정보는 config.settings(.env)에서 읽는다.

앱에서 호출할 때(core/migrate.py)는 이미 열린 connection 을 넘겨받아 사용하고,
CLI(python -m alembic ...)로 호출할 때는 DATABASE_URL 로 직접 접속한다.
"""
import sys
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings          # noqa: E402
from db.database import Base         # noqa: E402
import models                        # noqa: E402,F401  (모든 모델을 metadata 에 등록)

target_metadata = Base.metadata
APP_SCHEMAS = {"common", "account", "program", "depart", "dml", "ddl"}  # deploy 는 모델 없음 → 자동 비교 제외


def _include_object(obj, name, type_, reflected, compare_to):
    """우리 스키마의 객체만 비교 대상으로 (다른 스키마·확장 객체 무시)."""
    if type_ == "table":
        return getattr(obj, "schema", None) in APP_SCHEMAS
    return True


def _run(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=_include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


conn = context.config.attributes.get("connection")
if conn is not None:
    _run(conn)
else:
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as c:
        _run(c)
