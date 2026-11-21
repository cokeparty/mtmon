import enum
from sqlalchemy import Column, BigInteger, String, Integer, TIMESTAMP, func
from db.database import Base


class SystemCode(str, enum.Enum):
    """Python 레벨 상수 — DB 컬럼은 VARCHAR(10)."""
    HR   = "HR"
    EPRO = "EPRO"
    SR   = "SR"
    PMS  = "PMS"


class ServerConfig(Base):
    __tablename__  = "server_config"
    __table_args__ = {"schema": "program_change"}

    id           = Column(BigInteger, primary_key=True)
    system_code  = Column(String(10), nullable=False, unique=True)

    # A 서버 (xferlog)
    ssh_host     = Column(String(100), nullable=False)
    ssh_port     = Column(Integer,     nullable=False, default=22)
    ssh_user     = Column(String(50),  nullable=False)
    ssh_key_path = Column(String(300))
    ssh_password = Column(String(200))
    log_dir      = Column(String(300), nullable=False)
    log_pattern  = Column(String(100), nullable=False)
    include_path = Column(String(300), nullable=False)
    include_flag = Column(String(50),  nullable=False)

    # B 서버 (NFS)
    nfs_ssh_host     = Column(String(100))
    nfs_ssh_port     = Column(Integer, default=22)
    nfs_ssh_user     = Column(String(50))
    nfs_ssh_key_path = Column(String(300))
    nfs_ssh_password = Column(String(200))
    nfs_base_dir     = Column(String(300))

    updated_at = Column(TIMESTAMP, nullable=False, server_default=func.now())
