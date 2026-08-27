from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Известные страницы-получатели баннера. Добавление новой страницы —
# правка кода (новое значение здесь + опция в admin-select на фронте),
# без миграции схемы: сама колонка — обычная строка.
BannerPlacement = Literal["home", "services"]


class BannerSlideCreate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    highlight: Optional[str] = Field(default=None, max_length=255)
    sub: Optional[str] = None
    image_uuid: Optional[str] = None
    # Свободная строка, не строгий URL-тип: допускает и внутренние
    # относительные пути (/services), и внешние абсолютные ссылки.
    link_url: Optional[str] = Field(default=None, max_length=2048)
    placement: BannerPlacement = "home"
    display_order: int = 0
    is_active: bool = True


class BannerSlideUpdate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=255)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    highlight: Optional[str] = Field(default=None, max_length=255)
    sub: Optional[str] = None
    image_uuid: Optional[str] = None
    link_url: Optional[str] = Field(default=None, max_length=2048)
    placement: Optional[BannerPlacement] = None
    display_order: Optional[int] = None
    is_active: Optional[bool] = None


class BannerSlideRead(BaseModel):
    id: int
    uuid: str
    label: Optional[str] = None
    title: str
    highlight: Optional[str] = None
    sub: Optional[str] = None
    image_uuid: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    placement: str
    display_order: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PublicBannerSlideRead(BaseModel):
    label: Optional[str] = None
    title: str
    highlight: Optional[str] = None
    sub: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None

    model_config = {"from_attributes": True}
