"""
Модели: Дневник студента.

  DiaryEmotion — справочник эмоций (key, label, sort_order, is_active).
  DiaryEntry   — ежедневная запись студента с зашифрованными полями.

SECURITY NOTE:
  DiaryEntry.mood_score_enc, entry_text_enc, emotions_enc — физически TEXT,
  но application layer хранит ТОЛЬКО Fernet ciphertext с префиксом "enc:v1:"
  (app/core/encryption.py). Схема зеркалирует паттерн chat_messages.content.

  - Не записывать plaintext в эти поля.
  - Не логировать расшифрованное содержимое.
  - entry_text_enc nullable: NULL если студент не предоставил текст.
  - emotions_enc: зашифрованный JSON-массив ключей (пустой список → encrypt("[]")).

Доступ: только student (собственные записи).
  psychologist / supervisor / admin → 403 на уровне роутера.
  Дневник НЕ смешивается с session_notes и chat.
"""

import uuid as _uuid

from sqlalchemy import (
    BigInteger, Boolean, Column, Date, DateTime, ForeignKey,
    Index, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func, text as sa_text

from app.db.base import Base


class DiaryEmotion(Base):
    __tablename__ = "diary_emotions"

    id          = Column(BigInteger, primary_key=True, autoincrement=True)
    key         = Column(String(50),  unique=True, nullable=False)
    label       = Column(String(100), nullable=False)
    description = Column(Text,        nullable=True)
    sort_order  = Column(Integer,     nullable=False, default=0)
    is_active   = Column(Boolean,     nullable=False, default=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), server_default=func.now())


class DiaryEntry(Base):
    __tablename__ = "diary_entries"
    __table_args__ = (
        # Partial unique: одна активная запись на студента в день.
        # Создаётся migration b2e4d7f1a9c3.
        Index(
            "ux_diary_entries_student_date_active",
            "student_id",
            "entry_date",
            unique=True,
            postgresql_where=sa_text("deleted_at IS NULL"),
        ),
    )

    id             = Column(BigInteger, primary_key=True, autoincrement=True)
    uuid           = Column(
        UUID(as_uuid=False), unique=True, nullable=False,
        default=lambda: str(_uuid.uuid4()),
    )
    student_id     = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    entry_date     = Column(Date,    nullable=False)
    mood_score_enc = Column(Text,    nullable=False)
    entry_text_enc = Column(Text,    nullable=True)
    emotions_enc   = Column(Text,    nullable=False)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), server_default=func.now())
    deleted_at     = Column(DateTime(timezone=True), nullable=True)
