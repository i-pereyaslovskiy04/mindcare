from pydantic import BaseModel, EmailStr
from typing import Literal
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


class MessageResponse(BaseModel):
    message: str


class PasswordResetInitRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str
