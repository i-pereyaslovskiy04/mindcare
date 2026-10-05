"""Pydantic-схемы social login (Stage Social Auth 2B).

Успешный complete возвращает существующий app.auth.schemas.SessionResponse —
тот же контракт, что у входа по паролю; отдельной OAuth-сессии нет.
"""
from pydantic import BaseModel, Field, StrictBool, field_validator


class OAuthStartResponse(BaseModel):
    authorize_url: str


class OAuthCompleteRequest(BaseModel):
    model_config = {"extra": "forbid"}
    # token_urlsafe(32) — 43 символа; запас по длине без приёма мусора.
    ticket: str = Field(min_length=1, max_length=128)


class OAuthRegistrationInitRequest(BaseModel):
    """Отправка кода регистрации через провайдера (Stage Social Auth 4).
    Только ticket: email, имя, провайдер и subject берутся из ticket — от
    клиента они не принимаются (лишние поля → 422)."""
    model_config = {"extra": "forbid"}
    ticket: str = Field(min_length=1, max_length=128)


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
