"""
Модели: уведомления пользователей.
  NotificationTemplate — шаблоны уведомлений (по коду события)
  Notification         — фактическое уведомление пользователю
  SystemMessageIntent  — сохранённое намерение доставки system-сообщения
                         (outbox, ADR-029)
"""

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index,
    Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text as sa_text

from app.db.base import Base


class NotificationTemplate(Base):
    __tablename__ = "notification_templates"

    id         = Column(Integer, primary_key=True)
    code       = Column(String(100), nullable=False, unique=True)
    title      = Column(String(255), nullable=False)
    body       = Column(Text, nullable=False)
    channel    = Column(String(50), default="web")    # web / email / sms
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    notifications = relationship("Notification", back_populates="template")


class Notification(Base):
    __tablename__ = "notifications"

    id          = Column(BigInteger, primary_key=True)
    user_id     = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    template_id = Column(
        Integer, ForeignKey("notification_templates.id", ondelete="SET NULL")
    )
    params      = Column(JSONB, default=dict)
    channel     = Column(String(50), default="web")
    is_read     = Column(Boolean, default=False)
    read_at     = Column(DateTime(timezone=True))
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    template = relationship("NotificationTemplate", back_populates="notifications")


class SystemMessageIntent(Base):
    """
    Намерение доставить system-сообщение (outbox, ADR-029).

    Строка пишется В ТОЙ ЖЕ транзакции, что и бизнес-операция (регистрация,
    решение по заявке подтверждения студента), а публикация через
    app.chat.system_publisher выполняется ПОСЛЕ commit. delivered_at
    выставляется только после успешного результата publisher; недоставленные
    строки добирает scripts/deliver_system_message_intents.py. Дубль сообщения
    при повторе исключает event_key (partial UNIQUE ux_chat_messages_event_key).

    Текст сообщения здесь НЕ хранится: только стабильный message_code
    (app/notifications/templates.py), поэтому outbox не содержит ни plaintext,
    ни ПДн. attempts/last_attempt_at — счётчик неудачных попыток публикации.
    """
    __tablename__ = "system_message_intents"
    __table_args__ = (
        UniqueConstraint(
            "recipient_id", "event_key", name="ux_system_message_intents_key",
        ),
        Index(
            "ix_system_message_intents_undelivered", "id",
            postgresql_where=sa_text("delivered_at IS NULL"),
        ),
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    recipient_id    = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    event_key       = Column(String(200), nullable=False)
    message_code    = Column(String(64), nullable=False)
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    attempts        = Column(Integer, nullable=False, server_default=sa_text("0"))
    last_attempt_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at    = Column(DateTime(timezone=True), nullable=True)
