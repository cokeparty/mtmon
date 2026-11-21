# scripts/create_admin.py
import sys
from db.database import SessionLocal
from models.auth import AppUser
from core.security import hash_password

def main(login_id, name, password, role="operator"):
    db = SessionLocal()
    try:
        if db.query(AppUser).filter(AppUser.login_id == login_id).first():
            print(f"이미 존재: {login_id}"); return
        db.add(AppUser(
            login_id=login_id, name=name,
            password_hash=hash_password(password), role=role,
        ))
        db.commit()
        print(f"생성 완료: {login_id} ({role})")
    finally:
        db.close()

if __name__ == "__main__":
    # python -m scripts.create_admin admin 시스템관리자 admin operator
    main(*sys.argv[1:])
