"""
화면 공통 — 템플릿 렌더링 · 기본 회차 · DB 장애 응답.

    from core.web import render, default_ym
    return render(request, "ddl.html", {"active": "ddl", **data})

render() 가 자동으로 넣는 값
  request, current_user(id·name·role·role_name), perms(페이지별 권한 레벨), menu(접속 가능한 메뉴)
"""
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from core.periods import prev_month_ym

BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

DB_ERR_MSG = "DB 연결 실패 — 모니터링 DB 서버에 접속할 수 없습니다."

default_ym = prev_month_ym   # 월간 모니터링 기본 회차 = 전월


def session_user(request: Request) -> dict:
    s = request.session
    role = s.get("role", "")
    return {"id": s.get("user_id", -1), "name": s.get("name", ""), "role": role, "role_name": role}


def _perm_ctx(request: Request) -> dict:
    """메뉴 · 권한 표시용 값. DB 장애 중(에러 페이지)에도 화면은 떠야 하므로 실패하면 빈 값."""
    from core.permissions import request_perms
    user = session_user(request)
    if not request.session.get("user_id"):
        return {"current_user": user, "perms": {}, "menu": []}
    try:
        perms = request_perms(request)
        user["role"] = getattr(request.state, "role", None) or user["role"]
        user["role_name"] = _role_name(request, user["role"])
    except Exception:
        perms = {}
    return {"current_user": user, "perms": perms, "menu": _menu(perms)}


# 상단 메뉴 — (이름, 주소, 이 메뉴를 켜는 active 값들). 데이터변경은 두 화면을 한 메뉴로 묶는다.
_MENU = [
    ("대시보드",         ["dashboard"]),
    ("프로그램변경",     ["program"]),
    ("부서이동자(일간)", ["depart_daily"]),
    ("부서이동자(월간)", ["depart_monthly"]),
    ("데이터변경",       ["dml_manager", "dml_developer"]),
    ("프로시저",         ["ddl"]),
    ("배치관리",         ["batch"]),
    ("계정관리",         ["account"]),
    ("역할관리",         ["role"]),
]


def _menu(perms: dict) -> list[dict]:
    from core.permissions import PAGES
    urls = {code: url for code, _, url in PAGES}
    out = []
    for name, codes in _MENU:
        allowed = [c for c in codes if perms.get(c, 0) >= 1]
        if allowed:
            out.append({"name": name, "url": urls[allowed[0]], "codes": codes})
    return out


def _role_name(request: Request, code: str) -> str:
    from db.database import SessionLocal
    from models.account import Role
    s = SessionLocal()
    try:
        r = s.get(Role, code)
        return r.name if r else code
    finally:
        s.close()


def render(request: Request, template: str, ctx: dict | None = None, status_code: int = 200):
    data = {"request": request, "active": ""}
    data.update(_perm_ctx(request))
    data.update(ctx or {})
    return templates.TemplateResponse(template, data, status_code=status_code)


def db_error_response(request: Request):
    """DB 연결 실패(OperationalError) 공통 처리 — main.py 의 예외 핸들러가 사용."""
    wants_html = (request.method == "GET"
                  and "text/html" in request.headers.get("accept", "")
                  and "/api/" not in request.url.path)
    if wants_html:
        return render(request, "error_db.html", {"message": DB_ERR_MSG}, status_code=503)
    return JSONResponse({"ok": False, "db_error": True, "message": DB_ERR_MSG}, status_code=503)
