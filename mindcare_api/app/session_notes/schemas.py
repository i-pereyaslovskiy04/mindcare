from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

NoteType = Literal["general", "diagnosis", "plan", "followup"]


class SessionNoteCreate(BaseModel):
    appointment_id:        Optional[int]  = None
    engagement_id:         Optional[int]  = None
    note_type:             Literal["general", "diagnosis", "plan", "followup"] = "general"
    content:               str            = Field(min_length=1, max_length=50000)
    is_shared_with_client: bool           = False


class SessionNoteUpdate(BaseModel):
    """
    Generic PATCH (ADR-035). version — необязательный CAS: без него сохранённый
    режим last-write-wins (блокировка строки сериализует записи, но от потери
    изменений не защищает). Явный null у content/note_type означает «не
    передано» (как раньше); у is_shared_with_client — 422 (раньше 500).
    """
    note_type:             Optional[NoteType] = None
    content:               Optional[str]  = Field(default=None, min_length=1, max_length=50000)
    is_shared_with_client: Optional[bool] = None
    version:               Optional[int]  = Field(default=None, ge=1)

    @field_validator("is_shared_with_client")
    @classmethod
    def _shared_not_null(cls, value):
        if value is None:
            raise ValueError("is_shared_with_client не может быть null")
        return value


class SessionNoteRead(BaseModel):
    """Полный ответ с расшифрованным content — только psychologist (свои)
    и supervisor (GET by id, под audit)."""
    id:                    int
    uuid:                  str
    appointment_id:        Optional[int]
    engagement_id:         Optional[int]
    author_id:             int
    note_type:             str
    content:               str
    is_shared_with_client: bool
    version:               int
    created_at:            datetime
    updated_at:            datetime

    model_config = {"from_attributes": True}


class SessionNoteMetaRead(BaseModel):
    """
    Metadata-only ответ — без терапевтического content и без decrypt.
    Используется для admin (list + get) и supervisor (list).
    """
    id:                    int
    uuid:                  str
    appointment_id:        Optional[int]
    engagement_id:         Optional[int]
    author_id:             int
    note_type:             str
    is_shared_with_client: bool
    version:               int
    created_at:            datetime
    updated_at:            datetime
    content_available:     bool = False

    model_config = {"from_attributes": True}


class PaginatedNotesResponse(BaseModel):
    items: list[SessionNoteRead]
    total: int
    page:  int
    size:  int


class PaginatedNotesMetaResponse(BaseModel):
    items: list[SessionNoteMetaRead]
    total: int
    page:  int
    size:  int


# ── client-scoped заметки карточки клиента (ADR-035) ──────────────────────────

class ClientNoteCreate(BaseModel):
    content:          str = Field(min_length=1, max_length=50000)
    note_type:        NoteType = "general"
    appointment_uuid: Optional[UUID] = None

    model_config = {"extra": "forbid"}


class ClientNoteUpdate(BaseModel):
    """version обязателен (CAS); null у content/note_type — 422."""
    content:   Optional[str] = Field(default=None, min_length=1, max_length=50000)
    note_type: Optional[NoteType] = None
    version:   int = Field(ge=1)

    model_config = {"extra": "forbid"}

    @field_validator("content", "note_type")
    @classmethod
    def _not_null(cls, value):
        if value is None:
            raise ValueError("null недопустим")
        return value


class ClientNoteAppointmentRef(BaseModel):
    uuid:      str
    starts_at: datetime


class ClientNoteRead(BaseModel):
    """Заметка о клиенте для её автора — без внутренних id и is_shared_with_client."""
    uuid:        str
    note_type:   str
    content:     str
    version:     int
    created_at:  datetime
    updated_at:  datetime
    appointment: Optional[ClientNoteAppointmentRef] = None


class ClientNoteUpdateRead(ClientNoteRead):
    changed: bool


class ClientNotesPage(BaseModel):
    items:       list[ClientNoteRead]
    has_more:    bool
    next_cursor: Optional[str] = None
