"""
Stage Social Auth 2B — unit-тесты без БД: криптопримитивы, реестр провайдеров,
правило «чистый студент», маскировка access log, конфиг cookie.
"""
import base64
import hashlib
import logging
import re

import pytest

from app.auth.roles import is_pure_student
from app.core import log_redaction
from app.core.encryption import decrypt_text, encrypt_text
from app.oauth import providers, security, service
from tests.oauth_fakes import FakeProvider, registered

_URLSAFE = re.compile(r"^[A-Za-z0-9_-]+$")


# ── security helpers ─────────────────────────────────────────────────────────

def test_state_and_ticket_have_256_bits_and_urlsafe_alphabet():
    for gen in (security.generate_state, security.generate_ticket):
        values = {gen() for _ in range(50)}
        assert len(values) == 50                        # без повторов
        for v in values:
            assert len(v) == 43 and _URLSAFE.match(v)   # 32 байта → 43 символа


def test_state_meets_vk_minimum_length():
    assert len(security.generate_state()) >= 32


def test_verifier_length_within_pkce_range():
    verifier = security.generate_code_verifier()
    assert 43 <= len(verifier) <= 128
    assert _URLSAFE.match(verifier)


def test_challenge_is_s256_without_padding():
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"   # пример RFC 7636 App. B
    assert security.code_challenge_s256(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    v = security.generate_code_verifier()
    expected = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    assert security.code_challenge_s256(v) == expected
    assert "=" not in security.code_challenge_s256(v)


def test_sha256_hex_matches_db_format():
    h = security.sha256_hex(security.generate_state())
    assert re.fullmatch(r"[0-9a-f]{64}", h)


def test_constant_time_equals():
    assert security.constant_time_equals("abc", "abc")
    assert not security.constant_time_equals("abc", "abd")
    assert not security.constant_time_equals("abc", "")


def test_verifier_roundtrips_through_encryption():
    v = security.generate_code_verifier()
    enc = encrypt_text(v)
    assert enc.startswith("enc:v1:") and v not in enc
    assert decrypt_text(enc) == v


# ── provider registry ────────────────────────────────────────────────────────

def test_production_registry_is_empty_by_default():
    assert providers.get_provider("yandex") is None
    assert providers.get_provider("vk") is None


def test_unknown_provider_name_never_resolves():
    with registered(FakeProvider("yandex")):
        assert providers.get_provider("fake") is None
        assert providers.get_provider("telegram") is None


def test_register_rejects_name_outside_db_check():
    with pytest.raises(ValueError):
        providers.register_provider(FakeProvider("fake"))


def test_registered_context_restores_registry():
    with registered(FakeProvider("vk")):
        assert providers.get_provider("vk") is not None
    assert providers.get_provider("vk") is None


# ── pure student ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("roles,expected", [
    (["student"], True),
    (["student", "psychologist"], False),
    (["student", "supervisor"], False),
    (["student", "admin"], False),
    (["psychologist"], False),
    ([], False),
])
def test_is_pure_student(roles, expected):
    assert is_pure_student(roles) is expected


# ── cookie / redirect config ─────────────────────────────────────────────────

def test_cookie_secure_follows_callback_base_scheme(monkeypatch):
    monkeypatch.setattr(service.settings, "OAUTH_CALLBACK_BASE_URL", "http://localhost:8000")
    assert service.state_cookie_secure() is False
    monkeypatch.setattr(service.settings, "OAUTH_CALLBACK_BASE_URL", "https://mindcare.example")
    assert service.state_cookie_secure() is True


def test_callback_redirect_uri_goes_to_backend(monkeypatch):
    monkeypatch.setattr(service.settings, "OAUTH_CALLBACK_BASE_URL", "http://localhost:8000/")
    assert service.callback_redirect_uri("yandex") == (
        "http://localhost:8000/api/auth/oauth/yandex/callback"
    )


# ── access-log redaction ─────────────────────────────────────────────────────

def _access_record(target):
    return logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d', ("127.0.0.1:5000", "GET", target, "1.1", 302), None,
    )


def test_callback_query_is_redacted():
    record = _access_record("/api/auth/oauth/yandex/callback?code=SECRETCODE&state=SECRETSTATE")
    assert log_redaction.OAuthCallbackQueryRedactor().filter(record) is True
    line = record.getMessage()
    assert "SECRETCODE" not in line and "SECRETSTATE" not in line
    assert "/api/auth/oauth/yandex/callback?<redacted>" in line


@pytest.mark.parametrize("target", [
    "/api/auth/oauth/yandex/callback",                 # без query
    "/api/auth/login",
    "/api/auth/oauth/yandex/start",
    "/api/diary/entries?limit=10&offset=0",
    "/api/auth/oauth/yandex/callbackx?code=1",
])
def test_other_targets_untouched(target):
    record = _access_record(target)
    log_redaction.OAuthCallbackQueryRedactor().filter(record)
    assert record.args[2] == target


@pytest.mark.parametrize("args", [None, (), ("a",), ("a", "b", 3), ({"k": "v"},)])
def test_unexpected_records_do_not_break(args):
    record = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, "msg", args, None)
    assert log_redaction.OAuthCallbackQueryRedactor().filter(record) is True


def test_filter_installed_on_uvicorn_access_after_app_import():
    import app.main  # noqa: F401
    filters = logging.getLogger("uvicorn.access").filters
    assert sum(isinstance(f, log_redaction.OAuthCallbackQueryRedactor) for f in filters) == 1
    log_redaction.install_access_log_redaction()   # идемпотентно
    assert sum(isinstance(f, log_redaction.OAuthCallbackQueryRedactor) for f in filters) == 1
