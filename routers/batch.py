"""
배치관리 화면
GET  /batch                  → 배치잡 목록 + 실행 이력          (배치관리 조회)
GET  /batch/history/{id}     → 이력 1건 상세 (에러 원인 · 트레이스백)
GET  /batch/excel/jobs       → 배치잡 목록 엑셀
GET  /batch/excel/history    → 실행 이력 엑셀 (전체)
POST /batch/run/{job_id}     → 수동 실행 (배치관리 수정) — 백그라운드로 시작하고 바로 응답

배치를 사람이 직접 실행하는 곳은 이 화면뿐이다 (명령줄 실행 · 다른 화면의 실행 버튼 없음).
"""
import threading
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from batch import scheduler
from batch.jobs import JOBS, JOB_MAP
from batch.runner import STALE_AFTER, run_job
from core.periods import is_valid_ym
from core.permissions import page_edit, page_view
from core.web import render
from db.database import get_db
from models.common import BatchHistory
from services.common import excel

router    = APIRouter(prefix="/batch", tags=["batch"])

HISTORY_LIMIT = 1000     # 화면에 한 번에 보여주는 최근 이력 수 (엑셀은 전체)
STATUS_LABEL = {"running": "실행 중", "success": "성공", "partial": "부분 실패", "failed": "실패",
                "skipped": "건너뜀"}


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _duration(h: BatchHistory) -> str:
    if not h.finished_at:
        return ""
    s = int((h.finished_at - h.started_at).total_seconds())
    return f"{s // 60}분 {s % 60}초" if s >= 60 else f"{s}초"


def _row(h: BatchHistory) -> dict:
    job = JOB_MAP.get(h.job_id)
    return {
        "id": h.id, "job_id": h.job_id, "job_name": job.name if job else h.job_id,
        "trigger": "자동" if h.trigger_type == "schedule" else "수동",
        "triggered_by": h.triggered_by or "", "params": h.params or "",
        "started_at": _fmt(h.started_at), "finished_at": _fmt(h.finished_at),
        "duration": _duration(h), "status": h.status,
        "status_label": STATUS_LABEL.get(h.status, h.status),
        "summary": h.summary or "", "error_type": h.error_type or "",
        "error_message": h.error_message or "", "has_detail": bool(h.error_detail),
    }


def _jobs(db: Session) -> list[dict]:
    """배치잡 목록 + 잡별 최근 실행 1건 + 다음 실행 시각."""
    last_ids = (db.query(func.max(BatchHistory.id)).group_by(BatchHistory.job_id).all())
    last = {h.job_id: h for h in db.query(BatchHistory)
            .filter(BatchHistory.id.in_([i for (i,) in last_ids])).all()}
    next_runs = scheduler.next_run_times()
    out = []
    for j in JOBS:
        h = last.get(j.job_id)
        out.append({
            "job_id": j.job_id, "name": j.name, "description": j.description,
            "schedule_desc": j.schedule_desc, "cron": j.cron,
            "next_run": _fmt(next_runs.get(j.job_id)) if next_runs.get(j.job_id) else "",
            "has_period": bool(j.param_label(j.default_params())),
            "default_ym": j.default_params().get("year_month", ""),
            "last": _row(h) if h else None,
        })
    return out


@router.get("", response_class=HTMLResponse)
def batch_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(page_view("batch")),
):
    total = db.query(func.count(BatchHistory.id)).scalar() or 0
    rows = (db.query(BatchHistory)
            .order_by(BatchHistory.started_at.desc(), BatchHistory.id.desc())
            .limit(HISTORY_LIMIT).all())
    return render(request, "batch.html", {
        "active": "batch",
        "jobs": _jobs(db),
        "history": [_row(h) for h in rows],
        "total": total, "limit": HISTORY_LIMIT,
        "scheduler_on": scheduler.is_running(),
        "now": _fmt(datetime.now()),
    })


@router.get("/history/{hid}")
def history_detail(hid: int, db: Session = Depends(get_db), _u=Depends(page_view("batch"))):
    h = db.get(BatchHistory, hid)
    if not h:
        return JSONResponse({"ok": False, "message": "이력이 없습니다."}, status_code=404)
    return {"ok": True, "row": _row(h), "error_detail": h.error_detail or ""}


@router.get("/excel/jobs")
def excel_jobs(db: Session = Depends(get_db), _u=Depends(page_view("batch"))):
    headers = ["배치잡", "잡 ID", "설명", "일정", "cron", "다음 실행", "최근 실행 결과", "최근 실행 시각", "최근 처리 결과"]
    rows = []
    for j in _jobs(db):
        last = j["last"] or {}
        rows.append([j["name"], j["job_id"], j["description"], j["schedule_desc"], j["cron"],
                     j["next_run"], last.get("status_label", ""), last.get("started_at", ""),
                     last.get("summary", "") or last.get("error_message", "")])
    content = excel.build("배치잡 목록", headers, rows, auto_width=True)
    return excel.response(content, f"배치잡목록_{datetime.now():%Y%m%d}.xlsx",
                          ascii_fallback=f"batch_jobs_{datetime.now():%Y%m%d}.xlsx")


@router.get("/excel/history")
def excel_history(db: Session = Depends(get_db), _u=Depends(page_view("batch"))):
    headers = ["시작", "종료", "배치잡", "잡 ID", "실행", "실행자", "회차", "결과", "소요",
               "처리 결과", "에러 종류", "에러 원인"]
    hist = (db.query(BatchHistory)
            .order_by(BatchHistory.started_at.desc(), BatchHistory.id.desc()).all())
    rows = []
    for h in hist:
        r = _row(h)
        rows.append([r["started_at"], r["finished_at"], r["job_name"], r["job_id"], r["trigger"],
                     r["triggered_by"], r["params"].replace("회차 ", ""), r["status_label"], r["duration"],
                     r["summary"], r["error_type"], r["error_message"]])
    content = excel.build("배치 실행 이력", headers, rows, auto_width=True)
    return excel.response(content, f"배치실행이력_{datetime.now():%Y%m%d}.xlsx",
                          ascii_fallback=f"batch_history_{datetime.now():%Y%m%d}.xlsx")


@router.post("/run/{job_id}")
def run_now(job_id: str, request: Request, year_month: str = "",
            db: Session = Depends(get_db), _u=Depends(page_edit("batch"))):
    if job_id not in JOB_MAP:
        return JSONResponse({"ok": False, "message": "없는 배치잡입니다."}, status_code=404)
    if year_month and not is_valid_ym(year_month):
        return JSONResponse({"ok": False, "message": f"회차 형식이 올바르지 않습니다: {year_month} (예: 2026-10)"},
                            status_code=400)
    running = (db.query(BatchHistory)
               .filter(BatchHistory.job_id == job_id, BatchHistory.status == "running",
                       BatchHistory.started_at > datetime.now() - STALE_AFTER).first())
    if running:
        return JSONResponse({"ok": False, "message": f"이미 실행 중입니다 (시작 {_fmt(running.started_at)})"},
                            status_code=409)
    by = request.session.get("name") or "-"
    params = {"year_month": year_month} if year_month else {}
    threading.Thread(target=run_job, args=(job_id,), daemon=True,
                     kwargs={"trigger": "manual", "by": by, "params": params}).start()
    return {"ok": True, "message": f"'{JOB_MAP[job_id].name}' 실행을 시작했습니다. 결과는 실행 이력에서 확인하세요."}
