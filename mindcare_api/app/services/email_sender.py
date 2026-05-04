"""
Email transport layer.
Переключение режима: EMAIL_MODE=dev|smtp в .env
"""

import smtplib
import ssl
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Optional

from app.core.config import settings

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

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    stage = "init"
    print(f"[SMTP] host={settings.SMTP_HOST} port={settings.SMTP_PORT} user={settings.SMTP_USER}")

    try:
        stage = "connect"
        print("[SMTP] stage: connect")
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30)
        server.set_debuglevel(1)
        print("[SMTP] connect OK")

        stage = "ehlo"
        print("[SMTP] stage: ehlo")
        server.ehlo()

        stage = "starttls"
        print("[SMTP] stage: starttls")
        server.starttls(context=ctx)

        stage = "ehlo_after_tls"
        print("[SMTP] stage: ehlo after TLS")
        server.ehlo()

        stage = "login"
        print("[SMTP] stage: login")
        server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)

        stage = "send"
        print(f"[SMTP] stage: send -> {to}")
        server.send_message(msg)

        server.quit()
        print("[SMTP] OK")

    except Exception as e:
        import traceback
        print(f"[SMTP] FAIL at stage [{stage}]: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise
