from sqlalchemy.orm import Session
from models.server_config import ServerConfig

def get_by_system(db: Session, system_code: str) -> ServerConfig:
    cfg = db.query(ServerConfig).filter(ServerConfig.system_code == system_code).first()
    if not cfg:
        raise ValueError(f"server_config 미설정: {system_code}")
    return cfg
