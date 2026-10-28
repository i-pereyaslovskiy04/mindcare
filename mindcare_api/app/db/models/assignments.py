"""
Модель: задания психолога клиенту (ADR-033).

  Assignment — задание в рамках конкретного терапевтического сопровождения
               (TherapyEngagement): текст, необязательный срок, необязательный
               опубликованный материал библиотеки, статус и отметки переходов.

Автор и получатель НЕ хранятся отдельно: однозначно выводятся из
engagement.psychologist_id / engagement.client_id — пара в строке сопровождения
не меняется (передача создаёт или реактивирует ДРУГУЮ строку).

Lifecycle: active → completed (клиент) | active → cancelled (психолог).
completed и cancelled — конечные; возврата в active и редактирования нет
(для замены психолог отменяет задание и создаёт новое). Согласованность статуса и
отметок закреплена CHECK ck_assignments_status_timestamps.

article_id → articles ON DELETE RESTRICT: статьи удаляются только мягко
(deleted_at); RESTRICT не даёт физическому удалению молча стереть факт
прикрепления. Доступность материала (опубликован и не удалён) проверяется при
создании и вычисляется при каждом чтении — скрытое содержимое не раскрывается.

SECURITY: text_enc — ТОЛЬКО Fernet `enc:v1:` (app/core/encryption.py), что
закреплено CHECK. Не логировать, не копировать в audit/data_change_log.
"""
import uuid as _uuid

from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, ForeignKey, Index, Integer,
    String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text as sa_text

from app.db.base import Base

ASSIGNMENT_STATUSES = ("active", "completed", "cancelled")


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_assignments_status",
        ),
        CheckConstraint(
            "(status = 'active' AND completed_at IS NULL AND cancelled_at IS NULL)"
            " OR (status = 'completed' AND completed_at IS NOT NULL"
            " AND cancelled_at IS NULL)"
            " OR (status = 'cancelled' AND cancelled_at IS NOT NULL"
            " AND completed_at IS NULL)",
            name="ck_assignments_status_timestamps",
        ),
        CheckConstraint("text_enc LIKE 'enc:v1:%'", name="ck_assignments_text_enc_format"),
        # Списки сопровождения — keyset по (created_at, uuid) внутри engagement.
        Index("ix_assignments_engagement_created", "engagement_id", "created_at"),
        # Счётчик активных заданий клиента.
        Index(
            "ix_assignments_active_engagement",
            "engagement_id",
            postgresql_where=sa_text("status = 'active'"),
        ),
        # Проверка RESTRICT при удалении статьи и выборка по материалу.
        Index("ix_assignments_article_id", "article_id"),
    )

    id            = Column(Integer, primary_key=True)
    uuid          = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    engagement_id = Column(
        Integer, ForeignKey("therapy_engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    text_enc      = Column(Text, nullable=False)          # ТОЛЬКО enc:v1:
    due_date      = Column(Date)                          # необязательный срок
    article_id    = Column(
        Integer, ForeignKey("articles.id", ondelete="RESTRICT"), nullable=True
    )
    status        = Column(String(20), nullable=False, server_default="active")
    created_at    = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at    = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at  = Column(DateTime(timezone=True))
    cancelled_at  = Column(DateTime(timezone=True))
