"""
DB-backed OTP service. All OTP state lives in the otp_verifications table.
Safe for multi-instance deployments and server restarts.

Безопасность хранения кода:
  OTP-коды хранятся как SHA-256 хеш (hex, 64 символа), не plaintext.
  Это защищает от раскрытия действующих кодов при утечке дампа БД.

Выпуск кода обычной регистрации (issue_registration_otp):
  Каждый выпуск — НОВАЯ строка с новым id (UUIDv4). Этот id — registration
  reference из ссылки в письме (/register/confirm#r=<id>): он выбирает
  конкретный выпуск, но ничего не подтверждает без кода. Новый выпуск после
  cooldown удаляет прежние записи этого email (старый код и старая ссылка
  перестают действовать после commit). Отказ по cooldown ничего не меняет.

Сериализация по email:
  Все операции, создающие или меняющие OTP по email (обычная регистрация,
  reset, регистрация через провайдера) и подтверждение обычной регистрации
  берут transaction-scoped advisory lock на нормализованный email
  (lock_email_otp) — в том числе когда строки ещё нет (FOR UPDATE её бы не
  защитил). Поэтому на один email приходится не больше одной записи OTP.

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
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import sqlalchemy as sa

from app.core.normalization import normalize_email, mask_email
from app.db.session import SessionLocal
from app.db.models import OtpVerification, User
from app.auth.errors import (
    OtpExpiredError, OtpInvalidError, RegistrationEmailTakenError,
)

log = logging.getLogger(__name__)

RESEND_COOLDOWN = 60            # секунд между повторными отправками
OTP_TTL         = timedelta(minutes=10)
MAX_ATTEMPTS    = 5


def _utcnow() -> datetime:
    """Naive UTC timestamp — совместимо с DateTime (без timezone) в ORM."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_code(plaintext_code: str) -> str:
    """
    Хешируем OTP-код через SHA-256.
    Возвращает hex-строку из 64 символов.
    """
    return hashlib.sha256(plaintext_code.encode("utf-8")).hexdigest()


def _verify_code(plaintext_code: str, stored_hash: str) -> bool:
    """Сравниваем введённый код с сохранённым хешем."""
    return _hash_code(plaintext_code) == stored_hash


def _new_code() -> str:
    """6 цифр с ведущими нулями (000000–999999)."""
    return str(secrets.randbelow(1_000_000)).zfill(6)


# Стабильные между процессами ключи pg_advisory_xact_lock(key1, key2).
# key1 — пространство «OTP по email»: отрицательный и не равный domain-локу
# (app/email_domains/storage.py, -2_100_000_000) и appointment-локу
# (положительный psychologist_id). key2 — 32 бита SHA-256 email.
_OTP_EMAIL_LOCK_KEY1 = -2_100_000_100


