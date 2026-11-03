"""
Pydantic-схемы заданий (ADR-033).

Вход проверяется только по ФОРМЕ (типы, extra=forbid, потолок разбора длины);
содержательные правила (trim/пусто/длина/символы) — в validators с кодами без
значений. Ошибки формы санитизируются в sanitized_route (текст задания наружу
не попадает).
"""
from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

_TEXT_PARSE_CAP = 20_000   # потолок разбора; рабочий лимит — validators.TEXT_MAX

AssignmentStatus = Literal["active", "completed", "cancelled"]


class AssignmentCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(max_length=_TEXT_PARSE_CAP)
    due_date: Optional[date] = None
    article_uuid: Optional[UUID] = None


class MaterialOut(BaseModel):
    uuid: UUID
    title: str


class AssignmentOut(BaseModel):
    uuid: UUID
    text: str
    status: AssignmentStatus
    due_date: Optional[date] = None
    is_overdue: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    engagement_active: bool
    material: Optional[MaterialOut] = None
    material_unavailable: bool


class MyAssignmentOut(AssignmentOut):
    can_complete: bool
    psychologist_name: str


class ClientAssignmentOut(AssignmentOut):
    can_cancel: bool


class MyAssignmentsPageOut(BaseModel):
    items: list[MyAssignmentOut]
    has_more: bool
    next_cursor: Optional[str] = None
    total: int


class ClientAssignmentsPageOut(BaseModel):
    items: list[ClientAssignmentOut]
    has_more: bool
    next_cursor: Optional[str] = None
    total: int


class MySummaryOut(BaseModel):
    open_count: int
    completed_count: int
    total_count: int


class AssignmentMutationOut(BaseModel):
    """Итог перехода/создания без текста: список перечитывается отдельно."""
    uuid: UUID
    status: AssignmentStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    changed: bool
