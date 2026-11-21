from types import SimpleNamespace

from fastapi import Depends, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from db.database import get_db
from models.auth import AppUser


class RedirectToLogin(Exception):
    """미인증 시 /login 으로 보내기 위한 신호"""
    pass


class ForbiddenPage(Exception):
    """페이지 접근 권한 없음 — main.py 핸들러가 한국어 HTML 에러 페이지 반환."""
    def __init__(self, message: str = "이 페이지에 접근할 권한이 없습니다. 관리자에게 문의하세요."):
        self.message = message
        super().__init__(message)


def _session_user(request: Request):
    """세션에 저장된 정보만으로 임시 user 객체 생성 (DB 불가 시 폴백)."""
    return SimpleNamespace(
        id   = request.session.get("user_id", -1),
        name = request.session.get("name", "알 수 없음"),
        role = request.session.get("role", "operator"),
    )


def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        raise RedirectToLogin()

    # user_id == -1: DB 없는 환경에서 발급된 임시 세션
    if user_id == -1:
        return _session_user(request)

    try:
        user = db.query(AppUser).filter(
            AppUser.id == user_id,
            AppUser.active.is_(True),
        ).first()
    except OperationalError:
        # DB 일시 다운 → 세션 정보로 계속 사용
        return _session_user(request)

    if not user:
        request.session.clear()
        raise RedirectToLogin()

    return user


def require_operator(current_user=Depends(get_current_user)):
    """페이지 핸들러용 — 권한 없으면 한국어 HTML 에러 페이지."""
    if current_user.role != "operator":
        raise ForbiddenPage("이 페이지는 운영자(operator) 전용입니다. 관리자에게 문의하세요.")
    return current_user


def require_reviewer(current_user=Depends(get_current_user)):
    """페이지 핸들러용 — 권한 없으면 한국어 HTML 에러 페이지."""
    if current_user.role not in ("operator", "reviewer"):
        raise ForbiddenPage("이 페이지는 운영자·검토수행자 전용입니다. 관리자에게 문의하세요.")
    return current_user
