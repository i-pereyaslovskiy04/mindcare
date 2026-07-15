from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional
from datetime import datetime

Role = Literal["student", "psychologist", "admin", "supervisor"]

# Общие поля роли для auth-ответов (ADR-018): `roles` — источник истины (набор
# активных membership-ролей), `role` — legacy/default/effective primary для
# совместимости; может быть None у аккаунта без активных ролей (не маскируем
# отсутствие ролей как "student").


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
    roles: list[Role] = Field(default_factory=list)
    role: Optional[Role] = None


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    roles: list[Role] = Field(default_factory=list)
    role: Optional[Role] = None


class ProfileRead(BaseModel):
    """Self-profile (нечувствительные поля текущего пользователя)."""
    id: str
    email: str
    full_name: str
    phone: Optional[str] = None
    roles: list[Role] = Field(default_factory=list)
    role: Optional[Role] = None


class ProfileUpdate(BaseModel):
    """Self-update: только разрешённые поля. extra='forbid' → email/role/is_active
    в body дают 422, а не молча игнорируются."""
    model_config = {"extra": "forbid"}
    full_name: str
    phone: Optional[str] = Field(default=None, max_length=50)


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
