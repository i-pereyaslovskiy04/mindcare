"""
Stage Social Auth 3B — GET /api/public/config: social_providers (без БД).

Источник истины — фактический реестр OAuth-адаптеров после bootstrap, а не
настройки .env. Наружу — только allowlisted имена, без ClientID, URL, scope и
адресов провайдера. Прежние ключи (лимиты загрузки) не меняются.
"""
import json

import httpx
import pytest

from app.main import public_config
from app.oauth import providers
from app.oauth.providers import public_social_providers
from app.oauth.providers.yandex import YandexProvider
from tests.oauth_fakes import FakeProvider

CLIENT_ID = "synthetic0client0id0000000000001"


@pytest.fixture(autouse=True)
def clean_registry():
    snapshot = providers.registered_providers()
    providers.restore_providers({})
    yield
    providers.restore_providers(snapshot)


def test_no_registered_provider_gives_empty_list():
    assert public_config()["social_providers"] == []


def test_registered_yandex_is_listed():
    providers.register_provider(YandexProvider(CLIENT_ID))
    assert public_config()["social_providers"] == ["yandex"]


def test_list_follows_allowlist_order():
    providers.register_provider(FakeProvider("vk"))
    providers.register_provider(FakeProvider("yandex"))
    assert public_social_providers() == ["yandex", "vk"]


def test_unknown_names_in_registry_never_leak():
    """Даже если в реестр что-то попало в обход register_provider."""
    snapshot = providers.registered_providers()
    snapshot["telegram"] = FakeProvider("yandex")
    snapshot["evil"] = FakeProvider("yandex")
    providers.restore_providers(snapshot)
    assert public_social_providers() == []


def test_response_contains_no_provider_internals():
    providers.register_provider(YandexProvider(
        CLIENT_ID, transport=httpx.MockTransport(lambda r: httpx.Response(500)),
    ))
    payload = public_config()
    blob = json.dumps(payload, ensure_ascii=False)
    assert set(payload) == {"newsImageMaxSizeMb", "mediaAvMaxSizeMb", "social_providers"}
    for forbidden in (CLIENT_ID, "client_id", "secret", "http://", "https://",
                      "oauth.yandex.ru", "login.yandex.ru", "login:email", "callback",
                      "ENV", "redirect"):
        assert forbidden not in blob, forbidden
    assert all(isinstance(name, str) for name in payload["social_providers"])


def test_existing_upload_limits_unchanged():
    payload = public_config()
    assert isinstance(payload["newsImageMaxSizeMb"], int)
    assert isinstance(payload["mediaAvMaxSizeMb"], int)
