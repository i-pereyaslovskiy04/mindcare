"""
Email transport layer.
Переключение режима: EMAIL_MODE=dev|smtp в .env
"""

import logging
import smtplib
import ssl
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

from app.core.config import settings

log = logging.getLogger(__name__)

_SENDER_NAME = "Психология ДонГУ"


def send_email(
    to: str,
    subject: str,
    body: str,
    html: Optional[str] = None,
) -> None:
    if settings.EMAIL_MODE == "smtp":
        _send_smtp(to, subject, body, html)
    else:
        _send_dev(to, subject, body, html)


# ─── Transport implementations ────────────────────────────────────────────────

def _send_dev(to: str, subject: str, body: str, html: Optional[str]) -> None:
    print("\n" + "=" * 50)
    print(f"[EMAIL DEV] To:      {to}")
    print(f"[EMAIL DEV] Subject: {subject}")
    print(f"[EMAIL DEV] Body:\n{body}")
    if html:
        print(f"[EMAIL DEV] HTML:    <{len(html)} chars>")
    print("=" * 50 + "\n")


def _send_smtp(to: str, subject: str, body: str, html: Optional[str]) -> None:
    if settings.SMTP_TLS and settings.SMTP_SSL:
        raise RuntimeError("SMTP_TLS and SMTP_SSL cannot both be enabled")

    # Build MIME message: multipart/alternative when HTML is provided,
    # plain text otherwise.
    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html,  "html",  "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")

    # RFC 2047-encode the Cyrillic sender display name so all clients render it.
    encoded_name = str(Header(_SENDER_NAME, "utf-8"))
    msg["From"]    = formataddr((encoded_name, settings.SMTP_FROM))
    msg["To"]      = to
    msg["Subject"] = subject

    log.info("[SMTP] connecting host=%s port=%d tls=%s ssl=%s",
             settings.SMTP_HOST, settings.SMTP_PORT,
             settings.SMTP_TLS, settings.SMTP_SSL)

    if settings.SMTP_SSL:
        conn = smtplib.SMTP_SSL(
            settings.SMTP_HOST, settings.SMTP_PORT,
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        if not settings.SMTP_TLS:
            log.warning(
                "[SMTP] SMTP is configured without TLS/SSL. "
                "Credentials may be exposed if SMTP_USER/SMTP_PASSWORD are used."
            )
        conn = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)

    with conn as server:
        if settings.SMTP_TLS and not settings.SMTP_SSL:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)

    log.info("[SMTP] message sent to %s", to)
