"""
Модель: заявки на подтверждение статуса студента ДонГУ (ADR-029).

  StudentVerificationRequest — одна заявка пользователя: факультет из каталога
                               (app/student_verification/faculties.py — единый
                               источник кодов), номер студенческого билета и
                               единственное решение supervisor'а.

Статус «Студент ДонГУ подтверждён» — НЕ роль: membership `student`, его права и
доступ к тестам/консультациям не меняются. `student_profiles.faculty` к
подтверждению отношения не имеет.

Жизненный цикл строки: pending → approved | rejected, решение одно и после него
строка не изменяется. История — сами строки: повторная подача после отказа
создаёт НОВУЮ заявку. Одобрение финально (новая подача после него отклоняется).

  * ux_svr_user_pending  — не больше одной pending-заявки на пользователя;
  * ux_svr_user_approved — не больше одной одобренной (defense-in-depth поверх
                           сериализации операций по строке users).

Каталог факультетов в БД НЕ дублируется CHECK-ом: единый источник — код, а
исторические коды остаются читаемыми.

SECURITY: ticket_number_enc и rejection_reason_enc — ТОЛЬКО Fernet `enc:v1:`
(app/core/encryption.py), что закреплено CHECK. Не логировать, не копировать в
audit/data_change_log, в списке supervisor не расшифровывать.
"""

import uuid as _uuid

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text as sa_text

from app.db.base import Base

VERIFICATION_STATUSES = ("pending", "approved", "rejected")


class StudentVerificationRequest(Base):
    __tablename__ = "student_verification_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_svr_status",
        ),
        CheckConstraint(
            "ticket_number_enc LIKE 'enc:v1:%'", name="ck_svr_ticket_encrypted",
        ),
        CheckConstraint(
            "rejection_reason_enc IS NULL OR rejection_reason_enc LIKE 'enc:v1:%'",
            name="ck_svr_reason_encrypted",
        ),
        # reviewed_by не требуется для решённой строки: FK ON DELETE SET NULL.
        CheckConstraint(
            "(status = 'pending' AND reviewed_at IS NULL AND reviewed_by IS NULL "
            "AND rejection_reason_enc IS NULL) "
            "OR (status = 'approved' AND reviewed_at IS NOT NULL "
            "AND rejection_reason_enc IS NULL) "
            "OR (status = 'rejected' AND reviewed_at IS NOT NULL "
            "AND rejection_reason_enc IS NOT NULL)",
            name="ck_svr_decision_consistent",
        ),
        Index(
            "ux_svr_user_pending", "user_id",
            unique=True, postgresql_where=sa_text("status = 'pending'"),
        ),
        Index(
            "ux_svr_user_approved", "user_id",
            unique=True, postgresql_where=sa_text("status = 'approved'"),
        ),
        Index("ix_svr_status_submitted", "status", "submitted_at"),
        Index("ix_svr_user_id", "user_id"),
    )

    id                   = Column(Integer, primary_key=True)
    uuid                 = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    user_id              = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    faculty_code         = Column(String(64), nullable=False)
    ticket_number_enc    = Column(Text, nullable=False)       # ТОЛЬКО enc:v1:
    status               = Column(String(20), nullable=False)
    submitted_at         = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    reviewed_by          = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at          = Column(DateTime(timezone=True), nullable=True)
    rejection_reason_enc = Column(Text, nullable=True)        # ТОЛЬКО enc:v1:
