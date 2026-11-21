from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font
from sqlalchemy.orm import Session

from config import settings
from models.program_change import ProgramChangeLog
from services import pcl_view

HEADERS = [
    "순번", "이관시각", "접속계정", "파일명",
    "SR번호", "SR제목", "작업구분", "작업승인일", "SR종료일",
    "프로그램 변경요청·승인", "사용자테스트", "이관전 승인",
    "개발자", "이관자", "검토수행자", "검증결과", "모니터링결과",
]

GREEN  = PatternFill("solid", fgColor="C6EFCE")
YELLOW = PatternFill("solid", fgColor="FFEB9C")
RED    = PatternFill("solid", fgColor="FFC7CE")

FONT_GREEN  = Font(color="006100")
FONT_YELLOW = Font(color="9C6500")
FONT_RED    = Font(color="9C0006")

VALID_COL = HEADERS.index("검증결과") + 1  # 검증결과 셀만 색칠
# 작업승인일/SR종료일: 값은 datetime(시각 포함)으로 넣되 표시는 날짜만.
# → 셀을 클릭하면 수식줄에 시각까지 보인다.
APPR_COL  = HEADERS.index("작업승인일") + 1
CLOSE_COL = HEADERS.index("SR종료일") + 1
DATE_ONLY_FMT = "yyyy-mm-dd"


def _ui_status(r) -> str:
    """ORM 행의 검증결과(정상/비정상/미적용).

    대시보드 집계(services.dashboard_service)에서 SR DB 조회 없이 행 단위로
    호출하므로 sr_in_db=None(=result 기준 fallback)으로 위임한다.
    """
    result_val = r.result.value if hasattr(r.result, "value") else (r.result or "")
    return pcl_view.compute_ui_status(r.sr_no or "", result_val, None)


def export(db: Session, period_id: int, system_code: str) -> BytesIO:
    rows = (db.query(ProgramChangeLog)
            .filter(ProgramChangeLog.period_id == period_id,
                    ProgramChangeLog.system_code == system_code)
            .order_by(ProgramChangeLog.deploy_time).all())

    # 웹과 동일하게 SR DB 존재여부로 검증결과 산정
    sr_in_db_set = pcl_view.fetch_sr_in_db_set(
        (r.sr_no for r in rows if r.sr_no), settings.SR_DB_URL)

    wb = Workbook()
    ws = wb.active
    ws.title = "프로그램변경"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)

    for idx, r in enumerate(rows, 1):
        deploy_str = r.deploy_time.strftime("%Y-%m-%d %H:%M:%S") if r.deploy_time else ""
        sr_in_db = (None if sr_in_db_set is None
                    else (r.sr_no in sr_in_db_set if r.sr_no else None))
        ui_status = pcl_view.compute_ui_status(r.sr_no, r.result, sr_in_db)
        fname     = pcl_view.display_file_name(
            r.system_code, r.file_name, r.full_path, r.deploy_time)
        eff       = pcl_view.effective_fields(r)
        monitoring = pcl_view.monitoring_result(ui_status, r.reason)

        ws.append([
            idx,
            deploy_str,
            r.deployer or "",
            fname,
            r.sr_no or "",
            r.sr_title or "",
            r.sr_work_type or "",
            r.sr_approved_at,
            r.sr_closed_at,
            eff["approval_change_request"],
            eff["approval_user_test"],
            eff["approval_pre_deploy"],
            eff["sr_developer"],
            eff["transferer"],
            eff["sr_reviewer"],
            ui_status,
            monitoring,
        ])

        # 작업승인일/SR종료일: 표시는 날짜만, 클릭 시 시각까지(값은 datetime 그대로).
        for col in (APPR_COL, CLOSE_COL):
            c = ws.cell(row=ws.max_row, column=col)
            if c.value is not None:
                c.number_format = DATE_ONLY_FMT

        # '검증결과' 셀만 색칠 + 글씨색
        if ui_status == "정상":
            fill, font = GREEN, FONT_GREEN
        elif ui_status == "비정상":
            fill, font = YELLOW, FONT_YELLOW
        else:
            fill, font = RED, FONT_RED
        cell = ws.cell(row=ws.max_row, column=VALID_COL)
        cell.fill = fill
        cell.font = font

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf
