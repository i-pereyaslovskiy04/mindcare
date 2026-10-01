"""
Реестр OAuth-адаптеров (Stage Social Auth 2B).

В Stage 2B production-реестр ПУСТ: реальных адаптеров Яндекс/VK ещё нет,
поэтому любой провайдер даёт `oauth_provider_unavailable`. Адаптеры
регистрируются Stage 3. Тесты регистрируют FakeProvider под разрешённым
именем (yandex/vk — CHECK в БД) и восстанавливают реестр после теста.
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


def registered_providers() -> dict[str, OAuthProvider]:
    """Снимок реестра (для восстановления в тестах)."""
    return dict(_REGISTRY)


def restore_providers(snapshot: dict[str, OAuthProvider]) -> None:
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)
