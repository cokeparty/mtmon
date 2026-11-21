# scripts/create_user.py
"""
사용법:
  python -m scripts.create_user <login_id> <name> <password> <role>

role 허용값: operator | developer | reviewer

예시:
  python -m scripts.create_user admin    시스템관리자  admin1234   operator
  python -m scripts.create_user hong_gd  홍길동        dev1234     developer
  python -m scripts.create_user kim_rev  김검토        rev1234     reviewer
"""

import sys
from db.database import SessionLocal
from models.auth import AppUser
from core.security import hash_password

ALLOWED_ROLES = ("operator", "developer", "reviewer")

ROLE_LABEL = {
    "operator":  "🔧 운영자",
    "developer": "💻 개발자",
    "reviewer":  "🔍 검토수행자",
}


def create_user(login_id: str, name: str, password: str, role: str = "developer"):
    # ── 역할 검증 ──────────────────────────────────────────
    if role not in ALLOWED_ROLES:
        print(f"[ERROR] 허용되지 않는 역할: '{role}'")
        print(f"        허용값: {' | '.join(ALLOWED_ROLES)}")
        sys.exit(1)

    # ── 비밀번호 최소 길이 ─────────────────────────────────
    if len(password) < 8:
        print("[ERROR] 비밀번호는 8자 이상이어야 합니다.")
        sys.exit(1)

    db = SessionLocal()
    try:
        # ── 아이디 중복 확인 ───────────────────────────────
        if db.query(AppUser).filter(AppUser.login_id == login_id).first():
            print(f"[SKIP]  이미 존재하는 아이디: {login_id}")
            return

        # ── 이름 중복 확인 (db_user 매칭 고려) ────────────
        if db.query(AppUser).filter(AppUser.name == name).first():
            print(f"[SKIP]  이미 존재하는 이름: {name}  (DML 로그 db_user 충돌 방지)")
            return

        # ── 계정 생성 ──────────────────────────────────────
        db.add(AppUser(
            login_id      = login_id,
            name          = name,
            password_hash = hash_password(password),
            role          = role,
            active        = True,
        ))
        db.commit()
        print(f"[OK]    생성 완료: {login_id!r:20s} | 이름: {name:12s} | 역할: {ROLE_LABEL[role]}")

    finally:
        db.close()


# ── 배치 생성 헬퍼 ─────────────────────────────────────────────
def create_bulk(users: list[dict]):
    """
    코드에서 직접 여러 계정을 한 번에 생성할 때 사용.

    예시:
        create_bulk([
            {"login_id": "hong_gd", "name": "홍길동", "password": "dev1234", "role": "developer"},
            {"login_id": "kim_rev", "name": "김검토", "password": "rev1234", "role": "reviewer"},
        ])
    """
    print(f"총 {len(users)}개 계정 생성 시작...\n")
    for u in users:
        create_user(
            login_id = u["login_id"],
            name     = u["name"],
            password = u["password"],
            role     = u.get("role", "developer"),
        )
    print("\n완료.")


# ── CLI 진입점 ─────────────────────────────────────────────────
if __name__ == "__main__":
    # 인자 없이 실행 시 도움말 출력
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(0)

    _, login_id, name, password, role = sys.argv
    create_user(login_id, name, password, role)
