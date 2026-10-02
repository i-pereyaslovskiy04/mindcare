"""
Регистрация настроенных OAuth-адаптеров при старте (Stage Social Auth 3A).

Вызывается из FastAPI lifespan после init_db. Social login — необязательная
функция: неполная или небезопасная конфигурация НЕ роняет запуск MindCare —
адаптер просто не регистрируется (/api/auth/oauth/{provider}/* → 404
oauth_provider_unavailable), а в лог пишется ERROR без значений настроек.

Функция только ДОБАВЛЯЕТ адаптеры и никогда не очищает реестр: повторный вызов
(reload, повторный lifespan TestClient) идемпотентен, а FakeProvider, который
тест зарегистрировал сам, не стирается. Каждый воркер uvicorn — отдельный
процесс со своим реестром; адаптер хранит только client_id.

Адреса callback должны быть https:// либо http:// на loopback-хосте (dev:
http://localhost:8000 — Яндекс OAuth такой Redirect URI принимает). Проверка не
зависит от ENV: исторически локальный .env может содержать ENV=production.
"""
import logging
from typing import Optional
from urllib.parse import urlsplit

from app.core.config import settings as app_settings
from app.oauth.providers import register_provider
from app.oauth.providers.yandex import YandexProvider

log = logging.getLogger(__name__)

_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_CLIENT_ID_MAX = 128


def is_allowed_callback_url(url: object, *, allow_query: bool) -> bool:
    """https:// с хостом либо http:// на loopback; без userinfo и fragment.

    allow_query=False для OAUTH_CALLBACK_BASE_URL (к нему дописывается путь),
    True — для OAUTH_FRONTEND_CALLBACK_URL (к нему дописывается только #…).
    """
    if not isinstance(url, str) or not url or url != url.strip():
        return False
    try:
        parts = urlsplit(url)
        parts.port   # ValueError на некорректном порту
    except ValueError:
        return False
    host = parts.hostname
    if not host or parts.username is not None or parts.password is not None:
        return False
    if parts.fragment or "#" in url:
        return False
    if parts.query and not allow_query:
        return False
    if parts.scheme == "https":
        return True
    return parts.scheme == "http" and host in _LOOPBACK_HOSTS


def _valid_client_id(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not 0 < len(value) <= _CLIENT_ID_MAX:
        return None
    if not all("\x21" <= ch <= "\x7e" for ch in value):
        return None
    return value


def _build_yandex(config) -> Optional[YandexProvider]:
    if not config.YANDEX_OAUTH_ENABLED:
        log.info("Yandex ID login disabled (YANDEX_OAUTH_ENABLED=false)")
        return None
    client_id = _valid_client_id(config.YANDEX_OAUTH_CLIENT_ID)
    if client_id is None:
        log.error(
            "Yandex ID login NOT enabled: YANDEX_OAUTH_CLIENT_ID is empty or "
            "malformed. MindCare continues without it."
        )
        return None
    if not is_allowed_callback_url(config.OAUTH_CALLBACK_BASE_URL, allow_query=False):
        log.error(
            "Yandex ID login NOT enabled: OAUTH_CALLBACK_BASE_URL must be https:// "
            "or http:// on localhost, without credentials, query or fragment. "
            "MindCare continues without it."
        )
        return None
    if not is_allowed_callback_url(config.OAUTH_FRONTEND_CALLBACK_URL, allow_query=True):
        log.error(
            "Yandex ID login NOT enabled: OAUTH_FRONTEND_CALLBACK_URL must be "
            "https:// or http:// on localhost, without credentials or fragment. "
            "MindCare continues without it."
        )
        return None
    return YandexProvider(client_id)


def register_configured_providers(config=None) -> list[str]:
    """Регистрирует адаптеры, конфигурация которых полна и безопасна.

    Возвращает имена зарегистрированных этим вызовом провайдеров. Никогда не
    бросает: сбой bootstrap не должен останавливать MindCare.
    """
    config = config or app_settings
    registered: list[str] = []
    try:
        yandex = _build_yandex(config)
        if yandex is not None:
            register_provider(yandex)
            registered.append(yandex.name)
            base = config.OAUTH_CALLBACK_BASE_URL.rstrip("/")
            # redirect_uri — не секрет; лог помогает сверить его с Redirect URI
            # приложения: при неточном совпадении Яндекс молча берёт первый
            # зарегистрированный адрес.
            log.info(
                "Yandex ID login enabled (redirect_uri=%s/api/auth/oauth/yandex/callback)",
                base,
            )
    except Exception as exc:   # noqa: BLE001 — social login не блокирует старт
        log.error(
            "OAuth providers bootstrap failed (%s); social login unavailable",
            type(exc).__name__,
        )
    return registered
