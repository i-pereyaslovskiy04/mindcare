"""
Pydantic-схемы контактов (ADR-031).

Вход проверяется только по ФОРМЕ (типы, extra=forbid, жёсткие потолки длины);
содержательные правила (типы/сервисы/форматы/дубли) — в validators с кодами без
значений. `id` обязателен: это UUID, который клиент создаёт один раз; сервер ID
не генерирует. Ошибки формы санитизируются в sanitized_route (значения и имена
лишних полей наружу не попадают).
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.user_contacts.catalog import HARD_ITEMS_CAP

_ITEM_TEXT_CAP = 2000   # потолок разбора; рабочие лимиты проверяет validators


class ContactItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(max_length=64)
    type: str = Field(max_length=32)
    service: Optional[str] = Field(default=None, max_length=32)
    value: str = Field(max_length=_ITEM_TEXT_CAP)
    label: Optional[str] = Field(default=None, max_length=_ITEM_TEXT_CAP)


class ContactsSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=0, le=2_147_483_647)
    items: list[ContactItemIn] = Field(max_length=HARD_ITEMS_CAP)


class ContactItemOut(BaseModel):
    id: str
    type: str
    service: Optional[str] = None
    value: str
    label: Optional[str] = None


class LimitsOut(BaseModel):
    max_items: int
    label_max: int
    value_max: int


class ContactsOwnerOut(BaseModel):
    version: int
    updated_at: Optional[datetime] = None
    items: list[ContactItemOut]
    limits: LimitsOut
    catalog: dict


class ContactsSaveOut(ContactsOwnerOut):
    changed: bool


class ContactsStaffOut(BaseModel):
    primary_phone: Optional[str] = None
    updated_at: Optional[datetime] = None
    items: list[ContactItemOut]
    catalog: dict
