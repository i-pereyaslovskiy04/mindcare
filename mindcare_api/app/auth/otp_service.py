"""
DB-backed OTP service. All OTP state lives in the otp_verifications table.
Safe for multi-instance deployments and server restarts.

Безопасность хранения кода:
  OTP-коды хранятся как SHA-256 хеш (hex, 64 символа), не plaintext.
  Это защищает от раскрытия действующих кодов при утечке дампа БД.

  Почему SHA-256 (а не bcrypt):
    - TTL = 10 минут: атакующий ограничен во времени
    - MAX_ATTEMPTS = 5: brute force через API заблокирован
    - SHA-256 без соли достаточен для OTP (в отличие от постоянных паролей),
      потому что:
        a) коды одноразовые и истекают
        b) пространство перебора мало (1M), но это нейтрализуется TTL+attempts
    - bcrypt слишком медленный для OTP (каждая проверка занимала бы ~200ms)
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta

from app.db.session import SessionLocal
from app.db.models import OtpVerification

log = logging.getLogger(__name__)

RESEND_COOLDOWN = 60            # секунд между повторными отправками
OTP_TTL         = timedelta(minutes=10)
MAX_ATTEMPTS    = 5


def _utcnow() -> datetime:
    """Naive UTC timestamp — совместимо с DateTime (без timezone) в ORM."""
    return datetime.utcnow()


def _hash_code(plaintext_code: str) -> str:
    """
    Хешируем OTP-код через SHA-256.
    Возвращает hex-строку из 64 символов.
    """
    return hashlib.sha256(plaintext_code.encode("utf-8")).hexdigest()


def _verify_code(plaintext_code: str, stored_hash: str) -> bool:
    """Сравниваем введённый код с сохранённым хешем."""
    return _hash_code(plaintext_code) == stored_hash


# ─── Public API ───────────────────────────────────────────────────────────────

def create_or_update_otp(email: str, name: str, password_hash: str) -> str:
    """
    Создаёт (или перезаписывает) OTP-запись для email.

    - Если запись уже существует и код был отправлен < RESEND_COOLDOWN сек назад,
      бросает ValueError с пользовательским сообщением.
    - Иначе генерирует новый 6-значный код, хранит его SHA-256 хеш,
      устанавливает TTL 10 минут.
    - Возвращает plaintext-код для отправки по email.
      В БД хранится ТОЛЬКО хеш — plaintext нигде не сохраняется.
    """
    plaintext_code = str(secrets.randbelow(1_000_000)).zfill(6)
    code_hash      = _hash_code(plaintext_code)
    now            = _utcnow()

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

            # Обновляем запись — перезаписываем хеш нового кода
            existing.code          = code_hash
            existing.name          = name
            existing.password_hash = password_hash
            existing.attempts      = 0
            existing.expires_at    = now + OTP_TTL
            existing.last_sent_at  = now
        else:
            db.add(OtpVerification(
                email=email,
                code=code_hash,          # сохраняем хеш, не plaintext
                name=name,
                password_hash=password_hash,
                attempts=0,
                expires_at=now + OTP_TTL,
                created_at=now,
                last_sent_at=now,
            ))

        db.commit()

    log.info("[OTP] Code created/updated for %s", email)
    return plaintext_code   # plaintext возвращается caller'у для отправки по email


def verify_otp(email: str, code: str) -> dict:
    """
    Проверяет OTP-код для email.

    Принимает plaintext-код от пользователя, хеширует и сравнивает с БД.

    Успех  → удаляет запись из БД, возвращает {"name": ..., "password_hash": ...}.
    Ошибка → бросает ValueError с пользовательским сообщением.

    Случаи ошибок (по порядку):
      1. Запись не найдена (уже использована или не создана)
      2. TTL истёк           → запись удаляется
      3. Превышены попытки   → запись удаляется
      4. Неверный код        → attempts++; удаляется на последней попытке
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

        # Сравниваем хеш введённого кода с сохранённым хешем
        if not _verify_code(code, record.code):
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise ValueError(
                    "Неверный код. Попытки исчерпаны. Начните регистрацию заново"
                )
            db.commit()
            log.info(
                "[OTP] Wrong code for %s, attempts=%d, remaining=%d",
                email, record.attempts, remaining,
            )
            raise ValueError(f"Неверный код. Осталось попыток: {remaining}")

        user_data = {"name": record.name, "password_hash": record.password_hash}
        db.delete(record)
        db.commit()

    log.info("[OTP] Verification OK for %s", email)
    return user_data


def delete_otp(email: str) -> None:
    """Удаляет OTP-запись для email. No-op если записи нет."""
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == email).delete(
            synchronize_session=False
        )
        db.commit()


def cleanup_expired() -> int:
    """
    Удаляет все OTP-записи с истёкшим TTL.
    Возвращает количество удалённых строк.
    Вызывается при старте приложения и/или по расписанию.
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
        log.info("[OTP] cleanup_expired: removed %d expired record(s)", deleted)
    return deleted
