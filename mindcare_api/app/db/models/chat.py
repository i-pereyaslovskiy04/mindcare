"""
Модели: Chat MVP (one-to-one чат student ↔ psychologist).

  ChatConversation — одна беседа = один therapy_engagement (UNIQUE).
  ChatMessage      — сообщения беседы.

SECURITY NOTE (по образцу SessionNote):
  ChatMessage.content физически TEXT, но application layer хранит в нём
  ТОЛЬКО Fernet ciphertext с префиксом "enc:v1:" (app/core/encryption.py,
  подключается в chat storage на Stage 28c).
  - Не записывать plaintext в content.
  - Не логировать content в audit/stdout/errors.
  - Plaintext fallback намеренно отсутствует.

Участники one-to-one беседы определяются через therapy_engagements:
client_id (студент) и psychologist_id — отдельной таблицы участников нет.
Group chat в MVP не реализуется; при его появлении добавится chat_members,
текущая схема этого не блокирует.

Закрытость чата = therapy_engagements.status != 'active' (запись запрещена,
чтение истории разрешено участникам). Отдельного closed_at нет.

read_at — простой MVP read receipt (достаточно для one-to-one).
deleted_at — soft delete; физическое удаление сообщений не используется.
"""

import uuid as _uuid

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey,
    Index, Integer, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text as sa_text

from app.db.base import Base


class ChatConversation(Base):
    __tablename__ = "chat_conversations"
    __table_args__ = (
        UniqueConstraint("engagement_id", name="ux_chat_conversations_engagement"),
        Index("ix_chat_conversations_last_message_at", "last_message_at"),
    )

    id              = Column(Integer, primary_key=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    engagement_id   = Column(
        Integer,
        ForeignKey("therapy_engagements.id", ondelete="RESTRICT"),
        nullable=False,
    )
    last_message_at = Column(DateTime(timezone=True))
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    engagement = relationship("TherapyEngagement")
    messages   = relationship(
        "ChatMessage", back_populates="conversation", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index(
            "ix_chat_messages_conv_created",
            "conversation_id", "created_at",
            postgresql_where=sa_text("deleted_at IS NULL"),
        ),
        Index("ix_chat_messages_sender", "sender_id"),
        Index(
            "ix_chat_messages_unread",
            "conversation_id",
            postgresql_where=sa_text("read_at IS NULL AND deleted_at IS NULL"),
        ),
    )

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    conversation_id = Column(
        Integer,
        ForeignKey("chat_conversations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sender_id       = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    content         = Column(Text, nullable=False)   # ТОЛЬКО enc:v1:<fernet>
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at         = Column(DateTime(timezone=True))
    deleted_at      = Column(DateTime(timezone=True))

    conversation = relationship("ChatConversation", back_populates="messages")
    sender       = relationship("User")
