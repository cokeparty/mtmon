"""
메일 발송 (SMTP) — 설정은 .env 의 SMTP_* · MAIL_FROM.
"""
from __future__ import annotations

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from config import settings

logger = logging.getLogger(__name__)


def split_addrs(value: str) -> list[str]:
    """'a@x.com, b@x.com; c@x.com' → ['a@x.com', 'b@x.com', 'c@x.com']"""
    return [a.strip() for a in re.split(r"[,;\s]+", value or "") if a.strip()]


def send_html(to: list[str], subject: str, html: str, text: str = "",
              cc: list[str] | None = None) -> None:
    """HTML 메일 1통 발송. 실패하면 예외를 그대로 던진다."""
    cc = cc or []
    if not settings.SMTP_HOST:
        raise RuntimeError("메일 서버(SMTP_HOST)가 .env 에 설정되지 않았습니다.")
    if not settings.MAIL_FROM:
        raise RuntimeError("발신자(MAIL_FROM)가 .env 에 설정되지 않았습니다.")
    if not to:
        raise RuntimeError("받는 사람이 없습니다.")

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.MAIL_FROM
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Date"] = formatdate(localtime=True)
    domain = settings.SMTP_HELO or settings.MAIL_FROM.split("@")[-1]
    msg["Message-ID"] = make_msgid(domain=domain)
    msg.set_content(text or "HTML 메일입니다. HTML 을 볼 수 있는 메일 프로그램에서 열어 주세요.")
    msg.add_alternative(html, subtype="html")

    helo = settings.SMTP_HELO or None
    if settings.SMTP_SSL:
        smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, local_hostname=helo,
                                timeout=30, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, local_hostname=helo, timeout=30)
    try:
        smtp.ehlo()
        if settings.SMTP_STARTTLS and not settings.SMTP_SSL:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg, from_addr=settings.MAIL_FROM, to_addrs=to + cc)
    finally:
        try:
            smtp.quit()
        except Exception:
            pass
    logger.info("메일 발송 — %s → %s%s", subject, ", ".join(to), f" (참조 {', '.join(cc)})" if cc else "")
