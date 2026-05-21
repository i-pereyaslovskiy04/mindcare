"""
Модель: OTP-коды для подтверждения email.

Схема управляется через Alembic (baseline migration + c5d8a1b4e7f2).
"""

import uuid as _uuid

from sqlalchemy import Column, DateTime, Integer, String

from app.db.base import Base


class OtpVerification(Base):
    """
    OTP-коды для регистрации и сброса пароля.

    Поля:
      email         — к какому email привязан код
      code          — SHA-256 хеш 6-значного кода (VARCHAR(64), не plaintext)
                      Plaintext никогда не сохраняется в БД.
                      Сравнение через otp_service._verify_code().
      name          — имя пользователя из формы регистрации
      password_hash — bcrypt хеш пароля, сохраняется до confirm
      attempts      — счётчик неверных попыток (лимит: 5)
      expires_at    — UTC naive datetime (совместимо с datetime.utcnow())
      last_sent_at  — для cooldown между повторными отправками (60 сек)
    """
    __tablename__ = "otp_verifications"

    id            = Column(
        String(36), primary_key=True, default=lambda: str(_uuid.uuid4())
    )
    email         = Column(String(255), nullable=False, index=True)
    code          = Column(String(64),  nullable=False)  # SHA-256 hex (64 chars)
    name          = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    attempts      = Column(Integer,     nullable=False, default=0)
    expires_at    = Column(DateTime, nullable=False)   # naive UTC
    created_at    = Column(DateTime, nullable=False)
    last_sent_at  = Column(DateTime, nullable=False)
