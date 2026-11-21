import re
from pathlib import Path

from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from config import settings
from core.deps import get_current_user
from db.database import get_db
from models.auth import AppUser
from core.security import verify_password, hash_password

router = APIRouter()
BASE_DIR  = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

_LOGIN_ID_RE = re.compile(r'^[a-z0-9_]{4,20}$')
_VALID_ROLES = {"operator", "developer", "reviewer", "viewer"}


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    # 이미 로그인 상태면 대시보드로
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_submit(
    request: Request,
    login_id: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    def _login_error(msg: str):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": msg, "login_id": login_id},
            status_code=401,
        )

    # ── DB 조회 시도 ──────────────────────────────────────
    try:
        user = db.query(AppUser).filter(
            AppUser.login_id == login_id,
            AppUser.active.is_(True),
        ).first()
    except OperationalError:
        # DB 연결 불가 → 임시 계정으로 폴백 (설정돼 있을 때만)
        dev_id = settings.DEV_LOGIN_ID
        dev_pw = settings.DEV_LOGIN_PW
        if dev_id and login_id == dev_id and password == dev_pw:
            request.session.clear()
            request.session["user_id"] = -1
            request.session["name"]    = settings.DEV_USER_NAME
            request.session["role"]    = settings.DEV_USER_ROLE
            return RedirectResponse("/", status_code=303)
        return _login_error("DB에 연결할 수 없습니다. 임시 계정을 사용하거나 관리자에게 문의하세요.")

    # 사용자 없음 / 비번 불일치 → 동일 메시지(계정 존재 여부 노출 방지)
    if not user or not verify_password(password, user.password_hash):
        return _login_error("아이디 또는 비밀번호가 올바르지 않습니다.")

    # 세션 고정 공격 방지: 로그인 성공 시 세션 갱신
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["role"]    = user.role
    request.session["name"]    = user.name

    return RedirectResponse("/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ── 회원가입 ────────────────────────────────────────────────────
@router.get("/register", response_class=HTMLResponse)
async def register_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("register.html", {
        "request": request,
        "error": None,
        "success": None,
        "form": {},
    })


@router.post("/register")
async def register_submit(
    request: Request,
    login_id: str = Form(...),
    name:     str = Form(...),
    email:    str = Form(default=""),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    # 회원가입은 항상 viewer 고정
    role = "viewer"
    form_data = {
        "login_id": login_id,
        "name":     name,
        "email":    email,
    }

    def err(msg: str):
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": msg, "success": None, "form": form_data},
            status_code=400,
        )

    if not _LOGIN_ID_RE.match(login_id):
        return err("아이디는 영문 소문자·숫자·_(4~20자)만 허용됩니다.")
    if not name.strip():
        return err("이름을 입력해주세요.")
    if len(password) < 8:
        return err("비밀번호는 8자 이상이어야 합니다.")
    if password != password_confirm:
        return err("비밀번호가 일치하지 않습니다.")

    if db.query(AppUser).filter(AppUser.login_id == login_id).first():
        return err("이미 사용 중인 아이디입니다.")

    user = AppUser(
        login_id=login_id,
        name=name.strip(),
        email=email.strip() or None,
        role=role,
        password_hash=hash_password(password),
        active=True,
    )
    db.add(user)
    db.commit()

    return templates.TemplateResponse("register.html", {
        "request": request,
        "error":   None,
        "success": "계정이 생성되었습니다. 조회자(viewer) 역할로 가입되었으며, 다른 역할이 필요하면 관리자에게 문의해 주세요.",
        "form":    {},
    })


# ── 비밀번호 변경 ────────────────────────────────────────────────
@router.get("/change-password", response_class=HTMLResponse)
async def change_password_form(
    request: Request,
    current_user: AppUser = Depends(get_current_user),
):
    return templates.TemplateResponse("change_password.html", {
        "request":      request,
        "current_user": current_user,
        "error":        None,
        "success":      None,
    })


@router.post("/change-password")
async def change_password_submit(
    request: Request,
    current_password:  str = Form(...),
    new_password:      str = Form(...),
    new_password_confirm: str = Form(...),
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    def _err(msg: str):
        return templates.TemplateResponse("change_password.html", {
            "request":      request,
            "current_user": current_user,
            "error":        msg,
            "success":      None,
        }, status_code=400)

    if not verify_password(current_password, current_user.password_hash):
        return _err("현재 비밀번호가 올바르지 않습니다.")
    if len(new_password) < 8:
        return _err("새 비밀번호는 8자 이상이어야 합니다.")
    if new_password != new_password_confirm:
        return _err("새 비밀번호가 일치하지 않습니다.")
    if new_password == current_password:
        return _err("새 비밀번호는 현재 비밀번호와 달라야 합니다.")

    user = db.query(AppUser).filter(AppUser.id == current_user.id).first()
    user.password_hash = hash_password(new_password)
    db.commit()

    return templates.TemplateResponse("change_password.html", {
        "request":      request,
        "current_user": current_user,
        "error":        None,
        "success":      "비밀번호가 변경되었습니다.",
    })
