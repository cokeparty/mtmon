"""
============================================================
 program_change.py  (routers)
------------------------------------------------------------
 [수정 내역]
 2026-xx-xx  화면 역할 변경: '실시간 수집' → '조회 전용'
   1) POST /api/collect 제거
      - 수집은 월초 배치(scripts/load_program_change.py)가 전월분을
        NFS/SR DB/업로드서버에서 한꺼번에 적재함. 웹에서 트리거 안 함.
   2) GET /api/command-preview 제거 (화면에서 명령 표시/실행 안 함)
   3) collect_orchestrator / sftp_log_collector import 제거
      (수집 로직은 배치 스크립트로 이전)
   4) CollectRequest / CollectResult 스키마 import 제거
   5) GET /api/load-info 추가
      - 푸터 표시용 배치 적재 메타(적재시각/대상회차/소스) 반환
   6) 비고 수정(PATCH /remark)은 유지 (마감 회차는 계속 차단)
============================================================
"""
import logging
from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, Request, HTTPException, Query

log = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from config import settings
from core.deps import get_current_user
from core.permissions import can_edit_program_change, can_run_monthly_batch, PERM_DENIED_MSG
from db.database import get_db
from models.auth import AppUser
from models.period import MonitoringPeriod
from models.program_change import ProgramChangeLog
from schemas.program_change import (FieldUpdate, LoadInfo, ProgramChangeListResponse,
                                     ProgramChangeRow, SrUpdate)
from services import excel_exporter, pcl_view
from services.sr_db_client import SrDbClient
from services.sr_validation import judge_validation

router = APIRouter(prefix="/program-change", tags=["program-change"])

# 실행 위치와 무관하게 항상 templates 를 가리키도록 절대경로 처리
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _period(db: Session, ym: str) -> MonitoringPeriod:
    p = db.query(MonitoringPeriod).filter(MonitoringPeriod.year_month == ym).first()
    if not p:
        raise HTTPException(404, f"회차 없음: {ym}")
    return p


# ----- 화면 -----
@router.get("", response_class=HTMLResponse)
def page(request: Request, current_user: AppUser = Depends(get_current_user)):
    return templates.TemplateResponse("program_change.html", {
        "request": request,
        "systems": ["HR", "EPRO", "SR", "PMS"],
        "active":  "program_change",
        "current_user": {
            "id":   current_user.id,
            "name": current_user.name,
            "role": current_user.role,
        },
    })


_DB_ERR_MSG = "DB 연결 실패 — 서버(203.238.192.134)에 접속할 수 없습니다."


# ----- 리스트 조회 (필터) -----
@router.get("/api/list", response_model=ProgramChangeListResponse)
def list_rows(year_month: str, system_code: str,
              source_file: str | None = None, sr_no: str | None = None,
              result: str = Query("전체"),
              db: Session = Depends(get_db)):
    try:
        p = _period(db, year_month)
        q = db.query(ProgramChangeLog).filter(
            ProgramChangeLog.period_id == p.id,
            ProgramChangeLog.system_code == system_code)
        if source_file:
            q = q.filter(ProgramChangeLog.file_name.ilike(f"%{source_file}%"))
        if sr_no:
            q = q.filter(ProgramChangeLog.sr_no.ilike(f"%{sr_no}%"))
        if result != "전체":
            q = q.filter(ProgramChangeLog.result == result)
        rows = q.order_by(ProgramChangeLog.deploy_time).all()

        # SR DB 일괄 조회 → sr_in_db 설정 (웹/엑셀 공용 헬퍼)
        sr_in_db_set = pcl_view.fetch_sr_in_db_set(
            (r.sr_no for r in rows if r.sr_no), settings.SR_DB_URL)

        row_objs = []
        for r in rows:
            obj = ProgramChangeRow.model_validate(r)
            if r.sr_no and sr_in_db_set is not None:
                obj.sr_in_db = r.sr_no in sr_in_db_set
            row_objs.append(obj)

        return ProgramChangeListResponse(
            year_month=year_month, system_code=system_code,
            total=len(row_objs),
            rows=row_objs,
        )
    except HTTPException:
        raise
    except OperationalError:
        return JSONResponse(
            {"ok": False, "db_error": True, "message": _DB_ERR_MSG,
             "total": 0, "rows": []},
            status_code=503,
        )


# ----- 배치 적재 메타 (푸터 표시용) -----
@router.get("/api/load-info", response_model=LoadInfo)
def load_info(year_month: str, system_code: str, db: Session = Depends(get_db)):
    try:
        p = _period(db, year_month)
        q = db.query(ProgramChangeLog).filter(
            ProgramChangeLog.period_id == p.id,
            ProgramChangeLog.system_code == system_code)
        row_count = q.count()
        last = q.order_by(ProgramChangeLog.created_at.desc()).first()
        return LoadInfo(
            period=year_month,
            loaded_at=last.created_at if last else None,
            row_count=row_count,
        )
    except HTTPException:
        raise
    except OperationalError:
        return JSONResponse(
            {"ok": False, "db_error": True, "message": _DB_ERR_MSG},
            status_code=503,
        )


# ----- 배치 실행 (화면 버튼) -----
_PCL_SYSTEMS = ["HR", "EPRO", "SR", "PMS"]


@router.post("/api/run")
def run_batch(request: Request, year_month: str = Query(...),
              db: Session = Depends(get_db)):
    """프로그램 변경 배치를 화면에서 실행. 4개 시스템을 대상 회차로 동기 수집.

    - 권한: 운영자·검토수행자(can_run_monthly_batch)
    - 회차 없으면 자동 생성(collect_orchestrator)
    - 시스템별 성공/실패를 함께 반환(부분 실패 허용)
    """
    if not can_run_monthly_batch(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)

    from services import collect_orchestrator
    results = []
    for sc in _PCL_SYSTEMS:
        try:
            stats = collect_orchestrator.collect(db, sc, year_month, settings.SR_DB_URL)
            results.append({"ok": True, "system_code": sc, "stats": stats})
        except PermissionError as e:
            db.rollback()
            results.append({"ok": False, "system_code": sc,
                            "error": str(e), "closed": True})
        except Exception as e:  # noqa: BLE001  (한 시스템 실패에 전체 중단 금지)
            db.rollback()
            log.exception("[프로그램변경 배치] %s/%s 실행 실패", year_month, sc)
            results.append({"ok": False, "system_code": sc, "error": str(e)})

    partial_error = any(not r.get("ok") for r in results)
    total_inserted = sum(
        int((r.get("stats") or {}).get("inserted", 0) or 0) for r in results)
    return {"ok": True, "year_month": year_month,
            "total_inserted": total_inserted,
            "partial_error": partial_error, "results": results}


