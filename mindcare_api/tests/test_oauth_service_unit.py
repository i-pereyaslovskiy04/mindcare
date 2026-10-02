"""
Stage Social Auth 2B — unit-тесты порядка callback и правил входа (storage
замокан, БД не нужна). Интеграционное поведение — tests/integration/test_oauth_*.
"""
import pytest

from app.oauth import service
from app.oauth.errors import OAuthLoginDenied
from app.oauth.providers.base import ProviderIdentity
from app.oauth.security import code_challenge_s256
from tests.oauth_fakes import FakeProvider, registered

STATE = "s" * 43


@pytest.fixture
def calls(monkeypatch):
    """Фиксирует обращения к storage; consume по умолчанию успешен."""
    log = {"consume": 0, "ticket": 0}

    def _consume(**kw):
        log["consume"] += 1
        return {"intent": "login", "code_verifier_enc": "enc:v1:x", "user_id": None}

    monkeypatch.setattr(service.storage, "consume_auth_request", _consume)
    monkeypatch.setattr(
        service.storage, "create_login_ticket",
        lambda **kw: log.__setitem__("ticket", log["ticket"] + 1),
    )
    monkeypatch.setattr(service, "decrypt_text", lambda v: "verifier")
    return log


def _callback(query, cookie=STATE, provider="yandex"):
    return service.handle_callback(provider, query, cookie)


# ── browser binding до списания state ────────────────────────────────────────

@pytest.mark.parametrize("query,cookie", [
    ({"code": "c"}, STATE),                       # нет state
    ({"state": STATE, "code": "c"}, None),        # нет cookie
    ({"state": STATE, "code": "c"}, "x" * 43),    # не совпадает
    ({"state": STATE, "error": "access_denied"}, "x" * 43),   # ошибка + чужой state
])
def test_binding_failure_does_not_consume_or_clear_cookie(calls, query, cookie):
    with registered(FakeProvider()):
        outcome = _callback(query, cookie)
    assert outcome.fragment == {"error": "oauth_failed"}
    assert outcome.audit_code == "oauth_state_invalid"
    assert outcome.clear_cookie is False
    assert calls["consume"] == 0


def test_unregistered_provider_fails_without_consume_or_audit(calls):
    outcome = _callback({"state": STATE, "code": "c"})
    assert outcome.fragment == {"error": "oauth_failed"}
    assert outcome.audit_code is None and calls["consume"] == 0


def test_cancel_consumes_state_clears_cookie_and_is_not_audited(calls):
    fake = FakeProvider()
    with registered(fake):
        outcome = _callback({"state": STATE, "error": "access_denied"})
    assert calls["consume"] == 1
    assert outcome.fragment == {"error": "oauth_cancelled"}
    assert outcome.clear_cookie is True and outcome.audit_code is None
    assert fake.resolve_calls == 0


def test_provider_error_consumes_state_and_hides_provider_text(calls):
    with registered(FakeProvider()):
        outcome = _callback({
            "state": STATE, "error": "server_error",
            "error_description": "internal provider details",
        })
    assert calls["consume"] == 1
    assert outcome.fragment == {"error": "oauth_failed"}
    assert outcome.audit_code == "oauth_provider_error"
    assert "internal" not in str(outcome)


def test_missing_code_is_provider_error(calls):
    with registered(FakeProvider()):
        outcome = _callback({"state": STATE})
    assert outcome.audit_code == "oauth_provider_error" and outcome.clear_cookie


def test_consumed_or_unknown_state_is_state_invalid(calls, monkeypatch):
    monkeypatch.setattr(service.storage, "consume_auth_request", lambda **kw: None)
    with registered(FakeProvider()):
        outcome = _callback({"state": STATE, "code": "c"})
    assert outcome.audit_code == "oauth_state_invalid"
    assert outcome.clear_cookie is True


def test_link_intent_request_is_rejected_in_stage_2b(calls, monkeypatch):
    monkeypatch.setattr(
        service.storage, "consume_auth_request",
        lambda **kw: {"intent": "link", "code_verifier_enc": "enc:v1:x", "user_id": 1},
    )
    with registered(FakeProvider()):
        outcome = _callback({"state": STATE, "code": "c"})
    assert outcome.audit_code == "oauth_state_invalid"


def test_decrypt_failure_is_internal_error(calls, monkeypatch):
    def _boom(v):
        raise ValueError("bad key")
    monkeypatch.setattr(service, "decrypt_text", _boom)
    with registered(FakeProvider()):
        outcome = _callback({"state": STATE, "code": "c"})
    assert outcome.audit_code == "internal_error"
    assert outcome.fragment == {"error": "oauth_failed"}


