# db/database.py
from contextlib import contextmanager
from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base  # <-- declarative_base 추가됨
from config import settings

# 1. DB 엔진 생성
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
    connect_args={"connect_timeout": 3},   # 3초 안에 연결 안 되면 빠르게 실패
)

# 2. 세션 생성기
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# 3. ★ 에러 해결을 위해 추가된 Base ★
metadata = MetaData()           # 스키마는 각 모델 __table_args__에서 명시
Base = declarative_base(metadata=metadata)


# 4. 일반 파이썬 코드용 세션
@contextmanager
def get_session():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# 5. FastAPI Depends용 세션
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
