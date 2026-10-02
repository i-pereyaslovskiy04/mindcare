"""
Stage Social Auth 3A — bootstrap OAuth-адаптеров (без БД и без сети).

Регистрируется только полностью и безопасно настроенный Яндекс ID; неполная
конфигурация не роняет старт, а реестр только дополняется (FakeProvider тестов
не стирается). SAFE_TEST_ENV выключает реального Яндекса в автотестах.
"""
import logging
import os
from types import SimpleNamespace

import pytest

from app.core.config import Settings, settings
from app.oauth import providers
from app.oauth.providers import bootstrap
from app.oauth.providers.bootstrap import (
    is_allowed_callback_url, register_configured_providers,
)
from app.oauth.providers.yandex import YandexProvider
from isolated_test_db import SAFE_TEST_ENV   # scripts/ — в sys.path (tests/conftest.py)
from tests.oauth_fakes import FakeProvider, registered

CLIENT_ID = "synthetic0client0id0000000000001"


def _config(**overrides):
    base = dict(
        YANDEX_OAUTH_ENABLED=True,
        YANDEX_OAUTH_CLIENT_ID=CLIENT_ID,
        OAUTH_CALLBACK_BASE_URL="http://localhost:8000",
        OAUTH_FRONTEND_CALLBACK_URL="http://localhost:3000/auth/callback",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture(autouse=True)
def clean_registry():
    snapshot = providers.registered_providers()
    providers.restore_providers({})
    yield
    providers.restore_providers(snapshot)


# ── регистрация ──────────────────────────────────────────────────────────────

def test_disabled_registers_nothing(caplog):
    caplog.set_level(logging.INFO, logger=bootstrap.__name__)
    assert register_configured_providers(_config(YANDEX_OAUTH_ENABLED=False)) == []
    assert providers.get_provider("yandex") is None
    assert "disabled" in caplog.text


def test_enabled_with_client_id_registers_yandex(caplog):
    caplog.set_level(logging.INFO, logger=bootstrap.__name__)
    assert register_configured_providers(_config()) == ["yandex"]
    provider = providers.get_provider("yandex")
    assert isinstance(provider, YandexProvider)
    assert "redirect_uri=http://localhost:8000/api/auth/oauth/yandex/callback" in caplog.text
    assert CLIENT_ID not in caplog.text


def test_client_id_is_stripped():
    register_configured_providers(_config(YANDEX_OAUTH_CLIENT_ID=f"  {CLIENT_ID}  "))
    url = providers.get_provider("yandex").build_authorize_url(
        state="s", code_challenge="c", redirect_uri="r",
    )
    assert f"client_id={CLIENT_ID}&" in url


@pytest.mark.parametrize("client_id", ["", "   ", "has space", "tab\tid", "x" * 129, None])
def test_enabled_with_bad_client_id_not_registered(caplog, client_id):
    caplog.set_level(logging.ERROR, logger=bootstrap.__name__)
    assert register_configured_providers(
        _config(YANDEX_OAUTH_CLIENT_ID=client_id)) == []
    assert providers.get_provider("yandex") is None
    assert "YANDEX_OAUTH_CLIENT_ID" in caplog.text


@pytest.mark.parametrize("field,value", [
    ("OAUTH_CALLBACK_BASE_URL", "http://mindcare.example.ru"),
    ("OAUTH_CALLBACK_BASE_URL", "ftp://localhost:8000"),
    ("OAUTH_CALLBACK_BASE_URL", ""),
    ("OAUTH_CALLBACK_BASE_URL", "https://user:pw@mindcare.example.ru"),
    ("OAUTH_CALLBACK_BASE_URL", "https://mindcare.example.ru?x=1"),
    ("OAUTH_FRONTEND_CALLBACK_URL", "http://10.0.0.5:3000/auth/callback"),
    ("OAUTH_FRONTEND_CALLBACK_URL", "https://mindcare.example.ru/auth/callback#x"),
    ("OAUTH_FRONTEND_CALLBACK_URL", "javascript:alert(1)"),
])
def test_invalid_urls_not_registered(caplog, field, value):
    caplog.set_level(logging.ERROR, logger=bootstrap.__name__)
    assert register_configured_providers(_config(**{field: value})) == []
    assert providers.get_provider("yandex") is None
    assert field in caplog.text
    assert value not in caplog.text or value == ""


def test_https_production_layout_registered():
    assert register_configured_providers(_config(
        OAUTH_CALLBACK_BASE_URL="https://mindcare.example.ru",
        OAUTH_FRONTEND_CALLBACK_URL="https://mindcare.example.ru/auth/callback",
    )) == ["yandex"]


def test_idempotent_and_repeatable():
    assert register_configured_providers(_config()) == ["yandex"]
    assert register_configured_providers(_config()) == ["yandex"]
    assert isinstance(providers.get_provider("yandex"), YandexProvider)
    assert set(providers.registered_providers()) == {"yandex"}


def test_bootstrap_never_clears_test_registry():
    with registered(FakeProvider("vk")) as fake:
        register_configured_providers(_config())
        assert providers.get_provider("vk") is fake
        register_configured_providers(_config(YANDEX_OAUTH_ENABLED=False))
        assert providers.get_provider("vk") is fake
    assert providers.get_provider("vk") is None   # restore после теста


def test_bootstrap_never_raises(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger=bootstrap.__name__)

    def _boom(provider):
        raise RuntimeError("SECRET_bootstrap_detail")
    monkeypatch.setattr(bootstrap, "register_provider", _boom)
    assert register_configured_providers(_config()) == []
    assert "RuntimeError" in caplog.text
    assert "SECRET_bootstrap_detail" not in caplog.text


def test_vk_never_registered_by_bootstrap():
    register_configured_providers(_config())
    assert providers.get_provider("vk") is None


# ── валидатор URL ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    "http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000",
    "https://mindcare.example.ru", "https://mindcare.example.ru:8443",
])
def test_base_url_allowed(url):
    assert is_allowed_callback_url(url, allow_query=False)


