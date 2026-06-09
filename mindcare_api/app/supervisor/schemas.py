"""
Pydantic-схемы модуля супервизора.
Используются эндпоинтами в supervisor/routes.py.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── Refs (вложенные объекты) ──────────────────────────────────────────────────

class PsychologistRef(BaseModel):
    id:           int
    uuid:         str
    full_name:    str
    email:        str
    is_accepting: Optional[bool] = None

    model_config = {"from_attributes": True}


class StudentRef(BaseModel):
    id:        int
    uuid:      str
    full_name: str
    email:     str

    model_config = {"from_attributes": True}


class EngagementRef(BaseModel):
    id:          int
    status:      str
    psychologist: Optional[PsychologistRef] = None


# ── Students list ─────────────────────────────────────────────────────────────

class StudentListItem(BaseModel):
    id:                 int
    uuid:               str
    full_name:          str
    email:              str
    current_engagement: Optional[EngagementRef] = None

    model_config = {"from_attributes": True}


class PaginatedStudentsResponse(BaseModel):
    items: list[StudentListItem]
    total: int
    page:  int
    size:  int


# ── Psychologists list ────────────────────────────────────────────────────────

class PsychologistListItem(BaseModel):
    id:           int
    uuid:         str
    full_name:    str
    email:        str
    is_accepting: Optional[bool] = None

    model_config = {"from_attributes": True}


class PaginatedPsychologistsResponse(BaseModel):
    items: list[PsychologistListItem]
    total: int
    page:  int
    size:  int


# ── Engagements list ──────────────────────────────────────────────────────────

class EngagementListItem(BaseModel):
    id:              int
    status:          str
    primary_concern: Optional[str]      = None
    started_at:      Optional[datetime] = None
    ended_at:        Optional[datetime] = None
    transfer_reason: Optional[str]      = None
    client:          StudentRef
    psychologist:    PsychologistRef

    model_config = {"from_attributes": True}


class PaginatedEngagementsResponse(BaseModel):
    items: list[EngagementListItem]
    total: int
    page:  int
    size:  int


# ── Engagement read (full) ────────────────────────────────────────────────────

class EngagementRead(BaseModel):
    id:              int
    status:          str
    primary_concern: Optional[str]      = None
    started_at:      Optional[datetime] = None
    ended_at:        Optional[datetime] = None
    transfer_reason: Optional[str]      = None
    client_id:       int
    psychologist_id: int

    model_config = {"from_attributes": True}


# ── Write schemas ─────────────────────────────────────────────────────────────

class EngagementCreate(BaseModel):
    client_id:       int   = Field(description="ID студента")
    psychologist_id: int   = Field(description="ID психолога")
    primary_concern: Optional[str] = Field(
        default=None, max_length=2000, description="Основная жалоба (необязательно)"
    )


class EngagementTransfer(BaseModel):
    new_psychologist_id: int = Field(description="ID нового психолога")
    transfer_reason:     Optional[str] = Field(
        default=None, max_length=2000, description="Причина переназначения"
    )


class EngagementClose(BaseModel):
    reason: Optional[str] = Field(
        default=None, max_length=2000, description="Причина закрытия (необязательно)"
    )
