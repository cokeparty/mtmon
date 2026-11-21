from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.deps import get_current_user
from models.auth import AppUser

BASE_DIR  = Path(__file__).resolve().parent.parent
router    = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "templates")

@router.get("/security-log", response_class=HTMLResponse)
async def security_log(request: Request, current_user: AppUser = Depends(get_current_user)):
    events = [
        {"time": "11/15 02:14", "src": "secure", "user": "admin",
         "ip": "10.0.1.45", "msg": "SSH 로그인 성공", "server": "DBSAFER-01"},
        {"time": "11/12 23:55", "src": "message", "user": "svc_batch",
         "ip": "10.0.1.22", "msg": "연속 로그인 실패 5회", "server": "DBSAFER-01"},
        {"time": "11/10 09:30", "src": "last", "user": "kimdev",
         "ip": "10.0.2.11", "msg": "로그인/로그아웃", "server": "DBSAFER-01"},
    ]
    return templates.TemplateResponse("security_log.html", {
        "request": request,
        "active":  "security_log",
        "events":  events,
        "current_user": {
            "id":   current_user.id,
            "name": current_user.name,
            "role": current_user.role,
        },
    })
