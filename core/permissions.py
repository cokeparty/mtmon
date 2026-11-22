"""
페이지 권한 — 역할마다 페이지별로 '접속 불가 / 조회 / 수정' 중 하나 (역할관리 화면에서 설정).

  접속 불가(행 없음) : 메뉴에 안 보이고 주소로 들어와도 막힌다.
  조회(1)           : 화면을 볼 수 있지만 SR 입력·유지/회수·업로드·배치 실행 등 바꾸는 작업은 못 한다.
  수정(2)           : 그 페이지의 모든 기능.

사용법 (라우터)
    @router.get("")                         # 화면 — 조회 권한 필요
    def page(current_user=Depends(page_view("ddl"))): ...

    @router.post("/apply-sr")               # 바꾸는 작업 — 수정 권한 필요
    def apply(current_user=Depends(page_edit("ddl"))): ...

권한이 없으면 화면 요청은 안내 페이지(403), API 요청은 403 JSON {"ok": false, "message": ...}.
템플릿에서는 perms 로 확인한다:  {% if perms.ddl >= 2 %} ... {% endif %}
"""
from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from core.deps import ForbiddenPage, get_current_user
from db.database import get_db

PERM_DENIED_MSG = "권한이 부족합니다. 관리자에게 문의하세요."

LEVEL_NONE, LEVEL_VIEW, LEVEL_EDIT = 0, 1, 2

# 관리자 역할 — 항상 모든 권한. 앱(역할관리·계정관리)에서 보이지 않고 부여·수정·삭제 불가.
# 계정에 주는 방법은 DB 직접 입력뿐:  UPDATE account.app_user SET role='administrator' WHERE login_id='...';
ADMIN_ROLE = "administrator"
LEVEL_LABELS = {LEVEL_NONE: "접속 불가", LEVEL_VIEW: "조회", LEVEL_EDIT: "수정"}

# (페이지 코드, 이름, 주소) — 메뉴 순서
PAGES: list[tuple[str, str, str]] = [
    ("dashboard",      "대시보드",               "/dashboard"),
    ("program",        "프로그램변경",           "/program"),
    ("depart_daily",   "부서이동자(일간)",       "/depart/daily"),
    ("depart_monthly", "부서이동자(월간)",       "/depart"),
    ("dml_developer",  "데이터변경 - 개발자 화면", "/dml/developer"),
    ("dml_manager",    "데이터변경 - 운영자 화면", "/dml/manager"),
    ("ddl",            "프로시저",               "/ddl"),
    ("batch",          "배치관리",               "/batch"),
    ("account",        "계정관리",               "/account"),
    ("role",           "역할관리",               "/role"),
]
PAGE_CODES = [p[0] for p in PAGES]


class ApiForbidden(Exception):
    """API 권한 없음 — main.py 핸들러가 403 JSON 으로 응답."""


def load_perms(db: Session, role: str) -> dict[str, int]:
    """역할의 페이지별 권한 레벨 {page_code: level}. 없는 페이지는 0."""
    from models.account import RolePermission
    if role == ADMIN_ROLE:
        return {p: LEVEL_EDIT for p in PAGE_CODES}
    perms = {p: LEVEL_NONE for p in PAGE_CODES}
    for rp in db.query(RolePermission).filter(RolePermission.role_code == role).all():
        if rp.page_code in perms:
            perms[rp.page_code] = int(rp.level)
    return perms


def request_perms(request: Request, db: Session | None = None) -> dict[str, int]:
    """이번 요청 사용자의 권한 (한 요청 안에서는 한 번만 조회)."""
    cached = getattr(request.state, "perms", None)
    if cached is not None:
        return cached
    role = getattr(request.state, "role", None) or request.session.get("role", "")
    if request.session.get("user_id") == -1:
        # DB 없이 임시 계정으로 들어온 경우 — 권한 표를 읽을 수 없으므로 운영자만 전체 허용
        perms = {p: (LEVEL_EDIT if role == "operator" else LEVEL_VIEW) for p in PAGE_CODES}
    elif db is not None:
        perms = load_perms(db, role)
    else:
        from db.database import SessionLocal
        s = SessionLocal()
        try:
            perms = load_perms(s, role)
        finally:
            s.close()
    request.state.perms = perms
    return perms


def first_allowed_url(perms: dict[str, int]) -> str | None:
    """접속 가능한 첫 페이지 주소 (로그인 직후 · '/' 이동용)."""
    for code, _, url in PAGES:
        if perms.get(code, 0) >= LEVEL_VIEW:
            return url
    return None


def _wants_html(request: Request) -> bool:
    return (request.method == "GET"
            and "text/html" in request.headers.get("accept", "")
            and "/api/" not in request.url.path)


def _require(pages: tuple[str, ...], level: int):
    names = {c: n for c, n, _ in PAGES}
    page_name = " 또는 ".join(names.get(p, p) for p in pages)

    def dep(request: Request, db: Session = Depends(get_db),
            current_user=Depends(get_current_user)):
        # 세션이 아니라 DB 의 현재 역할 기준 (역할을 바꾸면 다음 요청부터 바로 반영)
        request.state.role = getattr(current_user, "role", None) or request.session.get("role", "")
        perms = request_perms(request, db)
        if max(perms.get(p, 0) for p in pages) < level:
            if _wants_html(request):
                what = "접속" if level == LEVEL_VIEW else "수정"
                raise ForbiddenPage(f"'{page_name}' {what} 권한이 없습니다. 관리자에게 문의하세요.")
            raise ApiForbidden()
        return current_user
    return dep


def page_view(*pages: str):
    """조회(접속) 권한이 필요한 핸들러용 의존성. 페이지를 여러 개 주면 그중 하나만 있어도 된다."""
    return _require(pages, LEVEL_VIEW)


def page_edit(*pages: str):
    """수정 권한이 필요한 핸들러용 의존성. 페이지를 여러 개 주면 그중 하나만 있어도 된다."""
    return _require(pages, LEVEL_EDIT)


def can_edit(request: Request, page: str) -> bool:
    return request_perms(request).get(page, 0) >= LEVEL_EDIT
