from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from core.deps import get_current_user
from db.database import get_db
from models.auth import AppUser
import services.dashboard_service as dashboard_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(tags=["Dashboard"])


def _default_ym() -> str:
    """월간 모니터링 기본 회차 = 전월(당월 아님)."""
    from core.periods import prev_month_ym
    return prev_month_ym()


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    period: str = Query(default=None),
    db: Session = Depends(get_db),
    current_user: AppUser = Depends(get_current_user),
):
    ym = period or _default_ym()
    data = dashboard_service.get_dashboard_data(db, ym)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "active":  "dashboard",
        "current_user": {
            "id":   current_user.id,
            "name": current_user.name,
            "role": current_user.role,
        },
        **data,
    })
