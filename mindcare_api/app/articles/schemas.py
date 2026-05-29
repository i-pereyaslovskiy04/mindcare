from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

from app.tags.schemas import TagPublicRead


class CategoryRead(BaseModel):
    id:   int
    name: str
    slug: str

    model_config = {"from_attributes": True}


class ArticleCreate(BaseModel):
    title:            str           = Field(min_length=1, max_length=255)
    excerpt:          Optional[str] = None
    content:          Optional[str] = None
    cover_image_uuid: Optional[str] = None
    category_ids:     list[int]     = Field(default_factory=list)
    tag_uuids:        list[str]     = Field(default_factory=list)
    is_published:     bool          = False
    published_at:     Optional[datetime] = None


class ArticleUpdate(BaseModel):
    title:            Optional[str]       = Field(default=None, min_length=1, max_length=255)
    excerpt:          Optional[str]       = None
    content:          Optional[str]       = None
    cover_image_uuid: Optional[str]       = None
    category_ids:     Optional[list[int]] = None
    tag_uuids:        Optional[list[str]] = None
    is_published:     Optional[bool]      = None
    published_at:     Optional[datetime]  = None


class ArticleRead(BaseModel):
    uuid:             str
    title:            str
    excerpt:          Optional[str]
    content:          Optional[str]
    cover_image_url:  Optional[str]
    categories:       list[CategoryRead]
    tags:             list[TagPublicRead]
    is_published:     bool
    published_at:     Optional[datetime]
    created_at:       datetime
    updated_at:       datetime
    created_by_name:  Optional[str]

    model_config = {"from_attributes": True}


class ArticleListItem(BaseModel):
    """Облегчённый объект для таблицы в AdminArticlesPage."""
    uuid:             str
    title:            str
    excerpt:          Optional[str]
    cover_image_url:  Optional[str]
    categories:       list[CategoryRead]
    tags:             list[TagPublicRead]
    is_published:     bool
    published_at:     Optional[datetime]
    created_at:       datetime
    created_by_name:  Optional[str]

    model_config = {"from_attributes": True}


class PaginatedArticlesResponse(BaseModel):
    items: list[ArticleListItem]
    total: int
    page:  int
    size:  int


class AdminArticlesListQuery(BaseModel):
    page:         int            = Field(default=1, ge=1)
    size:         int            = Field(default=20, ge=1, le=100)
    search:       Optional[str]  = Field(default=None, max_length=200)
    is_published: Optional[bool] = None
    category_id:  Optional[int]  = None