def _email_lock_key(normalized_email: str) -> int:
    digest = hashlib.sha256(normalized_email.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big", signed=True)


def lock_email_otp(db, email: str) -> None:
    """
    Transaction-scoped advisory lock на нормализованный email: сериализует
    выпуск OTP (всех потоков) и подтверждение обычной регистрации по одному
    адресу, включая случай, когда строки OTP ещё нет. Снимается на
    commit/rollback. Коллизия 32-битного ключа лишь заставит подождать
    чужой email, на корректность не влияет.
    """
    db.execute(
        sa.text("SELECT pg_advisory_xact_lock(:k1, :k2)"),
        {"k1": _OTP_EMAIL_LOCK_KEY1, "k2": _email_lock_key(normalize_email(email))},
    )


@dataclass(frozen=True)
class RegistrationOtpIssue:
    """Данные ОДНОГО выпуска кода обычной регистрации — из той же транзакции,
    в которой он создан (письмо строится из них, а не из повторного поиска по
    email). code — plaintext для письма; в repr не попадает."""
    code: str = field(repr=False)
    registration_reference: str


# ─── Public API ───────────────────────────────────────────────────────────────

def create_or_update_otp(
    email: str, name: str, password_hash: Optional[str]
) -> str:
    """
    Создаёт (или перезаписывает) OTP-запись для email.

    password_hash — bcrypt-хеш пароля из register_init (регистрационный OTP)
    либо None (reset-OTP: копия текущего хеша не хранится; confirm её не
    использует, а у social-only аккаунта пароля нет вовсе).

    - Если запись уже существует и код был отправлен < RESEND_COOLDOWN сек назад,
      бросает ValueError с пользовательским сообщением.
    - Иначе генерирует новый 6-значный код, хранит его SHA-256 хеш,
      устанавливает TTL 10 минут.
    - Возвращает plaintext-код для отправки по email.
      В БД хранится ТОЛЬКО хеш — plaintext нигде не сохраняется.
    """
    with SessionLocal() as db:
        plaintext_code = create_or_update_otp_in_tx(db, email, name, password_hash)
        db.commit()

    log.info("[OTP] Code created/updated for %s", mask_email(email))
    return plaintext_code   # plaintext возвращается caller'у для отправки по email


def create_or_update_otp_in_tx(
    db, email: str, name: str, password_hash: Optional[str], *, lock: bool = False,
) -> str:
    """
    Та же операция в ПЕРЕДАННОЙ сессии, без commit — владелец транзакции
    коммитит сам (social registration init проверяет ticket под FOR UPDATE и
    создаёт OTP одним commit). lock=True берёт FOR UPDATE на существующей записи.

    Бросает ValueError при действующем cooldown (до любых изменений записи).
    Возвращает plaintext-код; в БД — только хеш.
    """
    email = normalize_email(email)
    plaintext_code = _new_code()
    code_hash      = _hash_code(plaintext_code)
    now            = _utcnow()

    # Тот же lock, что у выпуска кода обычной регистрации: параллельные выпуски
    # по одному email не создают вторую строку.
    lock_email_otp(db, email)
    query = db.query(OtpVerification).filter(OtpVerification.email == email)
    if lock:
        query = query.with_for_update()
    existing = query.first()

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
    return plaintext_code


def issue_registration_otp(
    email: str, name: str, password_hash: str,
) -> RegistrationOtpIssue:
    """
    Выпуск кода ОБЫЧНОЙ регистрации (email + пароль) одной транзакцией.

    Под lock_email_otp:
      1. email уже принадлежит строке users → RegistrationEmailTakenError
         (ничего не меняется);
      2. последняя отправка по этому email < RESEND_COOLDOWN сек назад →
         ValueError с текстом ожидания (ничего не меняется: прежний код,
         ссылка и срок действуют как были);
      3. все прежние записи OTP этого email удаляются (прежний код и
         registration reference больше не действуют) и создаётся новая — с
         новым id (UUIDv4), новым кодом, сроком OTP_TTL и attempts = 0;
      4. commit.

    Сбой до commit → rollback: прежний выпуск остаётся действующим. Письмо
    отправляет caller ПОСЛЕ commit; его сбой новый выпуск не отменяет.
    """
    email = normalize_email(email)
    plaintext_code = _new_code()
    now = _utcnow()

    with SessionLocal() as db:
        lock_email_otp(db, email)

        if db.query(User.id).filter(User.email == email).first() is not None:
            raise RegistrationEmailTakenError()

        previous = (
            db.query(OtpVerification)
            .filter(OtpVerification.email == email)
            .with_for_update()
            .all()
        )
        if previous:
            elapsed = (now - max(r.last_sent_at for r in previous)).total_seconds()
            if elapsed < RESEND_COOLDOWN:
                wait = int(RESEND_COOLDOWN - elapsed)
                raise ValueError(f"Повторная отправка доступна через {wait} с")
        for record in previous:
            db.delete(record)

        reference = str(uuid.uuid4())
        db.add(OtpVerification(
            id=reference,
            email=email,
            code=_hash_code(plaintext_code),
            name=name,
            password_hash=password_hash,
            attempts=0,
            expires_at=now + OTP_TTL,
            created_at=now,
            last_sent_at=now,
        ))
        db.commit()

    log.info("[OTP] Registration code issued for %s", mask_email(email))
    return RegistrationOtpIssue(code=plaintext_code, registration_reference=reference)


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
    email = normalize_email(email)
    now = _utcnow()

    with SessionLocal() as db:
        record = (
            db.query(OtpVerification)
            .filter(OtpVerification.email == email)
            .first()
        )

        if not record:
            raise OtpInvalidError("Код не найден или уже использован")

        if now > record.expires_at:
            db.delete(record)
            db.commit()
            raise OtpExpiredError("Срок действия кода истёк. Начните регистрацию заново")

        if record.attempts >= MAX_ATTEMPTS:
            db.delete(record)
            db.commit()
            raise OtpInvalidError("Превышено число попыток. Начните регистрацию заново")

        # Сравниваем хеш введённого кода с сохранённым хешем
        if not _verify_code(code, record.code):
            record.attempts += 1
            remaining = MAX_ATTEMPTS - record.attempts
            if remaining <= 0:
                db.delete(record)
                db.commit()
                raise OtpInvalidError(
                    "Неверный код. Попытки исчерпаны. Начните регистрацию заново"
                )
            db.commit()
            log.info(
                "[OTP] Wrong code for %s, attempts=%d, remaining=%d",
                mask_email(email), record.attempts, remaining,
            )
            raise OtpInvalidError(f"Неверный код. Осталось попыток: {remaining}")

        user_data = {"name": record.name, "password_hash": record.password_hash}
        db.delete(record)
        db.commit()

    log.info("[OTP] Verification OK for %s", mask_email(email))
    return user_data


def delete_otp(email: str) -> None:
    """Удаляет OTP-запись для email. No-op если записи нет."""
    email = normalize_email(email)
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