@pytest.mark.parametrize("url", [
    "http://mindcare.example.ru", "http://localhost.evil.ru", "https://",
    "https://host:99999", " https://mindcare.example.ru", "https://x.ru#frag",
    "https://x.ru?a=1", None, 42,
])
def test_base_url_rejected(url):
    assert not is_allowed_callback_url(url, allow_query=False)


def test_frontend_url_may_have_query_but_no_fragment():
    assert is_allowed_callback_url("https://x.ru/cb?from=oauth", allow_query=True)
    assert not is_allowed_callback_url("https://x.ru/cb#a", allow_query=True)


# ── изоляция тестов от локального .env ───────────────────────────────────────

def test_safe_test_env_disables_real_yandex():
    assert SAFE_TEST_ENV["YANDEX_OAUTH_ENABLED"] == "false"
    assert SAFE_TEST_ENV["YANDEX_OAUTH_CLIENT_ID"] == ""
    assert os.environ.get("YANDEX_OAUTH_ENABLED") == "false"
    assert os.environ.get("YANDEX_OAUTH_CLIENT_ID") == ""
    assert settings.YANDEX_OAUTH_ENABLED is False
    assert settings.YANDEX_OAUTH_CLIENT_ID == ""


def test_env_overrides_dotenv_values(monkeypatch):
    monkeypatch.setenv("YANDEX_OAUTH_ENABLED", "false")
    monkeypatch.setenv("YANDEX_OAUTH_CLIENT_ID", "")
    fresh = Settings()
    assert fresh.YANDEX_OAUTH_ENABLED is False and fresh.YANDEX_OAUTH_CLIENT_ID == ""


def test_settings_defaults_are_disabled():
    fields = Settings.model_fields
    assert fields["YANDEX_OAUTH_ENABLED"].default is False
    assert fields["YANDEX_OAUTH_CLIENT_ID"].default == ""
    assert "YANDEX_OAUTH_CLIENT_SECRET" not in fields
