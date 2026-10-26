from pydantic import (
    UUID4, BaseModel, ConfigDict, EmailStr, Field, StrictBool, field_validator,
)
from typing import Annotated, Literal, Optional, Union
from datetime import datetime

Role = Literal["student", "psychologist", "admin", "supervisor"]

# Общие поля роли для auth-ответов (ADR-018): `roles` — источник истины (набор
# активных membership-ролей), `role` — legacy/default/effective primary для
# совместимости; может быть None у аккаунта без активных ролей (не маскируем
# отсутствие ролей как "student").


# DB/audit-контракт ограничивают email 255 символами; отклоняем слишком длинный
# на входе (Pydantic) — до бизнес-операции и audit-записи. См. _EMAIL_MAX в
# app/audit/validation.py и колонки users.email / auth_log.user_email.
_EMAIL_MAX_LEN = 255


class RegisterInitRequest(BaseModel):
    name: str
    email: EmailStr = Field(max_length=_EMAIL_MAX_LEN)
    password: str


# Код подтверждения регистрации: ровно 6 ASCII-цифр, строкой (ведущие нули
# сохраняются). [0-9], а не \d: \d в Unicode-режиме принял бы и не-ASCII цифры.
OtpCode = Annotated[str, Field(pattern=r"^[0-9]{6}$")]


class RegisterConfirmByEmailRequest(BaseModel):
    """Шаг кода в исходной вкладке: email из формы регистрации + код."""
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=_EMAIL_MAX_LEN)
    code: OtpCode


class RegisterConfirmByReferenceRequest(BaseModel):
    """Ссылка из письма: registration_reference (UUIDv4 выпуска кода) + код.
    Reference лишь выбирает ожидающую регистрацию, без кода она не завершится."""
    model_config = ConfigDict(extra="forbid")

    registration_reference: UUID4
    code: OtpCode


# POST /api/auth/register/confirm: ровно один идентификатор выпуска кода.
# extra="forbid" у обеих моделей: оба идентификатора сразу, ни одного или
# посторонние поля - 422, двусмысленного состояния нет.
RegisterConfirmRequest = Union[
    RegisterConfirmByEmailRequest, RegisterConfirmByReferenceRequest,
]


class RegisterConfirmResponse(BaseModel):
    """email - только у подтверждения по ссылке (для формы входа) и только
    после успешного commit; у подтверждения по email поля нет."""
    message: str
    email: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=_EMAIL_MAX_LEN)
    password: str


class SessionResponse(BaseModel):
    """Ответ на успешный логин — токен сессии."""
    session_token: str
    expires_at: datetime
    roles: list[Role] = Field(default_factory=list)
    role: Optional[Role] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    roles: list[Role] = Field(default_factory=list)
    role: Optional[Role] = None
    # Impersonation (ADR-025): выставлены только когда текущая сессия создана
    # администратором «под именем». impersonating=False у обычных сессий.
    impersonating: bool = False
    impersonator_name: Optional[str] = None
    # Есть ли у аккаунта пароль (social-only аккаунт — False). Вычисляется на
    # backend из password_hash IS NOT NULL; сам хеш наружу не отдаётся.
    has_password: bool


# Оформление UI. Списки синхронизированы с mindcare_web/src/features/theme/ThemeContext.jsx.
ThemePalette = Literal["dongu", "coffee", "nature", "classic", "hc"]
ThemeMode = Literal["light", "dark", "system"]


class ProfileRead(BaseModel):
    """Self-profile (нечувствительные поля текущего пользователя)."""
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    roles: list[Role] = Field(default_factory=list)
    role: Optional[Role] = None
    # None = «не задано»: тему определяет устройство (localStorage).
    ui_theme_palette: Optional[ThemePalette] = None
    ui_theme_mode: Optional[ThemeMode] = None
    # См. UserResponse.has_password (экраны настроек: смена vs установка пароля).
    has_password: bool


class ProfileUpdate(BaseModel):
    """Self-update: только разрешённые поля. extra='forbid' → email/role/is_active
    в body дают 422, а не молча игнорируются.

    Все поля опциональны (PATCH-семантика): не переданы → не меняются
    (unset ≠ None). Явный null у phone/полей темы = сбросить значение.
    """
    model_config = {"extra": "forbid"}
    full_name: Optional[str] = None
    phone: Optional[str] = Field(default=None, max_length=50)
    ui_theme_palette: Optional[ThemePalette] = None
    ui_theme_mode: Optional[ThemeMode] = None


class MessageResponse(BaseModel):
    message: str


class PasswordResetInitRequest(BaseModel):
    email: EmailStr = Field(max_length=_EMAIL_MAX_LEN)


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr = Field(max_length=_EMAIL_MAX_LEN)
    code: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str


class SelfDeactivateRequest(BaseModel):
    """
    POST /api/auth/account/deactivate (ADR-028). Target — ТОЛЬКО
    authenticated user: поля user_id/uuid/email и любые иные → 422
    (extra="forbid"). confirm — буквальное JSON true (StrictBool).
    """

    model_config = ConfigDict(extra="forbid")

    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def _must_confirm(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("Подтвердите отключение аккаунта")
        return v
