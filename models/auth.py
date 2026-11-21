from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, func
from db.database import Base

class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = {"schema": "auth"}

    id            = Column(BigInteger, primary_key=True)
    login_id      = Column(String(50),  nullable=False, unique=True)
    name          = Column(String(50),  nullable=False)
    password_hash = Column(String(200), nullable=False)
    email         = Column(String(100))
    role          = Column(String(20),  nullable=False)
    active        = Column(Boolean,     nullable=False, default=True)
    created_at    = Column(DateTime,    server_default=func.now())