# ----- SR 번호 수정 + SR DB 자동매핑 -----
@router.patch("/api/{row_id}/sr")
def update_sr(row_id: int, body: SrUpdate, request: Request, db: Session = Depends(get_db)):
    if not can_edit_program_change(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        row = db.get(ProgramChangeLog, row_id)
        if not row:
            raise HTTPException(404, "행 없음")

        sr_no = (body.sr_no or "").strip()
        row.sr_no = sr_no or None

        sr_found      = False
        sr_title      = None
        sr_work_type  = None
        sr_approved_at = None
        sr_closed_at  = None

        if sr_no:
            try:
                sr_client = SrDbClient(settings.SR_DB_URL)
                sr_df = sr_client.fetch_many_df([sr_no])
                if not sr_df.empty:
                    matched = sr_df[sr_df["SR번호"].astype(str).str.strip() == sr_no]
                    if not matched.empty:
                        r = matched.iloc[0]
                        sr_found     = True
                        sr_title     = str(r.get("SR제목") or "").strip() or None
                        sr_work_type = str(r.get("작업구분") or "").strip() or None
                        appr = r.get("작업승인일")
                        clos = r.get("SR종료일")
                        sr_approved_at = None if pd.isna(appr) else appr
                        sr_closed_at   = None if pd.isna(clos) else clos
            except Exception:
                pass

        row.sr_title      = sr_title
        row.sr_work_type  = sr_work_type
        row.sr_approved_at = sr_approved_at
        row.sr_closed_at  = sr_closed_at
        # '이관전 승인'은 SR(작업승인일) 기준 자동값. SR 변경 시 고정 저장값을 비워
        # 최신 작업승인일 vs 이관일로 즉시 재계산되게 한다(self-healing).
        row.approval_pre_deploy = None

        def _d(v):
            """응답용 날짜+시각 문자열('YYYY-MM-DD HH:MM:SS'). 화면에 시각까지 표시."""
            if v is None:
                return ""
            try:
                if pd.isna(v):
                    return ""
            except (TypeError, ValueError):
                pass
            try:
                return v.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                return str(v)

        def _parse_date(v):
            # 판정(검증결과)·이관전승인 계산은 날짜 단위. 자정 기준 datetime 으로 정규화.
            if v is None:
                return None
            from datetime import datetime as _dt
            try:
                return _dt.strptime(str(v)[:10], "%Y-%m-%d")
            except ValueError:
                return None

        # 검증결과 계산 후 DB에도 반영 (새로고침 시 일관성 유지)
        if not sr_no:
            ui_status = "미적용"
            row.result    = "SR없음"
            row.normal_yn = "이상"
        elif not sr_found:
            ui_status = "미적용"
            row.result    = "SR없음"
            row.normal_yn = "이상"
        else:
            vr = judge_validation(
                row.deploy_time,
                _parse_date(sr_approved_at),
                _parse_date(sr_closed_at),
                sr_work_type or "",
            )
            if vr == "정상":
                ui_status     = "정상"
                row.result    = "정상"
                row.normal_yn = "정상"
            else:
                ui_status     = "비정상"
                row.result    = "이상"
                row.normal_yn = "이상"

        log.info(
            "[프로그램변경] SR 저장 row_id=%d | sr_no=%s | sr_found=%s "
            "| sr_work_type=%s | sr_approved_at=%s | sr_closed_at=%s | 검증결과=%s",
            row_id, sr_no or "(없음)", sr_found,
            sr_work_type or "-", _d(sr_approved_at), _d(sr_closed_at), ui_status,
        )
        db.commit()

        return {
            "ok":           True,
            "sr_found":     sr_found,
            "sr_title":     sr_title or "",
            "sr_work_type": sr_work_type or "",
            "sr_approved_at": _d(sr_approved_at),
            "sr_closed_at":   _d(sr_closed_at),
            "ui_status":    ui_status,
            "monitoring_result": pcl_view.monitoring_result(ui_status, row.reason),
            # SR 변경 시 '이관전 승인' 디폴트(작업승인일 기준)도 갱신될 수 있음
            "eff_approval_pre_deploy": pcl_view._pick(
                row.approval_pre_deploy,
                pcl_view.default_pre_deploy(row.deploy_time, _parse_date(sr_approved_at))),
        }
    except HTTPException:
        raise
    except OperationalError:
        return JSONResponse({"ok": False, "message": _DB_ERR_MSG}, status_code=503)


# ----- 편집 칼럼 저장 (결재/이관자/개발자/검토수행자/사유) -----
@router.patch("/api/{row_id}/fields")
def update_fields(row_id: int, body: FieldUpdate, request: Request, db: Session = Depends(get_db)):
    if not can_edit_program_change(request.session.get("role", "")):
        return JSONResponse({"ok": False, "message": PERM_DENIED_MSG}, status_code=403)
    try:
        row = db.get(ProgramChangeLog, row_id)
        if not row:
            raise HTTPException(404, "행 없음")

        # 보낸 필드만 반영 (빈 문자열은 None 으로 저장 → 디폴트 재적용)
        sent = body.model_dump(exclude_unset=True)
        for k, v in sent.items():
            v = (v or "").strip() if isinstance(v, str) else v
            setattr(row, k, v or None)
        db.commit()
        db.refresh(row)

        obj = ProgramChangeRow.model_validate(row)
        # 검증결과는 SR DB 존재여부에 의존 → 단건 재조회
        if row.sr_no:
            s = pcl_view.fetch_sr_in_db_set([row.sr_no], settings.SR_DB_URL)
            if s is not None:
                obj.sr_in_db = row.sr_no in s
        return {
            "ok": True,
            "ui_status": obj.ui_status,
            "monitoring_result": obj.monitoring_result,
            "eff": {
                "approval_change_request": obj.eff_approval_change_request,
                "approval_user_test":      obj.eff_approval_user_test,
                "approval_pre_deploy":     obj.eff_approval_pre_deploy,
                "transferer":              obj.eff_transferer,
                "sr_developer":            obj.eff_sr_developer,
                "sr_reviewer":             obj.eff_sr_reviewer,
            },
            "reason": row.reason or "",
        }
    except HTTPException:
        raise
    except OperationalError:
        return JSONResponse({"ok": False, "message": _DB_ERR_MSG}, status_code=503)


# ----- 엑셀 출력 -----
@router.get("/api/export")
def export(year_month: str, system_code: str, db: Session = Depends(get_db)):
    try:
        p = _period(db, year_month)
        buf = excel_exporter.export(db, p.id, system_code)
        fname = f"{system_code}_프로그램변경_리스트_{year_month.replace('-', '')}.xlsx"
        # 한글 파일명 → RFC 5987(filename*) + ASCII fallback
        from urllib.parse import quote
        ascii_fallback = f"program_change_{system_code}_{year_month}.xlsx"
        disp = (f"attachment; filename=\"{ascii_fallback}\"; "
                f"filename*=UTF-8''{quote(fname)}")
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": disp},
        )
    except HTTPException:
        raise
    except OperationalError:
        raise HTTPException(503, _DB_ERR_MSG)
