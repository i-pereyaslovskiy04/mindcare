"""
Pydantic-схемы для модуля управления пользователями.
Используются эндпоинтами в routes_admin.py.
"""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class AdminUserListQuery(BaseModel):
    """Query-параметры для GET /api/admin/users."""

    page: int = Field(default=1, ge=1, description="Номер страницы, начиная с 1")
    size: int = Field(default=20, ge=1, le=100, description="Кол-во элементов на странице")
    search: Optional[str] = Field(default=None, max_length=200, description="Подстрока для поиска по email или ФИО")
    role: Optional[Literal["student", "psychologist", "admin", "supervisor"]] = Field(default=None, description="Фильтр по роли")
    is_active: Optional[bool] = Field(default=None, description="Фильтр по активности юзера")
    sort: str = Field(default="created_at", description="Поле сортировки")
    order: Literal["asc", "desc"] = Field(default="desc", description="Направление сортировки")
    include_deleted: bool = Field(default=False, description="Включать удалённых пользователей")


class AdminUserListItem(BaseModel):

    """Юзер в списке для админа. Не содержит чувствительных полей (password_hash и т.п.)."""

    # id нужен фронту для сравнения «это мой аккаунт» (self-admin guard, ADR-018):
    # auth /me отдаёт id, admin-строки — теперь тоже.
    id: int
    uuid: str
    email: str
    full_name: str
    roles: list[str] = Field(default_factory=list)
    # None у пользователя без активных ролей — НЕ маскируется как "student".
    role: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedUsersResponse(BaseModel):
    """Ответ GET /api/admin/users. Соответствует правилу из ARCHITECTURE.md раздел 6.1."""

    items: list[AdminUserListItem]
    total: int = Field(description="Общее число элементов с учётом фильтров")
    page: int
    size: int
    

class AdminUserCreate(BaseModel):
    """
    Тело запроса POST /api/admin/users. Пароль генерируется автоматически.

    legal_basis_confirmed — админ подтверждает наличие документированного
    основания для создания учётной записи и обработки персональных данных
    пользователя (НЕ «согласие за пользователя»). Без подтверждения — 422.
    """

    email: EmailStr = Field(description="Email нового пользователя")
    full_name: str = Field(min_length=2, description="ФИО пользователя")
    role: Optional[Literal["psychologist", "admin", "supervisor"]] = Field(
        default=None,
        description="Legacy single-role. student регистрируется сам. "
                    "Взаимоисключимо с roles[]; укажите ровно одно.",
    )
    roles: Optional[list[Literal["psychologist", "supervisor", "admin"]]] = Field(
        default=None,
        description="Multi-role создание: набор служебных ролей. student здесь "
                    "не принимается. Взаимоисключимо с role; укажите ровно одно.",
    )
    phone: Optional[str] = Field(default=None, description="Телефон (необязательно)")

    @model_validator(mode="after")
    def _role_or_roles(self):
        if (self.role is None) == (self.roles is None):
            raise ValueError(
                "Укажите ровно одно из role (legacy single) или roles[] (набор "
                "служебных ролей)"
            )
        if self.roles is not None and len(self.roles) == 0:
            raise ValueError("roles[] не может быть пустым")
        return self

    legal_basis_confirmed: bool = Field(
        description="Подтверждение наличия документированного основания "
                    "для создания учётной записи и обработки ПДн. Обязательно True."
    )
    basis_type: Literal[
        "service_duty", "employment", "contract", "administrative_order", "other"
    ] = Field(
        default="service_duty",
        description="Тип документированного основания",
    )
    basis_reference: str = Field(
        max_length=255,
        description="Документ-основание: «Приказ №…», «Договор №…» (обязателен)",
    )
    legal_basis_comment: Optional[str] = Field(
        default=None, description="Комментарий к основанию (необязательно)",
    )

    @field_validator("legal_basis_confirmed")
    @classmethod
    def _must_be_confirmed(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError(
                "Необходимо подтвердить наличие документированного основания "
                "для создания учётной записи и обработки персональных данных"
            )
        return v

    @field_validator("basis_reference")
    @classmethod
    def _basis_reference_required(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError(
                "Необходимо указать basis_reference (документ-основание) "
                "для создания служебной учётной записи"
            )
        return stripped


class AdminUserCreateResponse(BaseModel):
    """Ответ POST /api/admin/users."""

    uuid: str
    email: str
    full_name: str
    roles: list[str] = Field(default_factory=list)
    role: str
    is_active: bool
    created_at: datetime
    temporary_password: str

    model_config = {"from_attributes": True}


class AdminUserUpdate(BaseModel):
    """Тело запроса PATCH /api/admin/users/{uuid}. Все поля опциональны.

    Смена роли на служебную (psychologist/supervisor/admin) требует
    документированного основания — те же поля, что и в AdminUserCreate.
    Без подтверждения роль не меняется (см. service/storage). Это НЕ
    consent_records: админ не «соглашается за пользователя».
    """

    full_name: Optional[str] = Field(default=None, min_length=2, description="ФИО пользователя")
    phone: Optional[str] = Field(default=None, description="Телефон")
    is_active: Optional[bool] = Field(default=None, description="Активность аккаунта")
    role: Optional[Literal["student", "psychologist", "admin", "supervisor"]] = Field(
        default=None,
        description="Legacy single-role adapter. Multi-role пользователь → 409, "
                    "используйте roles[]. student — только no-op.",
    )
    roles: Optional[list[Literal["psychologist", "supervisor", "admin"]]] = Field(
        default=None,
        description="Set-based staff-role management: целевой набор служебных "
                    "ролей. student read-only и здесь не принимается. Взаимо"
                    "исключимо с role.",
    )

    @model_validator(mode="after")
    def _role_xor_roles(self):
        if self.role is not None and self.roles is not None:
            raise ValueError(
                "Укажите либо role (legacy single), либо roles[] (set-based), "
                "но не оба"
            )
        return self

    # Legal basis — требуется только при смене роли на служебную (см. service/storage).
    legal_basis_confirmed: Optional[bool] = Field(
        default=None,
        description="Подтверждение документированного основания при назначении служебной роли",
    )
    basis_type: Optional[Literal[
        "service_duty", "employment", "contract", "administrative_order", "other"
    ]] = Field(default=None, description="Тип документированного основания")
    basis_reference: Optional[str] = Field(
        default=None, max_length=255,
        description="Документ-основание: «Приказ №…», «Договор №…» (обязателен для служебной роли)",
    )
    legal_basis_comment: Optional[str] = Field(
        default=None, description="Комментарий к основанию (необязательно)",
    )


class AdminUserRead(BaseModel):
    """Ответ PATCH /api/admin/users/{uuid} и GET /api/admin/users/{uuid}."""

    # id — для сравнения «это мой аккаунт» на фронте (self-admin guard).
    id: int
    uuid: str
    email: str
    full_name: str
    phone: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    # None у пользователя без активных ролей — НЕ маскируется как "student".
    role: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

    model_config = {"from_attributes": True}