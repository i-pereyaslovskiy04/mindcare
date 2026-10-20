"""Pydantic-схемы social login (Stage Social Auth 2B).

Успешный complete возвращает существующий app.auth.schemas.SessionResponse —
тот же контракт, что у входа по паролю; отдельной OAuth-сессии нет.
"""
from typing import Optional

from pydantic import BaseModel, Field, StrictBool, field_validator


class OAuthStartResponse(BaseModel):
    authorize_url: str


class OAuthCompleteRequest(BaseModel):
    model_config = {"extra": "forbid"}
    # token_urlsafe(32) — 43 символа; запас по длине без приёма мусора.
    ticket: str = Field(min_length=1, max_length=128)


class OAuthRegistrationPreviewRequest(BaseModel):
    """Что показать на шаге email (Stage Social Auth VK-1B). Только ticket."""
    model_config = {"extra": "forbid"}
    ticket: str = Field(min_length=1, max_length=128)


class OAuthRegistrationPreviewResponse(BaseModel):
    provider: str
    # Маскированный адрес ticket (`i***@domain.ru`) или null. Raw email не отдаётся.
    email_masked: Optional[str] = None
    # Можно ли продолжить с этим адресом (есть и проходит allowlist, если нужен).
    email_allowed: bool
    # Может ли пользователь указать другой адрес (VK — да, Яндекс — нет).
    email_editable: bool


class OAuthRegistrationInitRequest(BaseModel):
    """Отправка кода регистрации через провайдера (Stage Social Auth 4 / VK-1B).

    Имя, провайдер и subject берутся из ticket — от клиента они не принимаются
    (лишние поля → 422). `email` — необязателен и допустим только для
    провайдера с выбором email (VK): адрес, который пользователь указал сам.
    Для Яндекса любой переданный email → 422 `email_not_changeable`. Формат,
    allowlist и занятость проверяет service/storage (стабильные коды ошибок)."""
    model_config = {"extra": "forbid"}
    ticket: str = Field(min_length=1, max_length=128)
    email: Optional[str] = Field(default=None, min_length=1, max_length=320)


class OAuthRegistrationInitResponse(BaseModel):
    message: str
    # Маскированный адрес (`i***@yandex.ru`) для экрана подтверждения.
    email_masked: str


class OAuthRegistrationConfirmRequest(BaseModel):
    model_config = {"extra": "forbid"}
    ticket: str = Field(min_length=1, max_length=128)
    # Только ASCII-цифры: \d в движке regex pydantic пропускает и юникодные.
    code: str = Field(pattern=r"^[0-9]{6}$")
    # Согласие MindCare — только буквальное JSON true: false, отсутствие, 1 или
    # "true" → 422, ничего не создаётся (Literal[True] пропустил бы число 1).
    consent_accepted: StrictBool

    @field_validator("consent_accepted")
    @classmethod
    def _consent_must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("consent must be accepted")
        return value
