"""
Модели: консультации и расписание.
  TherapyEngagement  — терапевтическое взаимодействие (связь клиент ↔ психолог)
  ScheduleRule       — правила расписания психолога (повторяющиеся слоты)
  ScheduleException  — исключения из расписания (отпуск, больничный, доп. часы)
  Appointment        — запись на конкретный сеанс (с проверкой пересечений)
  SessionNote        — заметки после сеанса (конфиденциальные)
"""

import uuid as _uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey,
    Index, Integer, String, Text, Time,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text as sa_text

from app.db.base import Base


class TherapyEngagement(Base):
    __tablename__ = "therapy_engagements"
    __table_args__ = (
        # Partial unique index: один клиент — не более одной активной связи.
        # Создаётся migration d2e5f8a1b4c7.
        Index(
            "ux_therapy_engagements_active_client",
            "client_id",
            unique=True,
            postgresql_where=sa_text("status = 'active' AND ended_at IS NULL"),
        ),
    )

    id              = Column(Integer, primary_key=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    client_id       = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status          = Column(String(20), default="active")   # active / completed / transferred / cancelled
    primary_concern = Column(Text)
    started_at      = Column(DateTime(timezone=True), server_default=func.now())
    ended_at        = Column(DateTime(timezone=True))
    transferred_to  = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    transfer_reason = Column(Text)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now())

    appointments  = relationship("Appointment", back_populates="engagement")
    session_notes = relationship("SessionNote", back_populates="engagement")


class ScheduleRule(Base):
    __tablename__ = "schedule_rules"

    id                    = Column(Integer, primary_key=True)
    psychologist_id       = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week           = Column(Integer, nullable=False)   # 0=Mon … 6=Sun
    start_time            = Column(Time, nullable=False)
    end_time              = Column(Time, nullable=False)
    slot_duration_minutes = Column(Integer, default=50)
    break_minutes         = Column(Integer, default=10)
    is_active             = Column(Boolean, default=True)
    effective_from        = Column(Date, nullable=False)
    effective_until       = Column(Date)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())


class ScheduleException(Base):
    __tablename__ = "schedule_exceptions"

    id              = Column(Integer, primary_key=True)
    psychologist_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    exception_date  = Column(Date, nullable=False)
    exception_type  = Column(String(20), nullable=False)   # day_off / extra_hours / shortened
    start_time      = Column(Time)
    end_time        = Column(Time)
    reason          = Column(Text)
    created_at      = Column(DateTime(timezone=True), server_default=func.now())


class Appointment(Base):
    __tablename__ = "appointments"

    id                  = Column(Integer, primary_key=True)
    uuid                = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    client_id           = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    psychologist_id     = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    engagement_id       = Column(
        Integer, ForeignKey("therapy_engagements.id", ondelete="SET NULL")
    )
    starts_at           = Column(DateTime(timezone=True), nullable=False)
    duration_minutes    = Column(Integer, nullable=False, default=50)
    ends_at             = Column(DateTime(timezone=True))   # вычисляется триггером в БД
    modality            = Column(String(20), default="in_person")   # in_person / online
    topic               = Column(Text)
    status              = Column(String(20), default="scheduled")    # scheduled / completed / cancelled / no_show
    cancellation_reason = Column(Text)
    canceled_by         = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at          = Column(DateTime(timezone=True))

    engagement    = relationship("TherapyEngagement", back_populates="appointments")
    session_notes = relationship("SessionNote", back_populates="appointment")


class SessionNote(Base):
    """
    Заметки после сеанса.

    SECURITY RISK: content хранится plaintext.
    Это нарушает требования ФЗ-152 к хранению специальных категорий ПДн
    (психологические данные = чувствительная категория).

    TODO (BACKLOG): реализовать encryption-at-rest для поля content.
    Предпочтительный подход: Fernet (cryptography.fernet) с ключом из env.
    Шифрование на уровне приложения, не PostgreSQL.
    Не менять схему БД — поле остаётся TEXT, шифрование в app-слое.
    """
    __tablename__ = "session_notes"

    id                    = Column(Integer, primary_key=True)
    uuid                  = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    appointment_id        = Column(
        Integer, ForeignKey("appointments.id", ondelete="SET NULL")
    )
    engagement_id         = Column(
        Integer, ForeignKey("therapy_engagements.id", ondelete="SET NULL")
    )
    author_id             = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    note_type             = Column(String(20), default="general")   # general / diagnosis / plan / followup
    content               = Column(Text, nullable=False)
    is_shared_with_client = Column(Boolean, default=False)
    version               = Column(Integer, default=1)
    created_at            = Column(DateTime(timezone=True), server_default=func.now())
    updated_at            = Column(DateTime(timezone=True), server_default=func.now())

    appointment = relationship("Appointment", back_populates="session_notes")
    engagement  = relationship("TherapyEngagement", back_populates="session_notes")
