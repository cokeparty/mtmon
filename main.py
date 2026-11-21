import logging
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import settings

from core.deps import RedirectToLogin, ForbiddenPage
from core.logging_config import setup_logging

# ───────────────────────────────────────────
# 로깅 설정 (logs/ 날짜별 — 앱/접속/에러)
# ───────────────────────────────────────────
access_logger = setup_logging()
logger = logging.getLogger(__name__)
from routers import (
    auth,
    dashboard,
    program_change,
    dept_transfer,
    dml_manager,      # DML 담당자 뷰
    dml_developer,    # DML 개발자 뷰
    ddl,              # DDL (담당자 단일 뷰)
    security_log,
    admin_users,
)

# ───────────────────────────────────────────
# 기본 설정
# ───────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="모니터링 시스템")

# ───────────────────────────────────────────
# SessionMiddleware 등록
# ───────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,   # 쿠키 서명 키
    session_cookie="dml_session",
    max_age=60 * 60 * 8,                   # 8시간
    same_site="lax",
    https_only=False,                      # HTTPS 운영 시 True
)


# ───────────────────────────────────────────
# 접속/에러 로그 미들웨어
#  - 모든 요청을 access 로그에 기록 (사용자 IP·메서드·경로·상태·소요시간·사용자)
#  - 처리 중 예외는 error 로그에 트레이스백 기록 후 재발생
#  ※ SessionMiddleware 이후 등록 → 본 미들웨어가 바깥쪽 → call_next 후 세션 조회 가능
# ───────────────────────────────────────────
def _client_ip(request: Request) -> str:
    """프록시 뒤에서도 실제 클라이언트 IP를 우선 사용."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "-"


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    start = time.perf_counter()
    ip    = _client_ip(request)
    try:
        response = await call_next(request)
    except Exception:
        elapsed = (time.perf_counter() - start) * 1000
        logger.exception(
            "처리 중 예외 — %s %s ip=%s (%.1fms)",
            request.method, request.url.path, ip, elapsed,
        )
        access_logger.info(
            '%s "%s %s" 500 %.1fms user=-',
            ip, request.method, request.url.path, elapsed,
        )
        raise

    elapsed = (time.perf_counter() - start) * 1000
    user = "-"
    try:
        user = (request.session.get("name")
                or request.session.get("user_id") or "-")
    except Exception:
        pass
    access_logger.info(
        '%s "%s %s" %s %.1fms user=%s',
        ip, request.method, request.url.path, response.status_code, elapsed, user,
    )
    return response


@app.exception_handler(RedirectToLogin)
async def redirect_to_login_handler(request, exc):
    return RedirectResponse(url="/login")


@app.exception_handler(ForbiddenPage)
async def forbidden_page_handler(request: Request, exc: ForbiddenPage):
    return templates.TemplateResponse(
        "error_forbidden.html",
        {
            "request": request,
            "active": "",
            "current_user": {
                "id":   request.session.get("user_id", -1),
                "name": request.session.get("name", ""),
                "role": request.session.get("role", ""),
            },
            "message": exc.message,
        },
        status_code=403,
    )

# 정적 파일 / 템플릿 (절대경로로 안전하게)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# ───────────────────────────────────────────
# 라우터 등록
# ───────────────────────────────────────────
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(program_change.router)
app.include_router(dept_transfer.router)
app.include_router(dml_manager.router)
app.include_router(dml_developer.router)
app.include_router(ddl.router)
app.include_router(security_log.router)
app.include_router(admin_users.router)

# ───────────────────────────────────────────
# 루트 → 대시보드
# ───────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return RedirectResponse(url="/dashboard", status_code=302)


# ───────────────────────────────────────────
# 실행
# ───────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
