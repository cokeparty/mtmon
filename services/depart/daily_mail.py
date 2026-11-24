"""
부서이동자 일간 결과 메일

오늘 일간 수집 배치(depart_daily)가 조회한 행(last_seen = 오늘)을
일간 화면 '전체' 탭과 같은 구성(요약 + 퇴직자 · 부서변경자 · HR권한 · 전자조달 · PMS 표)의
HTML 메일로 보낸다. 받는 사람은 .env 의 DEPART_DAILY_MAIL_TO / _CC.
해당 건이 없거나 오늘 수집이 없어도 빈 목록으로 보낸다 (수집이 없으면 메일 위에 경고 표시).
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from config import settings
from models.common import BatchHistory
from models.depart import DailyRecord
from services.common import mail
from services.depart.service import _daily_to_dict

PERM_TYPES = ("HR권한", "전자조달권한", "PMS권한")


def _today_collect(db: Session, today: date) -> BatchHistory | None:
    """오늘 끝난 일간 수집 배치 중 마지막 것 (성공·부분성공만)"""
    return (
        db.query(BatchHistory)
        .filter(BatchHistory.job_id == "depart_daily",
                BatchHistory.status.in_(("success", "partial")),
                BatchHistory.started_at >= datetime.combine(today, datetime.min.time()))
        .order_by(BatchHistory.started_at.desc())
        .first()
    )


def build(db: Session, today: date | None = None) -> dict:
    """메일 내용 만들기 → {subject, html, text, counts, collect}"""
    from core.web import templates

    today = today or date.today()
    collect = _today_collect(db, today)      # None 이면 빈 목록 + 경고

    rows = [_daily_to_dict(r) for r in
            db.query(DailyRecord).filter(DailyRecord.last_seen == today)
              .order_by(DailyRecord.change_date, DailyRecord.empno, DailyRecord.role_code).all()]
    groups = {
        "resign": [r for r in rows if r["record_type"] in ("퇴직자", "퇴직자(협력)")],
        "dept":   [r for r in rows if r["record_type"] == "부서변경자"],
        "hr":     [r for r in rows if r["record_type"] == "HR권한"],
        "epro":   [r for r in rows if r["record_type"] == "전자조달권한"],
        "pms":    [r for r in rows if r["record_type"] == "PMS권한"],
    }
    pending = {k: sum(1 for r in groups[k] if not r["action"]) for k in ("hr", "epro", "pms")}
    counts = {k: len(v) for k, v in groups.items()}
    total_pend = sum(pending.values())

    link = ""
    if settings.APP_BASE_URL:
        link = settings.APP_BASE_URL.rstrip("/") + f"/depart/daily?year_month={today:%Y-%m}"

    html = templates.env.get_template("mail/depart_daily.html").render(
        today=today, groups=groups, counts=counts, pending=pending, total_pend=total_pend,
        collect=collect, link=link, app_env=settings.APP_ENV,
    )
    subject = (f"[부서이동자 일간] {today:%Y-%m-%d} 퇴직 {counts['resign']} · 부서변경 {counts['dept']} · "
               f"권한 {counts['hr'] + counts['epro'] + counts['pms']}건"
               + (f" (미처리 {total_pend})" if total_pend else ""))
    if settings.APP_ENV != "prod":
        subject = f"[{settings.APP_ENV}] " + subject
    text = (f"부서이동자 일간 모니터링 {today:%Y-%m-%d}\n"
            f"퇴직자 {counts['resign']}건, 부서변경자 {counts['dept']}건, "
            f"HR권한 {counts['hr']}건, 전자조달 {counts['epro']}건, PMS {counts['pms']}건 "
            f"(권한 미처리 {total_pend}건)\n" + (f"화면에서 보기: {link}\n" if link else ""))
    if collect is None:
        text = f"※ 오늘({today}) 성공한 일간 수집이 없어 목록이 비어 있습니다.\n" + text
    return {"subject": subject, "html": html, "text": text, "counts": counts,
            "pending": pending, "collect": collect}


def send(db: Session, today: date | None = None) -> dict:
    to = mail.split_addrs(settings.DEPART_DAILY_MAIL_TO)
    cc = mail.split_addrs(settings.DEPART_DAILY_MAIL_CC)
    if not to:
        raise RuntimeError("받는 사람(DEPART_DAILY_MAIL_TO)이 .env 에 설정되지 않았습니다.")
    m = build(db, today)
    mail.send_html(to, m["subject"], m["html"], m["text"], cc=cc)
    return {"subject": m["subject"], "to": to, "cc": cc, "counts": m["counts"], "pending": m["pending"],
            "no_collect": m["collect"] is None}
