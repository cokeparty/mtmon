"""
월간모니터링 통합대시보드 — 앱 진입점

시작 순서 (lifespan):
  1) 로그 설정            core/logging_config.py
  2) DB 구조 자동 적용     core/migrate.py   (AUTO_MIGRATE=true)
  3) 배치 스케줄러 시작    batch/scheduler.py (SCHEDULER_ENABLED=true)

실행: python main.py   또는   uvicorn main:app --host 0.0.0.0 --port 8000
"""
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError
from starlette.middleware.sessions import SessionMiddleware

from config import settings
from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

from core.deps import ForbiddenPage, RedirectToLogin  # noqa: E402
from core.permissions import (ApiForbidden, PERM_DENIED_MSG,  # noqa: E402
                              first_allowed_url, request_perms)
from core.middleware import request_log_middleware    # noqa: E402
from core.web import db_error_response, render        # noqa: E402
from routers import (                                 # noqa: E402
    account, auth, batch, dashboard, ddl, depart, dml_developer, dml_manager, program, role,
)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("앱 시작 (APP_ENV=%s)", settings.APP_ENV)
    if settings.AUTO_MIGRATE:
        from core.migrate import upgrade_to_head
        upgrade_to_head()
    from batch import scheduler
    try:
        scheduler.start()
    except Exception:
        logger.exception("배치 스케줄러 시작 실패 — 화면은 계속 동작합니다")
    yield
    scheduler.shutdown()
    logger.info("앱 종료")


app = FastAPI(title="모니터링 시스템", lifespan=lifespan)

# 미들웨어: 나중에 등록한 것이 바깥쪽 → 요청 로그가 세션을 읽을 수 있도록 세션을 먼저 등록
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="dml_session",
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",
    https_only=settings.HTTPS_ONLY,
)
app.middleware("http")(request_log_middleware)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.exception_handler(RedirectToLogin)
async def redirect_to_login_handler(request, exc):
    return RedirectResponse(url="/login")


@app.exception_handler(ForbiddenPage)
async def forbidden_page_handler(request: Request, exc: ForbiddenPage):
    return render(request, "error_forbidden.html", {"message": exc.message}, status_code=403)


@app.exception_handler(ApiForbidden)
async def api_forbidden_handler(request: Request, exc: ApiForbidden):
    return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)


@app.exception_handler(OperationalError)
async def db_error_handler(request: Request, exc: OperationalError):
    """DB 연결 실패 — 화면은 안내 페이지, API 는 503 JSON. 라우터마다 try/except 하지 않는다."""
    logger.error("DB 연결 실패 %s %s: %s", request.method, request.url.path, str(exc.orig).strip())
    return db_error_response(request)


for r in (auth, dashboard, program, depart, dml_manager, dml_developer, ddl, account, role, batch):
    app.include_router(r.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """로그인 후 첫 화면 — 접속 권한이 있는 첫 페이지 (보통 대시보드)."""
    if not request.session.get("user_id"):
        return RedirectResponse(url="/login", status_code=302)
    url = first_allowed_url(request_perms(request))
    if not url:
        raise ForbiddenPage("접속할 수 있는 페이지가 없습니다. 관리자에게 역할 권한을 요청하세요.")
    return RedirectResponse(url=url, status_code=302)


# 이름 변경 전 주소(즐겨찾기) → 새 주소로 이동
_OLD_PATHS = [(re.compile(r"^/program-change"), "/program"),
              (re.compile(r"^/dept-transfer"), "/depart"),
              (re.compile(r"^/admin/users"), "/account")]


@app.get("/{old_path:path}", include_in_schema=False)
async def legacy_redirect(old_path: str, request: Request):
    path = "/" + old_path
    for pat, new in _OLD_PATHS:
        if pat.match(path):
            url = pat.sub(new, path, count=1)
            if request.url.query:
                url += "?" + request.url.query
            return RedirectResponse(url, status_code=301)
    return HTMLResponse("페이지를 찾을 수 없습니다.", status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.APP_HOST, port=settings.APP_PORT,
                reload=settings.APP_ENV == "dev")
