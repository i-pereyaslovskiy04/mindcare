from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional
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


class RegisterConfirmRequest(BaseModel):
    email: EmailStr = Field(max_length=_EMAIL_MAX_LEN)
    code: str


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


# Оформление UI. Списки синхронизированы с mindcare_web/src/features/theme/ThemeContext.jsx.
ThemePalette = Literal["coffee", "nature", "classic", "hc"]
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
