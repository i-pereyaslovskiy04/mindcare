"""
Модель: allowlist разрешённых почтовых доменов для создания новых аккаунтов.

AllowedEmailDomain — организационный список доменов, с которых разрешено
регистрировать/создавать новые учётные записи (self-registration, admin-created
staff, supervisor-created student). Отсутствие домена в активном allowlist
означает запрет создания аккаунта на этом домене (отдельного denylist нет).

Политика применяется ТОЛЬКО при создании новых аккаунтов. Она не влияет на
login и password reset существующих пользователей (в т.ч. с иностранными
адресами) — старые аккаунты продолжают работать.

`domain` хранится в нормализованном виде (lower/trim, без trailing dot);
уникальность нормализованного домена гарантируется на уровне БД
(ux_allowed_email_domains_domain). Отключение — через is_active=False
(физического DELETE нет). Изменения действуют сразу (живой DB-query).
"""

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint, Index,
)
from sqlalchemy.sql import func

from app.db.base import Base


class AllowedEmailDomain(Base):
    __tablename__ = "allowed_email_domains"
    __table_args__ = (
        UniqueConstraint("domain", name="ux_allowed_email_domains_domain"),
        Index("ix_allowed_email_domains_is_active", "is_active"),
    )

    id                 = Column(BigInteger, primary_key=True, autoincrement=True)
    domain             = Column(String(255), nullable=False)   # нормализованный
    is_active          = Column(Boolean, nullable=False, server_default=func.true())
    comment            = Column(Text)
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"),
    )
    created_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
