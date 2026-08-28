from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ServiceCardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    benefits: list[str] = Field(default_factory=list)
    image_uuid: Optional[str] = None
    # Свободная строка, не строгий URL-тип: допускает и внутренние
    # относительные пути (/services), и внешние абсолютные ссылки.
    link_url: Optional[str] = Field(default=None, max_length=2048)
    display_order: int = 0
    is_active: bool = True


class ServiceCardUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, min_length=1)
    benefits: Optional[list[str]] = None
    image_uuid: Optional[str] = None
    link_url: Optional[str] = Field(default=None, max_length=2048)
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class ServiceCardRead(BaseModel):
    id: int
    uuid: str
    title: str
    description: str
    benefits: list[str]
    image_uuid: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PublicServiceCardRead(BaseModel):
    title: str
    description: str
    benefits: list[str]
    image_url: Optional[str] = None
    link_url: Optional[str] = None

    model_config = {"from_attributes": True}
