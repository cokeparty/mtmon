"""
요청 로그 미들웨어 — 접속 로그와 감사(사용자 작업) 로그를 한 곳에서 남긴다.

  access : 모든 요청 1줄  (IP · 메서드 · 경로 · 상태 · 소요시간 · 사용자)
  audit  : 데이터를 바꾸는 요청(POST/PATCH/PUT/DELETE)과 엑셀 다운로드 1줄
           → 누가 · 언제 · 무엇을(작업명) · 어떤 값으로(요청 내용) · 결과(성공/실패 메시지)
             예) 2026-11-21 10:12:03 OK   홍길동(hong) 프로그램변경 SR 입력 | PATCH /program/api/123/sr | sr_no=H01-20261027-012

라우터마다 로그 코드를 흩어 넣지 않기 위해, 작업 이름은 아래 _ACTIONS 표에서 경로로 찾는다.
새 기능을 추가하면 이 표에 한 줄만 추가하면 된다.
"""
import json
import logging
import re
import time
from urllib.parse import parse_qsl

from fastapi import Request
from starlette.responses import Response

from core.logging_config import ACCESS_LOGGER, AUDIT_LOGGER

access_logger = logging.getLogger(ACCESS_LOGGER)
audit_logger  = logging.getLogger(AUDIT_LOGGER)
logger        = logging.getLogger(__name__)

# (메서드, 경로 정규식, 작업명)
_ACTIONS: list[tuple[str, re.Pattern, str]] = [(m, re.compile(p), a) for m, p, a in [
    ("POST",  r"^/login$",                          "로그인"),
    ("POST",  r"^/logout$",                         "로그아웃"),
    ("POST",  r"^/register$",                       "회원가입"),
    ("POST",  r"^/change-password$",                "비밀번호 변경"),
    # 계정관리
    ("POST",  r"^/account/create$",                 "계정 생성"),
    ("POST",  r"^/account/\d+/role$",               "계정 역할 변경"),
    ("POST",  r"^/account/\d+/toggle-active$",      "계정 사용여부 변경"),
    ("POST",  r"^/account/\d+/info$",               "계정 정보 수정"),
    ("POST",  r"^/account/\d+/email$",              "계정 이메일 수정"),
    ("POST",  r"^/account/\d+/reset-password$",     "비밀번호 초기화"),
    # 프로그램변경
    ("PATCH", r"^/program/api/\d+/sr$",             "프로그램변경 SR 입력"),
    ("PATCH", r"^/program/api/\d+/fields$",         "프로그램변경 항목 수정"),
    ("POST",  r"^/program/api/run$",                "프로그램변경 수집 실행"),
    ("GET",   r"^/program/api/export$",             "프로그램변경 엑셀 다운로드"),
    # 부서이동자
    ("POST",  r"^/depart/daily/action$",            "부서이동자(일간) 유지/회수"),
    ("POST",  r"^/depart/daily/sr$",                "부서이동자(일간) SR 입력"),
    ("POST",  r"^/depart/daily/run$",               "부서이동자 일간 수집 실행"),
    ("POST",  r"^/depart/monthly/run$",             "부서이동자 월간 수집 실행"),
    ("POST",  r"^/depart/monthly/sr$",              "부서이동자(월간) SR 입력"),
    ("GET",   r"^/depart/monthly/excel/",           "부서이동자 엑셀 다운로드"),
    # DML
    ("POST",  r"^/dml/manager/upload$",             "DML CSV 업로드"),
    ("POST",  r"^/dml/manager/enrich$",             "DML SR 검증"),
    ("GET",   r"^/dml/manager/excel$",              "DML 엑셀 다운로드"),
    ("POST",  r"^/dml/developer/apply-sr$",         "DML SR 입력"),
    ("POST",  r"^/dml/developer/clear-sr$",         "DML SR 삭제"),
    ("POST",  r"^/dml/developer/bulk-apply-sr$",    "DML SR 일괄 입력"),
    ("POST",  r"^/dml/developer/set-dml$",          "DML 여부 변경"),
    ("POST",  r"^/dml/developer/set-reason$",       "DML 사유 입력"),
    # DDL
    ("POST",  r"^/ddl/upload$",                     "DDL CSV 업로드"),
    ("POST",  r"^/ddl/apply-sr$",                   "DDL SR 입력"),
    ("POST",  r"^/ddl/clear-sr$",                   "DDL SR 삭제"),
    ("POST",  r"^/ddl/save-reason$",                "DDL 사유 입력"),
    ("POST",  r"^/ddl/save-fields$",                "DDL 항목 수정"),
    ("GET",   r"^/ddl/excel$",                      "DDL 엑셀 다운로드"),
    # 배치
    ("POST",  r"^/batch/run/[\w-]+$",               "배치 수동 실행"),
]]

_WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
_SECRET = re.compile(r"pass|pw|secret|token", re.I)
_MAX_VALUE = 120
_MAX_BODY = 64 * 1024


def _client_ip(request: Request) -> str:
    """프록시 뒤에서도 실제 클라이언트 IP를 우선 사용."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "-"


def _action(method: str, path: str) -> str | None:
    for m, pat, name in _ACTIONS:
        if m == method and pat.search(path):
            return name
    return method + " " + path if method in _WRITE_METHODS else None


def _short(v) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False, default=str)
    s = " / ".join(x.strip() for x in s.splitlines() if x.strip())   # 감사 로그는 1요청 1줄
    return s if len(s) <= _MAX_VALUE else s[:_MAX_VALUE] + "…"


def _fields(pairs) -> str:
    out = []
    for k, v in pairs:
        if v in (None, "", [], {}):
            continue
        out.append(f"{k}=***" if _SECRET.search(str(k)) else f"{k}={_short(v)}")
    return " ".join(out)


def _describe_body(content_type: str, body: bytes) -> str:
    if not body:
        return ""
    if "multipart/form-data" in content_type:
        m = re.search(rb'filename="([^"]*)"', body[:4096])
        return "file=" + (m.group(1).decode("utf-8", "replace") if m else "?")
    if len(body) > _MAX_BODY:
        return f"(본문 {len(body)} bytes)"
    try:
        if "application/json" in content_type:
            data = json.loads(body)
            return _fields(data.items()) if isinstance(data, dict) else _short(data)
        if "application/x-www-form-urlencoded" in content_type:
            return _fields(parse_qsl(body.decode("utf-8", "replace")))
    except Exception:
        return "(본문 해석 불가)"
    return ""


def _session_user(request: Request) -> str:
    try:
        s = request.session
        name, login = s.get("name"), s.get("login_id")
        if name or login:
            return f"{name or '-'}({login or s.get('user_id', '-')})"
    except Exception:
        pass
    return "-"


async def _read_response(response: Response) -> tuple[Response, str]:
    """JSON 응답이면 ok/message 를 꺼내 결과로 쓰고, 응답은 그대로 다시 만들어 돌려준다."""
    if "application/json" not in response.headers.get("content-type", ""):
        return response, ""
    chunks = [c async for c in response.body_iterator]
    body = b"".join(chunks)
    result = ""
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            if data.get("ok") is False:
                result = "실패: " + _short(data.get("message") or data.get("detail") or "")
            elif "detail" in data and response.status_code >= 400:
                result = "실패: " + _short(data["detail"])
    except Exception:
        pass
    new = Response(content=body, status_code=response.status_code,
                   headers=dict(response.headers), media_type=response.media_type)
    return new, result


async def request_log_middleware(request: Request, call_next):
    start  = time.perf_counter()
    ip     = _client_ip(request)
    method = request.method
    path   = request.url.path
    action = _action(method, path)

    detail = ""
    if action:
        query = _fields(request.query_params.multi_items())
        body  = await request.body() if method in _WRITE_METHODS else b""
        detail = " ".join(x for x in (query, _describe_body(request.headers.get("content-type", ""), body)) if x)
        user_before = _session_user(request)

    try:
        response = await call_next(request)
    except Exception:
        ms = (time.perf_counter() - start) * 1000
        logger.exception("처리 중 예외 — %s %s ip=%s (%.1fms)", method, path, ip, ms)
        access_logger.info('%s "%s %s" 500 %.1fms user=%s', ip, method, path, ms, _session_user(request))
        if action:
            audit_logger.info("FAIL %s %s | %s %s | %s | 서버 오류(500)",
                              user_before, action, method, path, detail)
        raise

    ms = (time.perf_counter() - start) * 1000
    user = _session_user(request)
    access_logger.info('%s "%s %s" %s %.1fms user=%s', ip, method, path, response.status_code, ms, user)

    if action:
        result = ""
        if method in _WRITE_METHODS:
            response, result = await _read_response(response)
        if path == "/login":
            ok = user != "-"
            result = "" if ok else "실패: 아이디 또는 비밀번호 불일치"
        else:
            ok = response.status_code < 400 and not result
            if not ok and not result:
                result = f"실패: HTTP {response.status_code}"
        who = user if user != "-" else user_before
        audit_logger.info("%s %s %s | %s %s | %s%s",
                          "OK  " if ok else "FAIL", who, action, method, path,
                          detail or "-", f" | {result}" if result else "")
    return response
