"""
DML 그룹 수정 API — 개발자 화면 · 운영자 화면이 같은 기능을 각자 주소로 쓴다.

    /dml/developer/apply-sr ...  → '데이터변경 - 개발자 화면' 권한으로만 검사
    /dml/manager/apply-sr   ...  → '데이터변경 - 운영자 화면' 권한으로만 검사

한 화면의 수정 권한으로 다른 화면을 수정할 수 없도록 화면마다 따로 등록한다.
    add_group_api(router, "dml_developer")
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core.permissions import page_edit, page_view
from db.database import get_db
from schemas.dml import ApplySrRequest, BulkApplySrRequest, ClearSrRequest, SetDmlRequest, SetReasonRequest
import services.dml.service as dml_service


def add_group_api(router: APIRouter, page: str) -> None:
    """router 에 그룹 조회·수정 API 를 붙인다. 권한은 page 하나로만 확인한다."""
    can_view, can_edit = page_view(page), page_edit(page)

    @router.get("/group/{group_id}/logs")
    async def get_group_logs_api(group_id: int, db: Session = Depends(get_db), _u=Depends(can_view)):
        """그룹에 속한 DmlLog 행 목록."""
        try:
            return {"ok": True, "logs": dml_service.get_group_logs(group_id, db)}
        except Exception as e:
            return {"ok": False, "message": str(e)}

    @router.post("/apply-sr")
    async def apply_sr_to_group(payload: ApplySrRequest, db: Session = Depends(get_db), _u=Depends(can_edit)):
        """그룹에 SR번호 적용 (그룹 + 소속 dml_log 행 모두)."""
        try:
            group, sr_found = dml_service.apply_sr(payload.group_id, payload.sr_no.strip(), db)
            return {"ok": True, "group": group, "sr_found": sr_found}
        except ValueError as e:
            return JSONResponse({"ok": False, "message": str(e)}, status_code=404)

    @router.post("/clear-sr")
    async def clear_sr_from_group(payload: ClearSrRequest, db: Session = Depends(get_db), _u=Depends(can_edit)):
        """그룹의 SR번호 제거."""
        try:
            return {"ok": True, "group": dml_service.clear_sr(payload.group_id, db)}
        except ValueError as e:
            return JSONResponse({"ok": False, "message": str(e)}, status_code=404)

    @router.post("/set-dml")
    async def set_group_dml(payload: SetDmlRequest, db: Session = Depends(get_db), _u=Depends(can_edit)):
        """그룹의 DML여부 설정 (비DML이면 SR 없이도 정상·적용완료)."""
        try:
            return {"ok": True, "group": dml_service.set_dml(payload.group_id, payload.is_dml, db)}
        except ValueError as e:
            return JSONResponse({"ok": False, "message": str(e)}, status_code=404)

    @router.post("/bulk-apply-sr")
    async def bulk_apply_sr(payload: BulkApplySrRequest, db: Session = Depends(get_db), _u=Depends(can_edit)):
        """순번 범위 일괄 SR 적용. 비DML 및 skip_existing 대상은 건너뜀."""
        if not payload.group_ids:
            return JSONResponse({"ok": False, "message": "적용할 그룹이 없습니다."}, status_code=400)
        try:
            result = dml_service.bulk_apply_sr(payload.group_ids, payload.sr_no.strip(),
                                               payload.skip_existing, db)
            return {"ok": True, **result}
        except Exception as e:
            return JSONResponse({"ok": False, "message": str(e)}, status_code=500)

    @router.post("/set-reason")
    async def set_group_reason(payload: SetReasonRequest, db: Session = Depends(get_db), _u=Depends(can_edit)):
        """비정상 그룹의 소명 사유 저장 (최대 500자)."""
        try:
            return {"ok": True, "group": dml_service.set_reason(payload.group_id, payload.reason, db)}
        except ValueError as e:
            return JSONResponse({"ok": False, "message": str(e)}, status_code=404)
