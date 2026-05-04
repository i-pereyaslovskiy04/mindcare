"""
SMTP diagnostic — STARTTLS port 587 with explicit SSL context.
Run from mindcare_api/ directory:
    python scripts/test_smtp.py
"""

import smtplib
import ssl
import sys
import os
from email.mime.text import MIMEText


def load_env(path=".env"):
    env = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                env[key.strip()] = val.strip()
    except FileNotFoundError:
        print(f"[ERROR] .env not found at {os.path.abspath(path)}")
        sys.exit(1)
    return env


env = load_env()
HOST     = env.get("SMTP_HOST", "")
PORT     = int(env.get("SMTP_PORT", 587))
USER     = env.get("SMTP_USER", "")
PASSWORD = env.get("SMTP_PASSWORD", "")
FROM     = env.get("SMTP_FROM", "")
TO       = USER

print("=" * 50)
print(f"  HOST:     {HOST}")
print(f"  PORT:     {PORT}")
print(f"  USER:     {USER}")
print(f"  PASSWORD: {'*' * len(PASSWORD) if PASSWORD else '(empty!)'}")
print("=" * 50)

if not all([HOST, USER, PASSWORD, FROM]):
    print("[ERROR] Одно или несколько SMTP полей пусты. Проверь .env")
    sys.exit(1)

ctx = ssl.create_default_context()
stage = "connect"

try:
    print(f"\nSTEP 1 [{stage}]: SMTP соединение на {HOST}:{PORT} ...")
    server = smtplib.SMTP(HOST, PORT, timeout=15)
    server.set_debuglevel(1)
    print(f"  OK\n")

    stage = "ehlo"
    print(f"STEP 2 [{stage}] ...")
    server.ehlo()
    print(f"  OK\n")

    stage = "starttls"
    print(f"STEP 3 [{stage}] ...")
    server.starttls(context=ctx, server_hostname=HOST)
    print(f"  OK\n")

    stage = "ehlo_after_tls"
    print(f"STEP 4 [{stage}] ...")
    server.ehlo()
    print(f"  OK\n")

    stage = "login"
    print(f"STEP 5 [{stage}]: login как {USER} ...")
    server.login(USER, PASSWORD)
    print(f"  OK\n")

    stage = "send"
    print(f"STEP 6 [{stage}]: отправка письма на {TO} ...")
    msg = MIMEText("Тест SMTP — MindCare. Если видите это, всё работает.", "plain", "utf-8")
    msg["Subject"] = "MindCare SMTP test"
    msg["From"] = FROM
    msg["To"] = TO
    server.send_message(msg)
    server.quit()
    print(f"  OK\n")

    print("=" * 50)
    print("SUCCESS: SMTP работает корректно.")
    print("=" * 50)

except smtplib.SMTPAuthenticationError as e:
    print(f"\nFAIL [{stage}] — SMTPAuthenticationError: {e}")
    print("\nПричины:")
    print("  - Неверный пароль")
    print("  - Нужен пароль приложения: mail.ru → Настройки → Безопасность → Пароли приложений")
    print("  - SMTP-доступ не включён: mail.ru → Настройки → Почтовые программы")
    server.quit()
    sys.exit(1)

except Exception as e:
    import traceback
    print(f"\nFAIL [{stage}] — {type(e).__name__}: {e}")
    traceback.print_exc()
    try:
        server.quit()
    except Exception:
        pass
    sys.exit(1)
