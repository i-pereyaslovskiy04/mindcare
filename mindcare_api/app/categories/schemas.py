from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class CategoryRead(BaseModel):
    """Категория в ответе с количеством связанных материалов."""
    id:            int
    name:          str
    slug:          str
    description:   Optional[str]
    display_order: int
    is_active:     bool
    created_at:    datetime
    article_count: int = 0

    model_config = {"from_attributes": True}


class PaginatedCategoriesResponse(BaseModel):
    """Ответ GET /api/admin/categories."""
    items: list[CategoryRead]
    total: int
    page:  int
    size:  int


class AdminCategoriesListQuery(BaseModel):
    """Query-параметры для GET /api/admin/categories."""
    page:      int            = Field(default=1, ge=1)
    size:      int            = Field(default=50, ge=1, le=100)
    search:    Optional[str]  = Field(default=None, max_length=200)
    is_active: Optional[bool] = None


class CategoryCreate(BaseModel):
    """Тело запроса POST /api/admin/categories."""
    name:          str           = Field(min_length=1, max_length=100)
    slug:          Optional[str] = Field(default=None, max_length=100)
    description:   Optional[str] = None
    display_order: int           = Field(default=0, ge=0)
    is_active:     bool          = True


class CategoryUpdate(BaseModel):
    """Тело запроса PATCH /api/admin/categories/{id}."""
    name:          Optional[str] = Field(default=None, min_length=1, max_length=100)
    slug:          Optional[str] = Field(default=None, max_length=100)
    description:   Optional[str] = None
    display_order: Optional[int] = Field(default=None, ge=0)
    is_active:     Optional[bool] = None
