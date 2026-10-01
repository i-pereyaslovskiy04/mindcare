"""Pydantic-схемы social login (Stage Social Auth 2B).

Успешный complete возвращает существующий app.auth.schemas.SessionResponse —
тот же контракт, что у входа по паролю; отдельной OAuth-сессии нет.
"""
from pydantic import BaseModel, Field


class OAuthStartResponse(BaseModel):
    authorize_url: str


class OAuthCompleteRequest(BaseModel):
    model_config = {"extra": "forbid"}
    # token_urlsafe(32) — 43 символа; запас по длине без приёма мусора.
    ticket: str = Field(min_length=1, max_length=128)
