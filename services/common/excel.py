"""
엑셀 출력 공용 — 모든 화면의 엑셀 다운로드는 여기서 만든다.

각 모듈은 '열 이름 + 행 데이터'만 준비해서 넘기면 된다.

    from services.common import excel
    content = excel.build("DDL모니터링", HEADERS, rows, status_col="검증결과")
    return excel.response(content, "DDL_2026-10_HR.xlsx")

  status_col   : 정상/비정상/미적용 값에 따라 색을 칠할 열 이름
  date_cols    : 값은 datetime 그대로 두고 표시만 날짜(yyyy-mm-dd)로 할 열 이름
  header_style : "bold"(기본, 굵게) | "dark"(남색 바탕 흰 글씨, 가운데 정렬)
  auto_width   : 내용 길이에 맞춰 열 너비 조정

데이터가 없어도 같은 양식(열 이름)으로 만들고, 첫 행에 "데이터가 없습니다" 를 적는다.
"""
from io import BytesIO
from typing import Iterable, Sequence
from urllib.parse import quote

from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.cell.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 검증결과 색: 정상=초록, 비정상=노랑, 미적용=빨강
STATUS_STYLE = {
    "정상":   (PatternFill("solid", fgColor="C6EFCE"), Font(color="006100")),
    "비정상": (PatternFill("solid", fgColor="FFEB9C"), Font(color="9C6500")),
    "미적용": (PatternFill("solid", fgColor="FFC7CE"), Font(color="9C0006")),
}
DATE_ONLY_FMT = "yyyy-mm-dd"

_HDR_BOLD = Font(bold=True)
NO_DATA_TEXT = "데이터가 없습니다"
_NO_DATA_FONT = Font(color="808080", italic=True)
_HDR_DARK = (PatternFill("solid", fgColor="1F3A5F"), Font(color="FFFFFF", bold=True),
             Alignment(horizontal="center"))


def build(sheet_title: str, headers: Sequence[str], rows: Iterable[Sequence], *,
          status_col: str | None = None, date_cols: Sequence[str] = (),
          header_style: str = "bold", auto_width: bool = False) -> bytes:
    """헤더 + 행 → xlsx 바이트. 대용량도 빠르게(write_only)."""
    rows = list(rows) if auto_width else rows
    wb = Workbook(write_only=True)
    ws = wb.create_sheet(sheet_title[:31])

    if auto_width:
        for i, h in enumerate(headers):
            longest = max([len(str(h))] + [len(str(r[i] or "")) for r in rows])
            ws.column_dimensions[get_column_letter(i + 1)].width = min(longest + 4, 40)

    head = []
    for h in headers:
        c = WriteOnlyCell(ws, value=h)
        if header_style == "dark":
            c.fill, c.font, c.alignment = _HDR_DARK
        else:
            c.font = _HDR_BOLD
        head.append(c)
    ws.append(head)

    status_idx = headers.index(status_col) if status_col else None
    date_idx = [headers.index(c) for c in date_cols]
    empty = True
    for r in rows:
        empty = False
        r = list(r)
        if status_idx is not None and r[status_idx] in STATUS_STYLE:
            c = WriteOnlyCell(ws, value=r[status_idx])
            c.fill, c.font = STATUS_STYLE[r[status_idx]]
            r[status_idx] = c
        for i in date_idx:
            if r[i] is not None and r[i] != "":
                c = WriteOnlyCell(ws, value=r[i])
                c.number_format = DATE_ONLY_FMT
                r[i] = c
        ws.append(r)

    if empty:
        c = WriteOnlyCell(ws, value=NO_DATA_TEXT)
        c.font = _NO_DATA_FONT
        ws.append([c])

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def response(content: bytes, filename: str, ascii_fallback: str | None = None) -> Response:
    """다운로드 응답. 한글 파일명은 RFC 5987(filename*) 로 보낸다."""
    disp = f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
    if ascii_fallback:
        disp = f'attachment; filename="{ascii_fallback}"; ' + disp[len("attachment; "):]
    return Response(content=content, media_type=XLSX_MEDIA,
                    headers={"Content-Disposition": disp})
