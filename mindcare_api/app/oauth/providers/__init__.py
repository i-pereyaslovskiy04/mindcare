"""
Реестр OAuth-адаптеров (Stage Social Auth 2B).

Production-адаптеры регистрирует bootstrap.register_configured_providers()
из lifespan — только при полной конфигурации (Stage 3A: Яндекс ID; Stage VK-1A:
VK ID); незарегистрированный провайдер даёт `oauth_provider_unavailable`. Тесты
регистрируют FakeProvider под разрешённым именем (yandex/vk — CHECK в БД) и
восстанавливают реестр после теста.
"""
from typing import Optional

from app.db.models.oauth import OAUTH_PROVIDERS
from app.oauth.providers.base import OAuthProvider

_REGISTRY: dict[str, OAuthProvider] = {}


def get_provider(name: str) -> Optional[OAuthProvider]:
    """Зарегистрированный адаптер или None (неизвестное/неактивное имя)."""
    if name not in OAUTH_PROVIDERS:
        return None
    return _REGISTRY.get(name)


def register_provider(provider: OAuthProvider) -> None:
    if provider.name not in OAUTH_PROVIDERS:
        raise ValueError("unsupported OAuth provider name")
    _REGISTRY[provider.name] = provider


def unregister_provider(name: str) -> None:
    _REGISTRY.pop(name, None)


def public_social_providers() -> list[str]:
    """Имена провайдеров, через которые сейчас можно войти (Stage 3B,
    GET /api/public/config). Источник истины — фактический реестр после
    bootstrap, а не настройки .env. Только allowlist OAUTH_PROVIDERS в его
    порядке: ни объектов адаптеров, ни ClientID, ни URL наружу не выходит."""
    return [name for name in OAUTH_PROVIDERS if name in _REGISTRY]


def registered_providers() -> dict[str, OAuthProvider]:
    """Снимок реестра (для восстановления в тестах)."""
    return dict(_REGISTRY)


def restore_providers(snapshot: dict[str, OAuthProvider]) -> None:
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)
