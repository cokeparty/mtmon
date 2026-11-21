"""
권한 체크 헬퍼 — 역할별 허용 기능 중앙 정의.

역할 계층 (높을수록 권한 많음):
  operator(운영자) > reviewer(검토수행자) > developer(개발자) > viewer(조회자)

원칙:
  - API 엔드포인트: 권한 부족 시 403 JSON {"ok": false, "message": PERM_DENIED_MSG}
  - 페이지 핸들러: 권한 부족 시 한국어 HTML 에러 페이지 반환
  - 프론트: 403 응답 수신 시 showToast(message, 'warn')
"""

PERM_DENIED_MSG = "권한이 부족합니다. 관리자에게 문의하세요."


def can_upload_csv(role: str) -> bool:
    """DML / DDL CSV 업로드 — 운영자 전용."""
    return role == "operator"


def can_edit_dml_developer(role: str) -> bool:
    """DML 개발자 화면 편집 (SR 적용·DML 설정·사유 저장) — 조회자 제외."""
    return role in ("operator", "reviewer", "developer")


def can_edit_dml_manager(role: str) -> bool:
    """DML 담당자 화면 편집 (SR 적용) — 운영자·검토수행자만."""
    return role in ("operator", "reviewer")


def can_edit_ddl(role: str) -> bool:
    """DDL 화면 편집 (SR 적용·저장) — 운영자·검토수행자만."""
    return role in ("operator", "reviewer")


def can_edit_program_change(role: str) -> bool:
    """프로그램변경 화면 편집 (필드 수정) — 운영자·검토수행자만."""
    return role in ("operator", "reviewer")


def can_run_monthly_batch(role: str) -> bool:
    """월간 부서이동자 배치 실행 — 운영자·검토수행자만."""
    return role in ("operator", "reviewer")


def can_run_daily_batch(role: str) -> bool:
    """일간 부서이동자 배치 실행 — 운영자만."""
    return role == "operator"


def can_daily_dept_action(role: str) -> bool:
    """일간 부서이동자 유지/회수 — 운영자·검토수행자만."""
    return role in ("operator", "reviewer")


def can_edit_daily_sr(role: str) -> bool:
    """일간 부서이동자 SR 입력 — 운영자·검토수행자·개발자 (조회자 제외)."""
    return role in ("operator", "reviewer", "developer")


def can_monthly_dept_action(role: str) -> bool:
    """월간 부서이동자 SR 입력 — 운영자·검토수행자만."""
    return role in ("operator", "reviewer")
