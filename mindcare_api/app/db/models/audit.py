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
    ARRAY, BigInteger, Boolean, CheckConstraint, Column, DateTime, ForeignKey,
    Index, Integer, String, Text, text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.sql import func

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_user",    "user_id",    "created_at"),
        Index("idx_audit_event",   "event_type", "created_at"),
        Index("idx_audit_entity",  "entity_type", "entity_id"),
        Index("idx_audit_outcome", "outcome",    "created_at"),
        # Stage 8: хронологическая лента admin viewer.
        # Порядок столбцов повторяет ORDER BY эндпоинтов, поэтому индекс
        # даёт и отсечение по периоду, и готовую сортировку с tie-break по id.
        Index("idx_audit_created", "created_at", "id"),
        CheckConstraint(
            "outcome IN ('success', 'failure')", name="ck_audit_outcome",
        ),
    )

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
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
    # Stage 2: исход действия. Старые writer'ы не передают outcome — client/server
    # default 'success' сохраняет совместимость. failure_reason_code — стабильный
    # enum-код (без PII/exception text), заполняется на следующих этапах.
    outcome             = Column(String(10), nullable=False, default="success", server_default=text("'success'"))
    failure_reason_code = Column(String(100))
    created_at     = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())


class AuthLog(Base):
    """
    Журнал аутентификационных событий.
    Заполняется через единый audit-facade (app/audit/service.py) для событий
    с destination=AUTH_LOG. Legacy-хелпер app/auth/audit.py::log_auth_event
    удалён (Stage 4B-5); сама таблица/модель остаётся.
    """
    __tablename__ = "auth_log"
    __table_args__ = (
        Index("idx_auth_user",     "user_id",    "created_at"),
        Index("idx_auth_ip",       "ip_address", "created_at"),
        Index("idx_auth_failures", "ip_address", "created_at"),
        Index("idx_auth_created",  "created_at", "id"),   # Stage 8
    )

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
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
    """Минимизированный журнал изменений — техническая мера прослеживаемости
    (who changed what). Не является утверждением о прямом требовании
    какого-либо закона или о соответствии законодательству — это отдельное
    решение DPO/ответственного лица, вне охвата этой модели.

    Stage 6-A: структурные инварианты минимизированного журнала закреплены на
    уровне БД (migration d4a7b2c9f6e1). Имена ограничений и текст CHECK здесь
    ОБЯЗАНЫ совпадать с миграцией — расхождение ловится drift-тестом.

    old_values/new_values остаются nullable JSONB намеренно: они заполняются
    ТОЛЬКО для явно размеченных нечувствительных enum/bool/int полей
    (app/audit/change_registry.py). CHECK на их содержимое не вводится — БД не
    может отличить безопасное значение от ПДн; это делает application allowlist.
    """
    __tablename__ = "data_change_log"
    __table_args__ = (
        Index("idx_dcl_actor",     "actor_id",   "created_at"),
        Index("idx_dcl_table",     "table_name", "record_id"),
        Index("idx_dcl_operation", "operation",  "created_at"),
        Index("idx_dcl_created",   "created_at", "id"),   # Stage 8
        CheckConstraint(
            "operation IN ('INSERT', 'UPDATE', 'DELETE')",
            name="ck_dcl_operation",
        ),
        CheckConstraint(
            "cardinality(changed_fields) > 0",
            name="ck_dcl_changed_fields_nonempty",
        ),
        # NOT NULL этот CHECK не заменяет: CHECK с NULL даёт NULL и проходит.
        CheckConstraint(
            "record_id > 0",
            name="ck_dcl_record_id_positive",
        ),
    )

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_id       = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    actor_role     = Column(String(50))
    table_name     = Column(String(100), nullable=False)
    record_id      = Column(Integer, nullable=False)
    operation      = Column(String(10), nullable=False)    # INSERT / UPDATE / DELETE
    old_values     = Column(JSONB)
    new_values     = Column(JSONB)
    changed_fields = Column(ARRAY(Text()), nullable=False)  # TEXT[] — совместимо с PostgreSQL reflection
    ip_address     = Column(INET)
    created_at     = Column(DateTime(timezone=True), primary_key=True, server_default=func.now())
