from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.tags.schemas import TagPublicRead


class NewsCreate(BaseModel):
    title:             str            = Field(min_length=1, max_length=255)
    content:           Optional[str]  = None
    cover_image_uuid:  Optional[str]  = None
    tag_uuids:         list[str]      = Field(default_factory=list)
    is_published:      bool           = False
    published_at:      Optional[datetime] = None


class NewsUpdate(BaseModel):
    title:             Optional[str]      = Field(default=None, min_length=1, max_length=255)
    content:           Optional[str]      = None
    cover_image_uuid:  Optional[str]      = None
    tag_uuids:         Optional[list[str]] = None
    is_published:      Optional[bool]     = None
    published_at:      Optional[datetime] = None


class NewsRead(BaseModel):
    uuid:             str
    title:            str
    content:          Optional[str]
    cover_image_url:  Optional[str]
    tags:             list[TagPublicRead]
    is_published:     bool
    published_at:     Optional[datetime]
    created_at:       datetime
    updated_at:       datetime
    created_by_name:  Optional[str]

    model_config = {"from_attributes": True}


class NewsListItem(BaseModel):
    """Облегчённый объект для таблицы в AdminNewsPage."""
    uuid:            str
    title:           str
    cover_image_url: Optional[str]
    tags:            list[TagPublicRead]
    is_published:    bool
    published_at:    Optional[datetime]
    created_at:      datetime
    created_by_name: Optional[str]

    model_config = {"from_attributes": True}


class PaginatedNewsResponse(BaseModel):
    items: list[NewsListItem]
    total: int
    page:  int
    size:  int


class AdminNewsListQuery(BaseModel):
    page:         int            = Field(default=1, ge=1)
    size:         int            = Field(default=20, ge=1, le=100)
    search:       Optional[str]  = Field(default=None, max_length=200)
    is_published: Optional[bool] = None
