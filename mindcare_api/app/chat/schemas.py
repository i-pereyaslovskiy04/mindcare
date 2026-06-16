"""
Pydantic-схемы Chat MVP (Stage 28c).

Message response содержит расшифрованный content — он попадает только
участникам беседы (student / psychologist по engagement). Encrypted
ciphertext наружу не отдаётся никогда.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


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


class ChatMessagesResponse(BaseModel):
    items: list[ChatMessageRead]


class ChatMessageCreate(BaseModel):
    """Body отправки сообщения. sender_id НЕ принимается — только из сессии."""
    content: str = Field(description="Текст сообщения, 1..10000 символов")

    @field_validator("content")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Сообщение не может быть пустым")
        if len(v) > 10000:
            raise ValueError("Сообщение слишком длинное (максимум 10000 символов)")
        return v


class ChatMessageEdit(BaseModel):
    """Body редактирования сообщения (Stage 31x). Те же правила, что и create:
    strip, 1..10000 символов. sender/идентификаторы — из URL/сессии, не из body."""
    content: str = Field(description="Новый текст сообщения, 1..10000 символов")

    @field_validator("content")
    @classmethod
    def _strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Сообщение не может быть пустым")
        if len(v) > 10000:
            raise ValueError("Сообщение слишком длинное (максимум 10000 символов)")
        return v


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
