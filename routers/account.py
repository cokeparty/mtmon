"""
계정관리
GET  /account                       → 계정 목록 (계정관리 조회)
POST /account/create                → 계정 생성 (계정관리 수정)
POST /account/{id}/role · toggle-active · info · email · reset-password  (계정관리 수정)

역할 목록은 역할관리(account.role)에서 읽는다.
관리자(administrator) 역할은 여기서 줄 수 없고, 관리자 계정은 여기서 바꿀 수 없다 (DB 에서만).
"""
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from config import settings
from core.permissions import ADMIN_ROLE, page_edit, page_view
from core.security import hash_password
from core.web import render
from db.database import get_db
from models.account import AppUser, Role

router = APIRouter(prefix="/account", tags=["admin"])

_LOGIN_ID_RE = re.compile(r'^[a-z0-9_]{4,20}$')


def _role_labels(db: Session, include_admin: bool = False) -> dict[str, str]:
    """{역할코드: 이름} — 역할관리 화면의 순서대로. 관리자 역할은 표시용으로만 포함한다."""
    q = db.query(Role).order_by(Role.sort_order, Role.code)
    if not include_admin:
        q = q.filter(Role.code != ADMIN_ROLE)
    return {r.code: r.name for r in q.all()}


def _target(request: Request, db: Session, user_id: int):
    """수정할 계정. 없거나 관리자 계정이면 (None, 안내 응답)."""
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        msg = "존재하지 않는 계정입니다."
    elif user.role == ADMIN_ROLE:
        msg = "관리자 계정은 앱에서 수정할 수 없습니다."
    else:
        return user, None
    request.session["flash"] = msg
    request.session["flash_type"] = "err"
    return None, RedirectResponse("/account", status_code=303)


@router.get("", response_class=HTMLResponse)
async def user_list(
    request: Request,
    current_user=Depends(page_view("account")),
    db: Session = Depends(get_db),
):
    users = db.query(AppUser).order_by(AppUser.id).all()
    flash      = request.session.pop("flash", None)
    flash_type = request.session.pop("flash_type", "ok")
    return render(request, "account.html", {
        "active":       "account",
        "users":        users,
        "role_labels":  _role_labels(db),                       # 부여 가능한 역할
        "role_names":   _role_labels(db, include_admin=True),   # 표시용 (관리자 포함)
        "admin_role":   ADMIN_ROLE,
        "flash":        flash,
        "flash_type":   flash_type,
    })


@router.post("/create")
async def user_create(
    request: Request,
    login_id: str = Form(...),
    name:     str = Form(...),
    email:    str = Form(default=""),
    role:     str = Form(...),
    current_user=Depends(page_edit("account")),
    db: Session = Depends(get_db),
):
    def _fail(msg: str):
        request.session["flash"] = msg
        request.session["flash_type"] = "err"
        return RedirectResponse("/account", status_code=303)

    if not _LOGIN_ID_RE.match(login_id):
        return _fail("아이디는 영문 소문자·숫자·_(4~20자)만 허용됩니다.")
    if not name.strip():
        return _fail("이름을 입력해주세요.")
    if role not in _role_labels(db):
        return _fail("올바른 역할을 선택해주세요.")
    if db.query(AppUser).filter(AppUser.login_id == login_id).first():
        return _fail(f"이미 사용 중인 아이디입니다: {login_id}")

    user = AppUser(
        login_id=login_id,
        name=name.strip(),
        email=email.strip() or None,
        role=role,
        password_hash=hash_password(settings.INITIAL_PASSWORD),
        active=True,
    )
    db.add(user)
    db.commit()

    request.session["flash"] = f"계정 '{login_id}' 생성 완료. 초기 비밀번호가 설정되었습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/account", status_code=303)


@router.post("/{user_id}/role")
async def user_change_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    current_user=Depends(page_edit("account")),
    db: Session = Depends(get_db),
):
    labels = _role_labels(db)
    if role not in labels:
        request.session["flash"] = "올바른 역할을 선택해주세요."
        request.session["flash_type"] = "err"
        return RedirectResponse("/account", status_code=303)

    user, fail = _target(request, db, user_id)        # 없거나 관리자 계정이면 거절
    if fail:
        return fail

    if user.id == current_user.id:
        request.session["flash"] = "자신의 역할은 변경할 수 없습니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/account", status_code=303)

    user.role = role
    db.commit()
    request.session["flash"] = f"'{user.name}' 역할을 {labels[role]}(으)로 변경했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/account", status_code=303)


@router.post("/{user_id}/toggle-active")
async def user_toggle_active(
    request: Request,
    user_id: int,
    current_user=Depends(page_edit("account")),
    db: Session = Depends(get_db),
):
    user, fail = _target(request, db, user_id)        # 없거나 관리자 계정이면 거절
    if fail:
        return fail

    if user.id == current_user.id:
        request.session["flash"] = "자신의 계정은 비활성화할 수 없습니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/account", status_code=303)

    user.active = not user.active
    db.commit()
    state = "활성화" if user.active else "비활성화"
    request.session["flash"] = f"'{user.name}' 계정을 {state}했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/account", status_code=303)


@router.post("/{user_id}/info")
async def user_update_info(
    request: Request,
    user_id: int,
    name:  str = Form(...),
    email: str = Form(default=""),
    current_user=Depends(page_edit("account")),
    db: Session = Depends(get_db),
):
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or \
              "application/json" in request.headers.get("accept", "")

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user or user.role == ADMIN_ROLE:
        msg = "존재하지 않는 계정입니다." if not user else "관리자 계정은 앱에서 수정할 수 없습니다."
        if is_ajax:
            return JSONResponse({"ok": False, "msg": msg}, status_code=404 if not user else 403)
        request.session["flash"] = msg
        request.session["flash_type"] = "err"
        return RedirectResponse("/account", status_code=303)
    if not name.strip():
        if is_ajax:
            return JSONResponse({"ok": False, "msg": "이름을 입력해주세요."}, status_code=400)
        request.session["flash"] = "이름을 입력해주세요."
        request.session["flash_type"] = "err"
        return RedirectResponse("/account", status_code=303)
    user.name  = name.strip()
    user.email = email.strip() or None
    db.commit()
    if is_ajax:
        return JSONResponse({"ok": True})
    request.session["flash"] = f"'{user.login_id}' 이름/이메일을 업데이트했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/account", status_code=303)


@router.post("/{user_id}/email")
async def user_update_email(
    request: Request,
    user_id: int,
    email:   str = Form(default=""),
    current_user=Depends(page_edit("account")),
    db: Session = Depends(get_db),
):
    user, fail = _target(request, db, user_id)        # 없거나 관리자 계정이면 거절
    if fail:
        return fail

    user.email = email.strip() or None
    db.commit()
    request.session["flash"] = f"'{user.name}' 이메일을 업데이트했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/account", status_code=303)


@router.post("/{user_id}/reset-password")
async def user_reset_password(
    request: Request,
    user_id: int,
    current_user=Depends(page_edit("account")),
    db: Session = Depends(get_db),
):
    user, fail = _target(request, db, user_id)        # 없거나 관리자 계정이면 거절
    if fail:
        return fail

    user.password_hash = hash_password(settings.INITIAL_PASSWORD)
    db.commit()
    request.session["flash"] = f"'{user.name}' 비밀번호를 초기화했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/account", status_code=303)
