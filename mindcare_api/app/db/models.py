import uuid as _uuid

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime,
    ForeignKey, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
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
    ip_address  = Column(String(50))
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
