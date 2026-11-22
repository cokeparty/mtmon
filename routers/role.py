"""
역할관리 — 역할 추가 · 이름 변경 · 삭제, 역할별 페이지 권한(접속 불가 / 조회 / 수정) 설정
GET  /role                    → 화면                         (역할관리 조회)
POST /role/create             → 역할 추가                    (역할관리 수정)
POST /role/{code}/update      → 이름 · 설명 · 순서 변경      (역할관리 수정)
POST /role/{code}/delete      → 역할 삭제 (쓰는 계정이 있으면 불가)
POST /role/permissions        → 권한표 저장 (전체 한 번에)

권한 확인 로직은 core/permissions.py.
"""
import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from core.permissions import (ADMIN_ROLE, LEVEL_EDIT, LEVEL_LABELS, LEVEL_NONE, LEVEL_VIEW, PAGES,
                              page_edit, page_view)
from core.web import render
from db.database import get_db
from models.account import AppUser, Role, RolePermission
from routers.auth import REGISTER_ROLE

router = APIRouter(prefix="/role", tags=["role"])

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,19}$")


def _flash(request: Request, msg: str, kind: str = "ok") -> RedirectResponse:
    request.session["flash"] = msg
    request.session["flash_type"] = kind
    return RedirectResponse("/role", status_code=303)


@router.get("", response_class=HTMLResponse)
def role_page(request: Request, db: Session = Depends(get_db),
              current_user=Depends(page_view("role"))):
    roles = (db.query(Role).filter(Role.code != ADMIN_ROLE)       # 관리자 역할은 화면에 보이지 않음
             .order_by(Role.sort_order, Role.code).all())
    counts = dict(db.query(AppUser.role, func.count(AppUser.id)).group_by(AppUser.role).all())
    perms: dict[str, dict[str, int]] = {r.code: {} for r in roles}
    for rp in db.query(RolePermission).all():
        perms.setdefault(rp.role_code, {})[rp.page_code] = int(rp.level)
    return render(request, "role.html", {
        "active": "role",
        "roles": roles,
        "user_counts": counts,
        "role_perms": perms,
        "pages": PAGES,
        "levels": [(LEVEL_NONE, LEVEL_LABELS[LEVEL_NONE]), (LEVEL_VIEW, LEVEL_LABELS[LEVEL_VIEW]),
                   (LEVEL_EDIT, LEVEL_LABELS[LEVEL_EDIT])],
        "register_role": REGISTER_ROLE,
        "my_role": getattr(current_user, "role", ""),
        "flash": request.session.pop("flash", None),
        "flash_type": request.session.pop("flash_type", "ok"),
    })


@router.post("/create")
def role_create(request: Request, code: str = Form(...), name: str = Form(...),
                description: str = Form(default=""), db: Session = Depends(get_db),
                _u=Depends(page_edit("role"))):
    code, name = code.strip().lower(), name.strip()
    if not _CODE_RE.match(code):
        return _flash(request, "역할 코드는 영문 소문자로 시작하는 영문 소문자·숫자·_ 2~20자입니다.", "err")
    if not name:
        return _flash(request, "역할 이름을 입력해주세요.", "err")
    if code == ADMIN_ROLE or db.get(Role, code):
        return _flash(request, f"이미 있는 역할 코드입니다: {code}", "err")
    if db.query(Role).filter(Role.name == name).first():
        return _flash(request, f"이미 있는 역할 이름입니다: {name}", "err")
    max_order = db.query(func.max(Role.sort_order)).scalar() or 0
    db.add(Role(code=code, name=name, description=description.strip() or None, sort_order=max_order + 1))
    db.commit()
    return _flash(request, f"역할 '{name}' 을(를) 추가했습니다. 아래 권한표에서 페이지 권한을 지정하세요.")


@router.post("/{code}/update")
def role_update(code: str, request: Request, name: str = Form(...),
                description: str = Form(default=""), sort_order: int = Form(default=100),
                db: Session = Depends(get_db), _u=Depends(page_edit("role"))):
    role = db.get(Role, code)
    if not role or code == ADMIN_ROLE:
        return _flash(request, "없는 역할입니다.", "err")
    name = name.strip()
    if not name:
        return _flash(request, "역할 이름을 입력해주세요.", "err")
    dup = db.query(Role).filter(Role.name == name, Role.code != code).first()
    if dup:
        return _flash(request, f"이미 있는 역할 이름입니다: {name}", "err")
    role.name, role.description, role.sort_order = name, description.strip() or None, sort_order
    db.commit()
    return _flash(request, f"역할 '{name}' 정보를 저장했습니다.")


@router.post("/{code}/delete")
def role_delete(code: str, request: Request, db: Session = Depends(get_db),
                current_user=Depends(page_edit("role"))):
    role = db.get(Role, code)
    if not role or code == ADMIN_ROLE:
        return _flash(request, "없는 역할입니다.", "err")
    if code == REGISTER_ROLE:
        return _flash(request, f"'{role.name}' 은(는) 회원가입 시 부여하는 기본 역할이라 삭제할 수 없습니다.", "err")
    used = db.query(func.count(AppUser.id)).filter(AppUser.role == code).scalar() or 0
    if used:
        return _flash(request, f"'{role.name}' 역할을 쓰는 계정이 {used}개 있어 삭제할 수 없습니다. "
                               "계정관리에서 다른 역할로 바꾼 뒤 삭제하세요.", "err")
    db.delete(role)          # 권한표 행은 ON DELETE CASCADE 로 함께 삭제
    db.commit()
    return _flash(request, f"역할 '{role.name}' 을(를) 삭제했습니다.")


@router.post("/permissions")
async def save_permissions(request: Request, db: Session = Depends(get_db),
                           current_user=Depends(page_edit("role"))):
    """폼 값 perm__{역할코드}__{페이지코드} = 0/1/2 를 한 번에 저장."""
    form = await request.form()
    roles = {r.code for r in db.query(Role).all()} - {ADMIN_ROLE}   # 관리자 권한은 바꿀 수 없음
    pages = {c for c, _, _ in PAGES}
    wanted: dict[tuple[str, str], int] = {}
    for key, val in form.items():
        if not key.startswith("perm__"):
            continue
        try:
            _, rc, pc = key.split("__", 2)
            level = int(val)
        except ValueError:
            continue
        if rc in roles and pc in pages and level in (LEVEL_NONE, LEVEL_VIEW, LEVEL_EDIT):
            wanted[(rc, pc)] = level

    # 자기 역할에서 역할관리 수정 권한을 없애면 이 화면을 다시 못 고친다 → 막는다
    my_role = getattr(current_user, "role", "")
    if my_role != ADMIN_ROLE and wanted.get((my_role, "role"), LEVEL_EDIT) < LEVEL_EDIT:
        return _flash(request, "본인 역할의 '역할관리' 수정 권한은 없앨 수 없습니다 "
                               "(저장하면 이 화면을 다시 고칠 수 없게 됩니다). 다른 운영자 계정에서 바꾸세요.", "err")

    changed = 0
    existing = {(rp.role_code, rp.page_code): rp for rp in db.query(RolePermission).all()}
    for (rc, pc), level in wanted.items():
        cur = existing.get((rc, pc))
        if level == LEVEL_NONE:
            if cur is not None:
                db.delete(cur)
                changed += 1
        elif cur is None:
            db.add(RolePermission(role_code=rc, page_code=pc, level=level))
            changed += 1
        elif cur.level != level:
            cur.level = level
            changed += 1
    db.commit()
    return _flash(request, f"권한표를 저장했습니다 (변경 {changed}칸). 해당 역할 사용자에게 바로 적용됩니다.")
