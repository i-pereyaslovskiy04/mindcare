"""
Provider-neutral контракт OAuth-адаптера (Stage Social Auth 2B).

Адаптер (Яндекс ID / VK ID — Stage 3; в тестах — FakeProvider) скрывает всё
провайдер-специфичное: формат authorize URL, разбор callback, обмен code на
токены и запрос профиля. Наружу выходят ТОЛЬКО нормализованные структуры ниже:
ни access/refresh/id token, ни сырой профиль, ни текст ошибки провайдера
сервису не передаются.
"""
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol

# Нормализованный код отмены пользователем (RFC 6749 §4.1.2.1 access_denied).
# Адаптер обязан приводить к нему отказ пользователя на странице провайдера.
CANCELLED_ERROR = "access_denied"


@dataclass(frozen=True)
class ProviderIdentity:
    """Нормализованная identity. subject — стабильный id у провайдера
    (Яндекс `id`, VK `user_id`). email — нормализованный адрес провайдера
    или None, suggested_name — имя для начального профиля или None. Для входа
    ни то ни другое не используется; регистрация (Stage 4) записывает их в
    registration-ticket, а владение email подтверждает только OTP MindCare.
    Привязки к существующему аккаунту по email нет."""
    provider: str
    subject: str
    email: Optional[str] = None
    suggested_name: Optional[str] = None


@dataclass(frozen=True)
class ProviderCallback:
    """Нормализованный callback. error — только код (никогда не
    error_description); extra — провайдер-специфичные поля для обмена
    (например, VK device_id). Ничто отсюда не логируется."""
    state: Optional[str]
    code: Optional[str]
    error: Optional[str]
    extra: Mapping[str, str] = field(default_factory=dict)


class ProviderError(Exception):
    """Базовая ошибка адаптера. Сообщение фиксированное — без текста провайдера."""


class ProviderUnavailable(ProviderError):
    """Провайдер недоступен (сеть, таймаут, 5xx)."""


class ProviderRejected(ProviderError):
    """Провайдер отклонил обмен (неверный code, PKCE mismatch, отозван доступ)."""


class OAuthProvider(Protocol):
    name: str

    def build_authorize_url(
        self, *, state: str, code_challenge: str, redirect_uri: str,
    ) -> str:
        """Authorize URL с state и PKCE challenge (метод S256)."""

    def parse_callback(self, query: Mapping[str, str]) -> ProviderCallback:
        """Разбор query callback. Не бросает: недостающее поле → None."""

    def resolve_identity(
        self, *, code: str, code_verifier: str, redirect_uri: str,
        extra: Mapping[str, str],
    ) -> ProviderIdentity:
        """code + verifier → identity. Токены провайдера живут только внутри.
        Бросает ProviderUnavailable / ProviderRejected."""
