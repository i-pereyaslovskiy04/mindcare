import uuid as _uuid

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime,
    ForeignKey, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


# ---------------------------------------------------------------------------
# Таблицы из SQL-схемы (db/sql/migrations/).
# SQLAlchemy описывает их здесь только для ORM-запросов — create_all их не трогает.
# ---------------------------------------------------------------------------

class Role(Base):
    __tablename__ = "roles"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(50), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    description  = Column(Text)
    is_system    = Column(Boolean, default=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user_roles = relationship("UserRole", back_populates="role")


class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    uuid          = Column(UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4)
    full_name     = Column(String(255), nullable=False)
    email         = Column(String(255), nullable=False, unique=True, index=True)
    phone         = Column(String(50))
    password_hash = Column(String(255), nullable=False)
    avatar_url    = Column(String(500))
    is_active     = Column(Boolean, default=True)
    last_login    = Column(DateTime(timezone=True))
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at    = Column(DateTime(timezone=True))

    user_roles = relationship(
        "UserRole",
        foreign_keys="UserRole.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id         = Column(Integer, primary_key=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id    = Column(Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    user = relationship("User", foreign_keys=[user_id], back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class UserSession(Base):
    """Сессии пользователей. Заменяет JWT refresh-токены.
    Таблица user_sessions создана через SQL-миграции, не через create_all."""
    __tablename__ = "user_sessions"

    id          = Column(String(255), primary_key=True)   # сам токен сессии
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    ip_address  = Column(INET)
    user_agent  = Column(Text)
    started_at  = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), server_default=func.now())
    expires_at  = Column(DateTime(timezone=True), nullable=False)
    is_revoked  = Column(Boolean, default=False)

    user = relationship("User", back_populates="sessions")


# ---------------------------------------------------------------------------
# Кастомные таблицы — создаются через SQLAlchemy create_all (не в SQL-схеме)
# ---------------------------------------------------------------------------

class OtpVerification(Base):
    """OTP-коды для подтверждения email при регистрации и сбросе пароля."""
    __tablename__ = "otp_verifications"

    id            = Column(String(36), primary_key=True, default=lambda: str(_uuid.uuid4()))
    email         = Column(String(255), nullable=False, index=True)
    code          = Column(String(6),   nullable=False)
    name          = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    attempts      = Column(Integer,     nullable=False, default=0)
    # Naive UTC — намеренно без timezone, совместимо с datetime.utcnow() в otp_service.py
    expires_at    = Column(DateTime, nullable=False)
    created_at    = Column(DateTime, nullable=False)
    last_sent_at  = Column(DateTime, nullable=False)




class Consent(Base):
    """Версионируемые политики (privacy_policy, data_processing, test_consent)."""
    __tablename__ = "consents"

    id           = Column(Integer, primary_key=True)
    policy_type  = Column(String(100), nullable=False)
    version      = Column(Integer, nullable=False, default=1)
    title        = Column(String(255), nullable=False)
    content      = Column(Text, nullable=False)
    is_mandatory = Column(Boolean, default=True)
    published_at = Column(DateTime(timezone=True))
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("policy_type", "version"),)


class ConsentRecord(Base):
    """Факт согласия пользователя на конкретную версию политики."""
    __tablename__ = "consent_records"

    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    consent_id  = Column(Integer, ForeignKey("consents.id", ondelete="RESTRICT"), nullable=False)
    accepted    = Column(Boolean, nullable=False)
    ip_address  = Column(INET)   
    user_agent  = Column(Text)
    accepted_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at  = Column(DateTime(timezone=True))

class AuthLog(Base):
    """
    Журнал аутентификационных событий: логины, выходы, сбросы пароля.
    Партиционирован по месяцам (управляется на уровне БД).
    Композитный PK (id, created_at) обязателен из-за партиционирования.
    """
    __tablename__ = "auth_log"

    id             = Column(Integer, primary_key=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    user_email     = Column(String(255))   # денормализация: email на момент события
    event          = Column(String(50), nullable=False)  # 'login'/'logout'/'failed_login'/'password_reset'/'register'
    success        = Column(Boolean, nullable=False, default=True)
    failure_reason = Column(String(255))
    ip_address     = Column(INET)
    user_agent     = Column(Text)
    session_id     = Column(String(255))
    mfa_method     = Column(String(20))
    created_at     = Column(DateTime(timezone=True), server_default=func.now(), primary_key=True)