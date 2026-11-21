
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from core.permissions import page_view
from core.web import render, default_ym
from db.database import get_db
import services.dashboard as dashboard_service


router = APIRouter(tags=["Dashboard"])



@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view(
    request: Request,
    period: str = Query(default=None),
    db: Session = Depends(get_db),
    current_user = Depends(page_view("dashboard")),
):
    ym = period or default_ym()
    data = dashboard_service.get_dashboard_data(db, ym)
    return render(request, "dashboard.html", {
        "active": "dashboard",
        **data,
    })
