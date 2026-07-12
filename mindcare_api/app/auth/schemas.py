from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional
from datetime import datetime

Role = Literal["student", "psychologist", "admin", "supervisor"]


class RegisterInitRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class RegisterConfirmRequest(BaseModel):
    email: EmailStr
    code: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SessionResponse(BaseModel):
    """Ответ на успешный логин — токен сессии."""
    session_token: str
    expires_at: datetime
    role: Role


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: Role


# Оформление UI. Списки синхронизированы с mindcare_web/src/features/theme/ThemeContext.jsx.
ThemePalette = Literal["coffee", "nature", "classic", "hc"]
ThemeMode = Literal["light", "dark", "system"]


class ProfileRead(BaseModel):
    """Self-profile (нечувствительные поля текущего пользователя)."""
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    role: Role
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
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str
