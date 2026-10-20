from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TagCreate(BaseModel):
    """Тело запроса POST /api/admin/tags."""
    name: str = Field(min_length=1, max_length=100)


class TagUpdate(BaseModel):
    """Тело запроса PATCH /api/admin/tags/{uuid}."""
    name: str = Field(min_length=1, max_length=100)


class TagRead(BaseModel):
    """Тег в ответе с количеством использований."""
    uuid: str
    name: str
    article_count: int = 0
    news_count:    int = 0
    test_count:    int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class TagPublicRead(BaseModel):
    """Облегчённый тег для публичного autocomplete-эндпоинта."""
    uuid: str
    name: str

    model_config = {"from_attributes": True}


class PaginatedTagsResponse(BaseModel):
    """Ответ GET /api/admin/tags."""
    items: list[TagRead]
    total: int
    page:  int
    size:  int


class AdminTagListQuery(BaseModel):
    """Query-параметры для GET /api/admin/tags."""
    page:   int = Field(default=1, ge=1)
    size:   int = Field(default=50, ge=1, le=100)
    search: Optional[str] = Field(default=None, max_length=200)