@pytest.mark.parametrize("mode", ["unavailable", "rejected", "crash"])
def test_provider_failures_fail_closed(calls, mode):
    fake = FakeProvider()
    fake.mode = mode
    with registered(fake):
        outcome = _callback({"state": STATE, "code": "c"})
    assert fake.resolve_calls == 1
    assert outcome.fragment == {"error": "oauth_failed"}
    assert outcome.audit_code == "oauth_provider_error"
    assert calls["ticket"] == 0


class _OtherProviderIdentity(FakeProvider):
    """Адаптер вернул identity чужого провайдера — должен быть отказ."""

    def resolve_identity(self, **kw):
        return ProviderIdentity(provider="vk", subject="integ_x")


def test_identity_from_other_provider_fails_closed(calls):
    with registered(_OtherProviderIdentity("yandex")):
        outcome = _callback({"state": STATE, "code": "c"})
    assert outcome.audit_code == "oauth_provider_error"
    assert calls["ticket"] == 0


# ── правила входа ────────────────────────────────────────────────────────────

def _user(**kw):
    base = {"id": "7", "roles": ["student"], "role": "student", "is_active": True}
    return {**base, **kw}


def test_pure_active_student_allowed():
    service.assert_social_login_allowed(_user())


@pytest.mark.parametrize("user,code", [
    (_user(is_active=False), "account_disabled"),
    (_user(roles=[], role=None), "no_active_roles"),
    (_user(roles=["psychologist", "student"], role="psychologist"), "social_login_not_allowed"),
    (_user(roles=["admin", "student"], role="admin"), "social_login_not_allowed"),
])
def test_denials_map_to_stable_codes(user, code):
    with pytest.raises(OAuthLoginDenied) as ei:
        service.assert_social_login_allowed(user)
    assert ei.value.audit_code == code
    expected_external = (
        "social_login_not_allowed" if code == "social_login_not_allowed"
        else "account_unavailable"
    )
    assert ei.value.external_code == expected_external


# ── авторитетный провайдер для auth_log.auth_method (Stage Social Auth 3A) ───

def _fake_with_code():
    """FakeProvider, чей challenge совпадает с verifier из фикстуры calls
    (decrypt_text замокан на "verifier") — PKCE-проверка проходит честно."""
    fake = FakeProvider()
    fake.build_authorize_url(
        state=STATE, code_challenge=code_challenge_s256("verifier"), redirect_uri="r",
    )
    return fake


@pytest.mark.parametrize("query,cookie", [
    ({"code": "c"}, STATE),                                   # state_invalid
    ({"state": STATE, "error": "access_denied"}, STATE),      # отмена
    ({"state": STATE, "error": "server_error"}, STATE),       # provider_error
    ({"state": STATE}, STATE),                                # нет code
])
def test_registered_provider_outcomes_carry_registry_name(calls, query, cookie):
    with registered(FakeProvider("yandex")):
        outcome = _callback(query, cookie)
    assert outcome.provider == "yandex"


def test_identity_unknown_carries_provider(calls, monkeypatch):
    monkeypatch.setattr(service.storage, "find_identity_user", lambda **kw: None)
    fake = _fake_with_code()
    code = fake.issue_code(STATE)
    with registered(fake):
        outcome = service.handle_callback("yandex", {"state": STATE, "code": code}, STATE)
    assert outcome.audit_code == "oauth_identity_unknown"
    assert outcome.provider == "yandex"


def test_success_and_denial_carry_provider(calls, monkeypatch):
    found = {"user_id": 7, "user": _user()}
    monkeypatch.setattr(service.storage, "find_identity_user", lambda **kw: found)
    for user, expect_ticket in ((_user(), True), (_user(is_active=False), False)):
        found["user"] = user
        fake = _fake_with_code()
        with registered(fake):
            outcome = service.handle_callback(
                "yandex", {"state": STATE, "code": fake.issue_code(STATE)}, STATE,
            )
        assert outcome.provider == "yandex"
        assert ("ticket" in outcome.fragment) is expect_ticket


@pytest.mark.parametrize("path_name", ["yandex", "vk", "evil", "YANDEX"])
def test_unregistered_path_name_never_becomes_provider(calls, path_name):
    outcome = service.handle_callback(path_name, {"state": STATE, "code": "c"}, STATE)
    assert outcome.provider is None and outcome.audit_code is None


def test_complete_login_returns_ticket_provider(monkeypatch):
    monkeypatch.setattr(service.storage, "complete_login_atomic", lambda *a, **k: {
        "session_token": "t", "expires_at": None, "user": _user(), "provider": "yandex",
    })
    assert service.complete_login("ticket").provider == "yandex"
