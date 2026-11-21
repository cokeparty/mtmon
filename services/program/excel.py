"""프로그램변경 엑셀 — 열 정의와 행 데이터만 만들고, 파일은 services/common/excel.py 가 만든다."""
from sqlalchemy.orm import Session

from models.program import ProgramChangeLog
from services.common import excel, sr
from services.common.fmt import fmt_datetime
from services.program import view as pcl_view

HEADERS = [
    "순번", "이관시각", "접속계정", "파일명",
    "SR번호", "SR제목", "작업구분", "작업승인일", "SR종료일",
    "프로그램 변경요청·승인", "사용자테스트", "이관전 승인",
    "개발자", "이관자", "검토수행자", "검증결과", "모니터링결과",
]


def export(db: Session, period_id: int | None, system_code: str) -> bytes:
    """period_id 가 None(회차 없음)이면 빈 양식."""
    rows = [] if period_id is None else (
        db.query(ProgramChangeLog)
        .filter(ProgramChangeLog.period_id == period_id,
                ProgramChangeLog.system_code == system_code)
        .order_by(ProgramChangeLog.deploy_time).all())

    # 웹 화면과 동일하게 SR DB 존재여부로 검증결과 산정
    in_db = sr.existing_set(r.sr_no for r in rows)

    out = []
    for idx, r in enumerate(rows, 1):
        sr_in_db = None if in_db is None else (r.sr_no in in_db if r.sr_no else None)
        status = pcl_view.compute_ui_status(r.sr_no, r.result, sr_in_db)
        eff = pcl_view.effective_fields(r)
        out.append([
            idx, fmt_datetime(r.deploy_time), r.deployer or "",
            pcl_view.display_file_name(r.system_code, r.file_name, r.full_path, r.deploy_time),
            r.sr_no or "", r.sr_title or "", r.sr_work_type or "",
            r.sr_approved_at, r.sr_closed_at,
            eff["approval_change_request"], eff["approval_user_test"], eff["approval_pre_deploy"],
            eff["sr_developer"], eff["transferer"], eff["sr_reviewer"],
            status, pcl_view.monitoring_result(status, r.reason),
        ])
    # 작업승인일/SR종료일: 값은 datetime(시각 포함), 표시는 날짜만 → 셀 클릭 시 시각까지 보임
    return excel.build("프로그램변경", HEADERS, out, status_col="검증결과",
                       date_cols=("작업승인일", "SR종료일"))
