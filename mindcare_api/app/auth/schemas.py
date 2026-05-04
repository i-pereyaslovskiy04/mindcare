from pydantic import BaseModel, EmailStr
from typing import Literal

Role = Literal["student", "psychologist", "admin"]


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


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


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: Role


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LogoutRequest(BaseModel):
    refresh_token: str


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
