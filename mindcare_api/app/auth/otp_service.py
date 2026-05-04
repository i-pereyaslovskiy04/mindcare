"""
DB-backed OTP service. All OTP state lives in the otp_verifications MySQL table.
Replaces the former in-memory otp_store.py — safe for multi-instance deployments
and server restarts.
"""

import secrets
from datetime import datetime, timedelta

from app.db.session import SessionLocal
from app.db.models import OtpVerification

RESEND_COOLDOWN = 60            # seconds before a new code can be requested
OTP_TTL         = timedelta(minutes=10)
MAX_ATTEMPTS    = 5


def _utcnow() -> datetime:
    """Naive UTC timestamp — consistent with MySQL DATETIME column storage."""
    return datetime.utcnow()


# ─── Public API ───────────────────────────────────────────────────────────────

def create_or_update_otp(email: str, name: str, password_hash: str) -> str:
    """
    Create (or overwrite) the OTP record for *email*.

    - If a record already exists and was sent < RESEND_COOLDOWN seconds ago,
      raises ValueError with a user-facing cooldown message.
    - Otherwise writes a fresh 6-digit code with a 10-minute TTL.
    - Returns the plaintext code so the caller can send it by email.
    """
    code = str(secrets.randbelow(1_000_000)).zfill(6)
    now  = _utcnow()

    with SessionLocal() as db:
        existing = (
            db.query(OtpVerification)
            .filter(OtpVerification.email == email)
            .first()
        )

        if existing:
            elapsed = (now - existing.last_sent_at).total_seconds()
            if elapsed < RESEND_COOLDOWN:
                wait = int(RESEND_COOLDOWN - elapsed)
                raise ValueError(f"Повторная отправка доступна через {wait} с")

            existing.code          = code
            existing.name          = name
            existing.password_hash = password_hash
            existing.attempts      = 0
            existing.expires_at    = now + OTP_TTL
            existing.last_sent_at  = now
        else:
            db.add(OtpVerification(
                email=email,
                code=code,
                name=name,
                password_hash=password_hash,
                attempts=0,
                expires_at=now + OTP_TTL,
                created_at=now,
                last_sent_at=now,
            ))

        db.commit()

    print(f"[OTPService] OTP created/updated for {email}")
    return code


def verify_otp(email: str, code: str) -> dict:
    """
    Verify *code* for *email*.

    Success  → deletes the DB record, returns {"name": ..., "password_hash": ...}.
    Failure  → raises ValueError with a user-facing Russian message.

    Failure cases (in order):
      1. No record found (already used or never created)
      2. TTL expired             → record deleted
      3. Max attempts exceeded   → record deleted
      4. Wrong code              → attempts incremented; record deleted on last attempt
    """
    now = _utcnow()

    with SessionLocal() as db:
        record = (
            db.query(OtpVerification)
            .filter(OtpVerification.email == email)
            .first()
        )

        if not record:
            raise ValueError("Код не найден или уже использован")

        if now > record.expires_at:
            db.delete(record)
            db.commit()
            raise ValueError("Срок действия кода истёк. Начните регистрацию заново")

        if record.attempts >= MAX_ATTEMPTS:
            db.delete(record)
            db.commit()
            raise ValueError("Превышено число попыток. Начните регистрацию заново")

        if record.code != code:
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise ValueError("Неверный код. Попытки исчерпаны. Начните регистрацию заново")
            db.commit()
            print(f"[OTPService] wrong code for {email}, attempts={record.attempts}, remaining={remaining}")
            raise ValueError(f"Неверный код. Осталось попыток: {remaining}")

        user_data = {"name": record.name, "password_hash": record.password_hash}
        db.delete(record)
        db.commit()

    print(f"[OTPService] verify_otp OK for {email}")
    return user_data


def delete_otp(email: str) -> None:
    """Remove the OTP record for *email*. No-op if no record exists."""
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == email).delete(
            synchronize_session=False
        )
        db.commit()


def cleanup_expired() -> int:
    """
    Delete all OTP records whose TTL has elapsed.
    Returns the number of rows removed.
    Intended to run at application startup and/or on a schedule.
    """
    now = _utcnow()
    with SessionLocal() as db:
        deleted = (
            db.query(OtpVerification)
            .filter(OtpVerification.expires_at < now)
            .delete(synchronize_session=False)
        )
        db.commit()

    if deleted:
        print(f"[OTPService] cleanup_expired: removed {deleted} expired record(s)")
    return deleted
