# models/account.py  —  schema: account
from sqlalchemy import (Column, BigInteger, String, Boolean, DateTime, Integer, SmallInteger,
                        ForeignKey, CheckConstraint, func)
from db.database import Base


class Role(Base):
    """역할 — 역할관리 화면에서 추가·삭제·이름 변경."""
    __tablename__ = "role"
    __table_args__ = {"schema": "account"}

    code        = Column(String(20), primary_key=True)
    name        = Column(String(50), nullable=False, unique=True)
    description = Column(String(200))
    sort_order  = Column(Integer, nullable=False, default=100, server_default="100")
    created_at  = Column(DateTime, nullable=False, server_default=func.now())


class RolePermission(Base):
    """역할별 페이지 권한 — level 1=조회, 2=수정. 행이 없으면 접속 불가."""
    __tablename__ = "role_permission"
    __table_args__ = (
        CheckConstraint("level IN (1, 2)", name="role_permission_level_check"),
        {"schema": "account"},
    )

    role_code = Column(String(20), ForeignKey("account.role.code", onupdate="CASCADE", ondelete="CASCADE"),
                       primary_key=True)
    page_code = Column(String(30), primary_key=True)
    level     = Column(SmallInteger, nullable=False)


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = {"schema": "account"}

    id            = Column(BigInteger, primary_key=True)
    login_id      = Column(String(50),  nullable=False, unique=True)
    name          = Column(String(50),  nullable=False)
    password_hash = Column(String(200), nullable=False)
    email         = Column(String(100))
    role          = Column(String(20),  ForeignKey("account.role.code", onupdate="CASCADE",
                                                   name="fk_app_user_role"), nullable=False)
    active        = Column(Boolean,     nullable=False, default=True)
    created_at    = Column(DateTime,    server_default=func.now())
    last_login_at = Column(DateTime)
