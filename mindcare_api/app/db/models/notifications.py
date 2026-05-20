"""
Модели: уведомления пользователей.
  NotificationTemplate — шаблоны уведомлений (по коду события)
  Notification         — фактическое уведомление пользователю
"""

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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
