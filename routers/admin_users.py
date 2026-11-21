import re
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from config import settings
from core.deps import require_operator, get_current_user
from core.security import hash_password
from db.database import get_db
from models.auth import AppUser

router = APIRouter(prefix="/admin/users", tags=["admin"])
BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

_LOGIN_ID_RE = re.compile(r'^[a-z0-9_]{4,20}$')
_VALID_ROLES = {"operator", "developer", "reviewer", "viewer"}
_ROLE_LABELS = {"operator": "운영자", "developer": "개발자", "reviewer": "검토자", "viewer": "조회자"}


@router.get("", response_class=HTMLResponse)
async def user_list(
    request: Request,
    current_user=Depends(require_operator),
    db: Session = Depends(get_db),
):
    users = db.query(AppUser).order_by(AppUser.id).all()
    flash      = request.session.pop("flash", None)
    flash_type = request.session.pop("flash_type", "ok")
    return templates.TemplateResponse("admin_users.html", {
        "request":      request,
        "current_user": current_user,
        "active":       "admin_users",
        "users":        users,
        "role_labels":  _ROLE_LABELS,
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
    current_user=Depends(require_operator),
    db: Session = Depends(get_db),
):
    def _fail(msg: str):
        request.session["flash"] = msg
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    if not _LOGIN_ID_RE.match(login_id):
        return _fail("아이디는 영문 소문자·숫자·_(4~20자)만 허용됩니다.")
    if not name.strip():
        return _fail("이름을 입력해주세요.")
    if role not in _VALID_ROLES:
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
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/{user_id}/role")
async def user_change_role(
    request: Request,
    user_id: int,
    role: str = Form(...),
    current_user=Depends(require_operator),
    db: Session = Depends(get_db),
):
    if role not in _VALID_ROLES:
        request.session["flash"] = "올바른 역할을 선택해주세요."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        request.session["flash"] = "존재하지 않는 계정입니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    if user.id == current_user.id:
        request.session["flash"] = "자신의 역할은 변경할 수 없습니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    user.role = role
    db.commit()
    request.session["flash"] = f"'{user.name}' 역할을 {_ROLE_LABELS[role]}(으)로 변경했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/{user_id}/toggle-active")
async def user_toggle_active(
    request: Request,
    user_id: int,
    current_user=Depends(require_operator),
    db: Session = Depends(get_db),
):
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        request.session["flash"] = "존재하지 않는 계정입니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    if user.id == current_user.id:
        request.session["flash"] = "자신의 계정은 비활성화할 수 없습니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    user.active = not user.active
    db.commit()
    state = "활성화" if user.active else "비활성화"
    request.session["flash"] = f"'{user.name}' 계정을 {state}했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/{user_id}/info")
async def user_update_info(
    request: Request,
    user_id: int,
    name:  str = Form(...),
    email: str = Form(default=""),
    current_user=Depends(require_operator),
    db: Session = Depends(get_db),
):
    is_ajax = request.headers.get("x-requested-with") == "XMLHttpRequest" or \
              "application/json" in request.headers.get("accept", "")

    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        if is_ajax:
            return JSONResponse({"ok": False, "msg": "존재하지 않는 계정입니다."}, status_code=404)
        request.session["flash"] = "존재하지 않는 계정입니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)
    if not name.strip():
        if is_ajax:
            return JSONResponse({"ok": False, "msg": "이름을 입력해주세요."}, status_code=400)
        request.session["flash"] = "이름을 입력해주세요."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)
    user.name  = name.strip()
    user.email = email.strip() or None
    db.commit()
    if is_ajax:
        return JSONResponse({"ok": True})
    request.session["flash"] = f"'{user.login_id}' 이름/이메일을 업데이트했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/{user_id}/email")
async def user_update_email(
    request: Request,
    user_id: int,
    email:   str = Form(default=""),
    current_user=Depends(require_operator),
    db: Session = Depends(get_db),
):
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        request.session["flash"] = "존재하지 않는 계정입니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    user.email = email.strip() or None
    db.commit()
    request.session["flash"] = f"'{user.name}' 이메일을 업데이트했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/{user_id}/reset-password")
async def user_reset_password(
    request: Request,
    user_id: int,
    current_user=Depends(require_operator),
    db: Session = Depends(get_db),
):
    user = db.query(AppUser).filter(AppUser.id == user_id).first()
    if not user:
        request.session["flash"] = "존재하지 않는 계정입니다."
        request.session["flash_type"] = "err"
        return RedirectResponse("/admin/users", status_code=303)

    user.password_hash = hash_password(settings.INITIAL_PASSWORD)
    db.commit()
    request.session["flash"] = f"'{user.name}' 비밀번호를 초기화했습니다."
    request.session["flash_type"] = "ok"
    return RedirectResponse("/admin/users", status_code=303)
