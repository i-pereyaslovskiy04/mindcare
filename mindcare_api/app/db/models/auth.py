"""
Модели: аутентификация, роли, пользователи, сессии.
"""

import uuid as _uuid

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.base import Base


# ─── Roles & Permissions ──────────────────────────────────────────────────────

class Role(Base):
    __tablename__ = "roles"

    id           = Column(Integer, primary_key=True)
    name         = Column(String(50), nullable=False, unique=True)
    display_name = Column(String(100), nullable=False)
    description  = Column(Text)
    is_system    = Column(Boolean, default=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    user_roles       = relationship("UserRole", back_populates="role")
    role_permissions = relationship(
        "RolePermission", back_populates="role", cascade="all, delete-orphan"
    )


class Permission(Base):
    __tablename__ = "permissions"

    id          = Column(Integer, primary_key=True)
    code        = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    module      = Column(String(50))

    role_permissions = relationship(
        "RolePermission", back_populates="permission", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id            = Column(Integer, primary_key=True)
    role_id       = Column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    permission_id = Column(
        Integer, ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False
    )

    role       = relationship("Role", back_populates="role_permissions")
    permission = relationship("Permission", back_populates="role_permissions")


# ─── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True)
    uuid          = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
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

    # ── relationships (строковые ссылки → нет циклических импортов) ──
    user_roles = relationship(
        "UserRole",
        foreign_keys="UserRole.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sessions = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    student_profile = relationship(
        "StudentProfile", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )
    psychologist_profile = relationship(
        "PsychologistProfile", back_populates="user", uselist=False,
        cascade="all, delete-orphan",
    )
    mfa_methods = relationship(
        "UserMfaMethod", back_populates="user", cascade="all, delete-orphan"
    )
    emergency_contacts = relationship(
        "EmergencyContact", back_populates="user", cascade="all, delete-orphan"
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id         = Column(Integer, primary_key=True)
    user_id    = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id    = Column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    granted_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    user = relationship("User", foreign_keys=[user_id], back_populates="user_roles")
    role = relationship("Role", back_populates="user_roles")


class UserSession(Base):
    """Сессии пользователей (заменяют JWT refresh-токены)."""
    __tablename__ = "user_sessions"

    id          = Column(String(255), primary_key=True)   # токен сессии
    user_id     = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    ip_address  = Column(INET)
    user_agent  = Column(Text)
    started_at  = Column(DateTime(timezone=True), server_default=func.now())
    last_active = Column(DateTime(timezone=True), server_default=func.now())
    expires_at  = Column(DateTime(timezone=True), nullable=False)
    is_revoked  = Column(Boolean, default=False)

    user = relationship("User", back_populates="sessions")


class RefreshToken(Base):
    """
    NOT IMPLEMENTED.

    Таблица создана в baseline migration, но refresh-token flow не реализован.
    Аутентификация использует UserSession (session_token), не RefreshToken.

    Зарезервировано для будущей реализации JWT refresh flow.
    До реализации: не использовать в бизнес-логике.
    """
    __tablename__ = "refresh_tokens"

    id         = Column(Integer, primary_key=True)
    user_id    = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token      = Column(String(512), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    revoked_at = Column(DateTime(timezone=True))
    ip_address = Column(INET)
    user_agent = Column(Text)

    user = relationship("User")


class UserMfaMethod(Base):
    """
    NOT IMPLEMENTED.

    Таблица создана в baseline migration, но MFA flow не реализован.
    Зарезервировано для будущей реализации TOTP/SMS/email MFA.
    До реализации: не использовать в бизнес-логике.
    """
    __tablename__ = "user_mfa_methods"

    id               = Column(Integer, primary_key=True)
    user_id          = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    method_type      = Column(String(20), nullable=False)  # totp / sms / email
    secret_encrypted = Column(Text)
    recovery_codes   = Column(Text)
    is_active        = Column(Boolean, default=True)
    verified_at      = Column(DateTime(timezone=True))
    created_at       = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="mfa_methods")
