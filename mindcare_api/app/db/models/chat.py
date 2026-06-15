"""
Модели: Chat (one-to-one чат student ↔ psychologist + system conversation).

  ChatConversation — type='engagement': одна беседа = один therapy_engagement
                     (UNIQUE engagement_id); type='system' (Stage 29b): read-only
                     системные уведомления, одна на пользователя (recipient_id,
                     partial UNIQUE), engagement_id IS NULL. CHECK гарантирует
                     взаимоисключающие наборы полей.
  ChatMessage      — message_kind='user' (sender_id NOT NULL) либо 'system'
                     (sender_id IS NULL, Stage 29b); event_key — идемпотентность
                     доставки system-сообщений (partial UNIQUE с conversation_id).

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
    BigInteger, CheckConstraint, Column, DateTime, ForeignKey,
    Index, Integer, String, Text, UniqueConstraint,
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
        # Одна system-беседа на пользователя (engagement_id NULL у system).
        Index(
            "ux_chat_conversations_system_recipient", "recipient_id",
            unique=True, postgresql_where=sa_text("type = 'system'"),
        ),
        CheckConstraint(
            "(type = 'engagement' AND engagement_id IS NOT NULL AND recipient_id IS NULL)"
            " OR "
            "(type = 'system' AND engagement_id IS NULL AND recipient_id IS NOT NULL)",
            name="ck_chat_conversations_type",
        ),
    )

    id              = Column(Integer, primary_key=True)
    uuid            = Column(
        UUID(as_uuid=True), unique=True, nullable=False, default=_uuid.uuid4
    )
    # 'engagement' — 1:1 student↔psychologist; 'system' — read-only системные уведомления.
    type            = Column(
        String(20), nullable=False, server_default="engagement"
    )
    engagement_id   = Column(
        Integer,
        ForeignKey("therapy_engagements.id", ondelete="RESTRICT"),
        nullable=True,   # NULL для system-беседы
    )
    recipient_id    = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,   # получатель system-беседы; NULL для engagement
    )
    last_message_at = Column(DateTime(timezone=True))
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    engagement = relationship("TherapyEngagement")
    recipient  = relationship("User")
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
        # Идемпотентность publish: один event_key на беседу.
        Index(
            "ux_chat_messages_event_key", "conversation_id", "event_key",
            unique=True, postgresql_where=sa_text("event_key IS NOT NULL"),
        ),
        CheckConstraint(
            "(message_kind = 'user' AND sender_id IS NOT NULL)"
            " OR "
            "(message_kind = 'system' AND sender_id IS NULL)",
            name="ck_chat_messages_kind_sender",
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
    # 'user' — отправлено участником (sender_id NOT NULL);
    # 'system' — системное уведомление (sender_id NULL).
    message_kind    = Column(
        String(20), nullable=False, server_default="user"
    )
    sender_id       = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    # Идемпотентность доставки system-сообщения (UNIQUE с conversation_id).
    event_key       = Column(String, nullable=True)
    content         = Column(Text, nullable=False)   # ТОЛЬКО enc:v1:<fernet>
    created_at      = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    read_at         = Column(DateTime(timezone=True))
    # NULL — сообщение не редактировалось; иначе момент последней правки (Stage 31x).
    edited_at       = Column(DateTime(timezone=True))
    deleted_at      = Column(DateTime(timezone=True))

    conversation = relationship("ChatConversation", back_populates="messages")
    sender       = relationship("User")
