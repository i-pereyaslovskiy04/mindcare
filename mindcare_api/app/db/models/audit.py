"""
Модели: таблицы аудита.

Схема управляется через Alembic migration 3a7c5e2b8f1d.
Таблицы партиционированы по RANGE (created_at), месячные партиции.

Партиции управляются через maintenance-скрипт:
  cd mindcare_api/
  python scripts/ensure_audit_partitions.py --months-ahead 24

PRIMARY KEY составной (id, created_at) — требование PostgreSQL для
partitioned tables: partition key должен входить в PRIMARY KEY.

Примечание по отношениям:
  AuditLog/AuthLog/DataChangeLog не имеют ORM-relationship к User —
  только FK на уровне SQL. Это намеренно: при партиционировании
  SQLAlchemy relationship через партицию работает некорректно.
"""

from sqlalchemy import (
    ARRAY, BigInteger, Boolean, Column, DateTime, ForeignKey,
    Index, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_user",   "user_id",    "created_at"),
        Index("idx_audit_event",  "event_type", "created_at"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
    )

    id             = Column(BigInteger, primary_key=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    user_role      = Column(String(50))
    event_type     = Column(String(100), nullable=False)
    entity_type    = Column(String(100))
    entity_id      = Column(Integer)
    description    = Column(Text)
    log_metadata   = Column("metadata", JSONB, default=dict)
    ip_address     = Column(INET)
    user_agent     = Column(Text)
    session_id     = Column(String(255))
    request_url    = Column(String(500))
    request_method = Column(String(10))
    created_at     = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())


class AuthLog(Base):
    """
    Журнал аутентификационных событий.
    Используется в app/auth/audit.py → log_auth_event().
    """
    __tablename__ = "auth_log"
    __table_args__ = (
        Index("idx_auth_user",     "user_id",    "created_at"),
        Index("idx_auth_ip",       "ip_address", "created_at"),
        Index("idx_auth_failures", "ip_address", "created_at"),
    )

    id             = Column(BigInteger, primary_key=True)
    user_id        = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    user_email     = Column(String(255))   # денормализация: email на момент события
    event          = Column(String(150), nullable=False)
    success        = Column(Boolean, nullable=False, default=True)
    failure_reason = Column(String(255))
    ip_address     = Column(INET)
    user_agent     = Column(Text)
    session_id     = Column(String(255))
    mfa_method     = Column(String(20))
    created_at     = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())


class DataChangeLog(Base):
    """Лог изменений данных (who changed what, ФЗ-152)."""
    __tablename__ = "data_change_log"
    __table_args__ = (
        Index("idx_dcl_actor",     "actor_id",   "created_at"),
        Index("idx_dcl_table",     "table_name", "record_id"),
        Index("idx_dcl_operation", "operation",  "created_at"),
    )

    id             = Column(BigInteger, primary_key=True)
    actor_id       = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    actor_role     = Column(String(50))
    table_name     = Column(String(100), nullable=False)
    record_id      = Column(Integer)
    operation      = Column(String(10), nullable=False)    # INSERT / UPDATE / DELETE
    old_values     = Column(JSONB)
    new_values     = Column(JSONB)
    changed_fields = Column(ARRAY(Text()))   # TEXT[] — совместимо с PostgreSQL reflection
    ip_address     = Column(INET)
    created_at     = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
