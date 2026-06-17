"""
Pydantic-схемы Chat MVP (Stage 28c).

Message response содержит расшифрованный content — он попадает только
участникам беседы (student / psychologist по engagement). Encrypted
ciphertext наружу не отдаётся никогда.
"""

import uuid as _uuid_module
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ChatUserRead(BaseModel):
    """Краткая карточка собеседника."""
    id:        int
    full_name: str


class ChatConversationRead(BaseModel):
    """Детали беседы для участника."""
    uuid:              str
    partner:           ChatUserRead       # собеседник (психолог для студента и наоборот)
    engagement_status: str                # active / completed / transferred / cancelled
    last_message_at:   Optional[datetime]
    unread_count:      int
    peer_is_online:    bool = False       # приблизительный presence по last_active (Stage 30c)


class MyConversationResponse(BaseModel):
    """GET /chat/my-conversation: null — психолог ещё не назначен."""
    conversation: Optional[ChatConversationRead]


class ChatConversationListItem(BaseModel):
    """Элемент списка бесед психолога."""
    uuid:              str
    student:           ChatUserRead
    engagement_status: str
    last_message_at:   Optional[datetime]
    unread_count:      int
    peer_is_online:    bool = False       # приблизительный presence по last_active (Stage 30c)


class PaginatedChatConversationsResponse(BaseModel):
    items: list[ChatConversationListItem]
    total: int
    page:  int
    size:  int


class StudentChatConversationListItem(BaseModel):
    """Элемент списка бесед студента (partner = психолог)."""
    uuid:              str
    partner:           ChatUserRead
    engagement_status: str
    last_message_at:   Optional[datetime]
    unread_count:      int
    peer_is_online:    bool = False


class PaginatedStudentConversationsResponse(BaseModel):
    items: list[StudentChatConversationListItem]
    total: int
    page:  int
    size:  int


# ─── Attachments (Stage 32c) ────────────────────────────────────────────────

class ChatAttachmentRead(BaseModel):
    """Метаданные вложения в ответе API.

    storage_key и физический путь наружу не отдаются.
    checksum_sha256 не нужен frontend и тоже скрыт.
    """
    uuid:              str
    original_filename: str
    mime_type:         str
    file_size:         int
    is_image:          bool
    created_at:        datetime


# ─── Messages ───────────────────────────────────────────────────────────────

class ChatMessageRead(BaseModel):
    id:          int                      # курсор для before/after пагинации
    uuid:        str
    sender_id:   Optional[int]            # None для system-сообщения
    sender_role: str                      # student / psychologist / system
    is_mine:     bool
    content:     str                      # plaintext (decrypt после проверки прав); "" для удалённого
    created_at:  datetime
    read_at:     Optional[datetime]
    edited_at:   Optional[datetime] = None  # NULL — не редактировалось (Stage 31x)
    is_deleted:  bool = False                # True — soft-deleted, content не отдаётся (Stage 31y)
    attachments: list[ChatAttachmentRead] = Field(default_factory=list)  # Stage 32c


class ChatMessagesResponse(BaseModel):
    items: list[ChatMessageRead]


class ChatMessageCreate(BaseModel):
    """
    Body отправки сообщения. sender_id НЕ принимается — только из сессии.

    Stage 32c: content может быть пустым, если переданы attachment_uuids.
    Нельзя отправить одновременно пустой content и пустой список вложений.
    """
    content:          str            = Field(default="", description="Текст сообщения (0..10000 символов)")
    attachment_uuids: list[_uuid_module.UUID] = Field(
        default_factory=list,
        description="UUID вложений, загруженных через upload endpoint (Stage 32c)",
    )

    @model_validator(mode="after")
    def _check_not_empty(self) -> "ChatMessageCreate":
        text = (self.content or "").strip()
        if not text and not self.attachment_uuids:
            raise ValueError("Сообщение не может быть пустым (нужен текст или вложение)")
        if len(text) > 10000:
            raise ValueError("Сообщение слишком длинное (максимум 10000 символов)")
        self.content = text
        return self


class ChatMessageEdit(BaseModel):
    """Body редактирования сообщения (Stage 31x/32g).

    Stage 32g: добавлено remove_attachment_uuids — UUID вложений для soft-delete
    при редактировании. content может быть пустым, если после удаления остаётся
    хотя бы одно вложение; итоговая «не пустое» проверка делается в storage
    после вычисления остатка. sender/идентификаторы — из URL/сессии, не из body.
    """
    content: str = Field(default="", description="Новый текст сообщения (0..10000 символов)")
    remove_attachment_uuids: list[_uuid_module.UUID] = Field(
        default_factory=list,
        description="UUID вложений для soft-delete при редактировании (Stage 32g)",
    )

    @model_validator(mode="after")
    def _strip_and_check(self) -> "ChatMessageEdit":
        self.content = (self.content or "").strip()
        if len(self.content) > 10000:
            raise ValueError("Сообщение слишком длинное (максимум 10000 символов)")
        return self


class ChatReadResponse(BaseModel):
    """POST .../read: сколько входящих сообщений помечено прочитанными."""
    updated_count: int


# ─── System conversation (Stage 29b) ────────────────────────────────────────

class SystemConversationRead(BaseModel):
    """Детали read-only system-беседы получателя."""
    uuid:            str
    type:            str = "system"
    last_message_at: Optional[datetime]
    unread_count:    int


class MySystemConversationResponse(BaseModel):
    """GET /chat/system-conversation: null — беседы ещё нет (сообщений не было)."""
    conversation: Optional[SystemConversationRead]
