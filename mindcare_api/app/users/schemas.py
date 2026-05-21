"""
Pydantic-схемы для модуля управления пользователями.
Используются эндпоинтами в routes_admin.py.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field


class AdminUserListQuery(BaseModel):
    """Query-параметры для GET /api/admin/users."""

    page: int = Field(default=1, ge=1, description="Номер страницы, начиная с 1")
    size: int = Field(default=20, ge=1, le=100, description="Кол-во элементов на странице")
    search: Optional[str] = Field(default=None, max_length=200, description="Подстрока для поиска по email или ФИО")
    role: Optional[Literal["student", "psychologist", "admin", "supervisor"]] = Field(default=None, description="Фильтр по роли")
    is_active: Optional[bool] = Field(default=None, description="Фильтр по активности юзера")
    sort: str = Field(default="created_at", description="Поле сортировки")
    order: Literal["asc", "desc"] = Field(default="desc", description="Направление сортировки")


class AdminUserListItem(BaseModel):

    """Юзер в списке для админа. Не содержит чувствительных полей (password_hash и т.п.)."""

    uuid: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedUsersResponse(BaseModel):
    """Ответ GET /api/admin/users. Соответствует правилу из ARCHITECTURE.md раздел 6.1."""

    items: list[AdminUserListItem]
    total: int = Field(description="Общее число элементов с учётом фильтров")
    page: int
    size: int
    

class AdminUserCreate(BaseModel):
    """Тело запроса POST /api/admin/users. Пароль генерируется автоматически."""

    email: EmailStr = Field(description="Email нового пользователя")
    full_name: str = Field(min_length=2, description="ФИО пользователя")
    role: Literal["psychologist", "admin", "supervisor"] = Field(
        description="Роль нового пользователя. student регистрируется сам."
    )
    phone: Optional[str] = Field(default=None, description="Телефон (необязательно)")


class AdminUserCreateResponse(BaseModel):
    """Ответ POST /api/admin/users."""

    uuid: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime
    temporary_password: str

    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    """Тело запроса PATCH /api/admin/users/{uuid}. Все поля опциональны."""

    full_name: Optional[str] = Field(default=None, min_length=2, description="ФИО пользователя")
    phone: Optional[str] = Field(default=None, description="Телефон")
    is_active: Optional[bool] = Field(default=None, description="Активность аккаунта")
    role: Optional[Literal["student", "psychologist", "admin", "supervisor"]] = Field(
        default=None, description="Новая роль пользователя"
    )


class AdminUserRead(BaseModel):
    """Ответ PATCH /api/admin/users/{uuid} и GET /api/admin/users/{uuid}."""

    uuid: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}