"""
Модели: фундамент social auth (Яндекс ID / VK ID) — Stage Social Auth 2A.

  UserOAuthIdentity  — привязка внешней identity провайдера к пользователю
  OAuthAuthRequest   — незавершённый OAuth-запрос (state/PKCE), одноразовый
  OAuthPendingTicket — одноразовый ticket между backend callback и frontend

Схема — migration c6e1a4f8b2d7. На этом этапе production-код записи НЕ создаёт:
OAuth flow (authorize/callback/complete) реализуется отдельной стадией.

SECURITY: здесь НЕ хранятся provider access/refresh/id token, authorization
code, raw state, raw ticket, plaintext PKCE verifier, client secret и сырой
профиль провайдера. state и ticket — только SHA-256 hex; verifier — только
Fernet ciphertext `enc:v1:` (app/core/encryption.encrypt_text), что
закреплено CHECK-ограничением.
"""

import uuid as _uuid

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.base import Base

# Допустимые провайдеры. Расширение набора — только миграцией (CHECK в БД).
OAUTH_PROVIDERS = ("yandex", "vk")
OAUTH_REQUEST_INTENTS = ("login", "link")
OAUTH_TICKET_KINDS = ("login", "registration", "link_required")

_PROVIDER_CHECK = "provider IN ('yandex', 'vk')"
_SHA256_HEX = "'^[0-9a-f]{64}$'"


class UserOAuthIdentity(Base):
    """
    Внешняя identity провайдера, связанная с пользователем MindCare.

    provider_subject — стабильный id пользователя у провайдера: Яндекс `id`
    (НЕ `psuid`, он свой у каждого приложения), VK `user_id` строкой.
    Email провайдера здесь не хранится (минимизация ПДн: email — в users).
    """
    __tablename__ = "user_oauth_identities"
    __table_args__ = (
        CheckConstraint(_PROVIDER_CHECK, name="ck_user_oauth_identities_provider"),
        CheckConstraint(
            "char_length(provider_subject) > 0",
            name="ck_user_oauth_identities_subject_nonempty",
        ),
        # Одна внешняя identity — один аккаунт MindCare.
        UniqueConstraint(
            "provider", "provider_subject",
            name="ux_user_oauth_identities_provider_subject",
        ),
        # Не больше одной identity каждого провайдера на аккаунт.
        UniqueConstraint(
            "user_id", "provider", name="ux_user_oauth_identities_user_provider",
        ),
        Index("ix_user_oauth_identities_user_id", "user_id"),
    )

    id               = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid             = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    user_id          = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider         = Column(String(20), nullable=False)
    provider_subject = Column(String(255), nullable=False)
    created_at       = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login_at    = Column(DateTime(timezone=True), nullable=True)


class OAuthAuthRequest(Base):
    """
    Незавершённый OAuth authorization request (state + PKCE).

    state_hash — SHA-256 hex от raw state (raw state не хранится).
    code_verifier_enc — PKCE verifier, только в виде `enc:v1:` ciphertext.
    intent=login — анонимный старт (user_id IS NULL); intent=link — старт из
    authenticated settings (user_id обязателен). Одноразовость: consumed_at
    выставляется атомарным UPDATE ... WHERE consumed_at IS NULL.
    """
    __tablename__ = "oauth_auth_requests"
    __table_args__ = (
        CheckConstraint(_PROVIDER_CHECK, name="ck_oauth_auth_requests_provider"),
        CheckConstraint(
            "intent IN ('login', 'link')", name="ck_oauth_auth_requests_intent",
        ),
        CheckConstraint(
            f"state_hash ~ {_SHA256_HEX}",
            name="ck_oauth_auth_requests_state_hash_format",
        ),
        CheckConstraint(
            "code_verifier_enc LIKE 'enc:v1:%'",
            name="ck_oauth_auth_requests_verifier_encrypted",
        ),
        CheckConstraint(
            "(intent = 'link' AND user_id IS NOT NULL) "
            "OR (intent = 'login' AND user_id IS NULL)",
            name="ck_oauth_auth_requests_intent_user",
        ),
        CheckConstraint(
            "expires_at > created_at", name="ck_oauth_auth_requests_expiry",
        ),
        Index("ix_oauth_auth_requests_expires_at", "expires_at"),
    )

    state_hash        = Column(String(64), primary_key=True)
    provider          = Column(String(20), nullable=False)
    intent            = Column(String(20), nullable=False)
    code_verifier_enc = Column(Text, nullable=False)
    user_id           = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at        = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at        = Column(DateTime(timezone=True), nullable=False)
    consumed_at       = Column(DateTime(timezone=True), nullable=True)


class OAuthPendingTicket(Base):
    """
    Одноразовый ticket от backend callback к frontend (/auth/callback).

    ticket_hash — SHA-256 hex от raw ticket. Session token через ticket/URL
    не передаётся: сессия создаётся только при complete.
      kind=login         — identity уже привязана, user_id обязателен;
      kind=registration  — новая identity, аккаунта ещё нет (user_id NULL).
                           email / suggested_name — email и имя из профиля
                           провайдера, записанные callback'ом при создании
                           ticket (Stage Social Auth 4); после этого не
                           меняются, клиент их не передаёт. Email считается
                           подтверждённым только после OTP MindCare на confirm;
      kind=link_required — email принадлежит существующему аккаунту
                           (in-flow linking не реализуется; ticket нужен для
                           безопасного ответа «войдите и привяжите в настройках»).
    """
    __tablename__ = "oauth_pending_tickets"
    __table_args__ = (
        CheckConstraint(_PROVIDER_CHECK, name="ck_oauth_pending_tickets_provider"),
        CheckConstraint(
            "kind IN ('login', 'registration', 'link_required')",
            name="ck_oauth_pending_tickets_kind",
        ),
        CheckConstraint(
            f"ticket_hash ~ {_SHA256_HEX}",
            name="ck_oauth_pending_tickets_ticket_hash_format",
        ),
        CheckConstraint(
            "char_length(provider_subject) > 0",
            name="ck_oauth_pending_tickets_subject_nonempty",
        ),
        CheckConstraint(
            "kind <> 'login' OR user_id IS NOT NULL",
            name="ck_oauth_pending_tickets_login_user",
        ),
        CheckConstraint(
            "kind <> 'registration' OR user_id IS NULL",
            name="ck_oauth_pending_tickets_registration_no_user",
        ),
        # Тот же инвариант, что ck_users_email_normalized.
        CheckConstraint(
            "email IS NULL OR email = lower(trim(email))",
            name="ck_oauth_pending_tickets_email_normalized",
        ),
        CheckConstraint(
            "expires_at > created_at", name="ck_oauth_pending_tickets_expiry",
        ),
        Index("ix_oauth_pending_tickets_expires_at", "expires_at"),
    )

    ticket_hash      = Column(String(64), primary_key=True)
    kind             = Column(String(20), nullable=False)
    provider         = Column(String(20), nullable=False)
    provider_subject = Column(String(255), nullable=False)
    email            = Column(String(255), nullable=True)
    suggested_name   = Column(String(255), nullable=True)
    user_id          = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_at       = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at       = Column(DateTime(timezone=True), nullable=False)
    consumed_at      = Column(DateTime(timezone=True), nullable=True)
