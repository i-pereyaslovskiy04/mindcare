"""
Pydantic-схемы allowlist почтовых доменов (admin CRUD).

extra="forbid" на create/patch: лишние поля → 422. Различение omitted vs
явного `comment: null` в PATCH делается в роутере через `model_fields_set`.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EmailDomainCreate(BaseModel):
    model_config = {"extra": "forbid"}

    domain: str = Field(min_length=1, max_length=255,
                        description="Доменное имя, напр. donnu.ru")
    comment: Optional[str] = Field(
        default=None, max_length=500,
        description="Необязательный комментарий",
    )


class EmailDomainUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    is_active: Optional[bool] = Field(
        default=None, description="Включить (true) / отключить (false)",
    )
    comment: Optional[str] = Field(
        default=None, max_length=500,
        description="Комментарий; передача null очищает",
    )


class EmailDomainRead(BaseModel):
    id: int
    domain: str
    is_active: bool
    comment: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
