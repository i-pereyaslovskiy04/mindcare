"""
Stage Social Auth 4 — unit-тесты регистрации через провайдера без БД: схемы
запросов (init — только ticket; consent — на confirm), consent gate в service,
email/имя провайдера для registration-ticket, digest-ключ лимитера, сбой
доставки письма. Атомарность и гонки — tests/integration/test_oauth_registration_*.
"""
import hashlib

import pytest
from pydantic import ValidationError

from app.core import rate_limit
from app.oauth import service
from app.oauth.errors import OAuthRegistrationError, OAuthTicketInvalidError
from app.oauth.schemas import (
    OAuthRegistrationConfirmRequest, OAuthRegistrationInitRequest,
)

TICKET = "t" * 43
EMAIL = "integ_x@yandex.ru"


def _confirm_body(**over):
    body = {"ticket": TICKET, "code": "012345", "consent_accepted": True}
    body.update(over)
    return body


@pytest.fixture
def issued(monkeypatch):
    """Фиксирует вызовы storage и отправку письма."""
    calls = {"issue": [], "sent": [], "confirm": []}

    def _issue(ticket_hash):
        calls["issue"].append(ticket_hash)
        return "123456", EMAIL

    def _complete(ticket_hash, code, **kwargs):
        calls["confirm"].append((ticket_hash, code))
        raise AssertionError("must not be reached")

    monkeypatch.setattr(service.storage, "issue_registration_otp", _issue)
    monkeypatch.setattr(service.storage, "complete_registration_atomic", _complete)
    monkeypatch.setattr(
        "app.services.email_service.send_registration_otp",
        lambda to, code: calls["sent"].append((to, code)),
    )
    return calls


# ── схемы ────────────────────────────────────────────────────────────────────

def test_init_schema_accepts_only_ticket():
    assert OAuthRegistrationInitRequest(ticket=TICKET).ticket == TICKET


@pytest.mark.parametrize("extra", [
    "name", "email", "consent_accepted", "provider", "subject", "provider_subject",
    "user_id", "password", "role",
])
def test_init_schema_forbids_client_supplied_fields(extra):
    with pytest.raises(ValidationError):
        OAuthRegistrationInitRequest(ticket=TICKET, **{extra: "x"})


@pytest.mark.parametrize("ticket", ["", "x" * 129])
def test_init_schema_ticket_bounds(ticket):
    with pytest.raises(ValidationError):
        OAuthRegistrationInitRequest(ticket=ticket)


def test_confirm_schema_accepts_literal_true_only():
    assert OAuthRegistrationConfirmRequest(**_confirm_body()).consent_accepted is True
    for bad in (False, 1, "true", "yes", None):
        with pytest.raises(ValidationError):
            OAuthRegistrationConfirmRequest(**_confirm_body(consent_accepted=bad))
    body = _confirm_body()
    del body["consent_accepted"]
    with pytest.raises(ValidationError):
        OAuthRegistrationConfirmRequest(**body)


@pytest.mark.parametrize("code", ["12345", "1234567", "12345a", "", " 123456", "１２３４５６"])
def test_confirm_schema_requires_six_ascii_digits(code):
    with pytest.raises(ValidationError):
        OAuthRegistrationConfirmRequest(**_confirm_body(code=code))


@pytest.mark.parametrize("extra", ["email", "name", "provider", "subject", "password"])
def test_confirm_schema_forbids_extra(extra):
    assert OAuthRegistrationConfirmRequest(**_confirm_body()).code == "012345"
    with pytest.raises(ValidationError):
        OAuthRegistrationConfirmRequest(**_confirm_body(**{extra: "x"}))


# ── service: init ────────────────────────────────────────────────────────────

def test_init_hashes_ticket_sends_to_ticket_email_and_masks(issued):
    masked = service.registration_init(TICKET)
    assert issued["issue"] == [hashlib.sha256(TICKET.encode()).hexdigest()]
    assert issued["issue"][0] != TICKET
    assert issued["sent"] == [(EMAIL, "123456")]       # письмо — после storage
    assert masked == "i***@yandex.ru" and EMAIL not in masked


@pytest.mark.parametrize("ticket", ["", None])
def test_empty_ticket_is_invalid_without_storage(issued, ticket):
    with pytest.raises(OAuthTicketInvalidError):
        service.registration_init(ticket)
    with pytest.raises(OAuthTicketInvalidError):
        service.registration_confirm(ticket, "123456", consent_accepted=True)
    assert issued["issue"] == [] and issued["confirm"] == []


def test_email_delivery_failure_is_safe_error(issued, monkeypatch, caplog):
    def _smtp_down(to, code):
        raise RuntimeError("SMTP SECRET detail 123456")

    monkeypatch.setattr("app.services.email_service.send_registration_otp", _smtp_down)
    with pytest.raises(OAuthRegistrationError) as ei:
        service.registration_init(TICKET)
    assert ei.value.code == "email_delivery_failed" and ei.value.status_code == 500
    assert "SECRET" not in ei.value.message
    assert ei.value.__cause__ is None and ei.value.__context__ is None
    assert len(issued["issue"]) == 1                  # состояние БД уже закоммичено
    assert "SECRET" not in caplog.text and "123456" not in caplog.text
    assert EMAIL not in caplog.text                   # email маскируется


# ── service: consent gate на confirm ─────────────────────────────────────────

@pytest.mark.parametrize("consent", [False, None, 1, "true"])
def test_consent_gate_blocks_confirm_before_storage(issued, consent):
    with pytest.raises(OAuthRegistrationError) as ei:
        service.registration_confirm(TICKET, "123456", consent_accepted=consent)
    assert ei.value.code == "consent_required" and ei.value.status_code == 422
    assert ei.value.audit_code is None
    assert issued["confirm"] == []                    # OTP не проверяется, ничего не создаётся


def test_storage_error_propagates_unchanged(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(service.storage, "complete_registration_atomic", _boom)
    with pytest.raises(RuntimeError, match="db down"):
        service.registration_confirm(TICKET, "123456", consent_accepted=True)


# ── email и имя провайдера для registration-ticket ───────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("  Ivan.Petrov@Yandex.RU ", "ivan.petrov@yandex.ru"),
    ("student@donnu.ru", "student@donnu.ru"),
])
def test_provider_email_normalized(raw, expected):
    assert service._provider_email(raw) == expected


@pytest.mark.parametrize("raw", [
    None, "", "   ", 42, "no-at-sign", "a@@b.ru", "@yandex.ru", "user@",
    "us er@yandex.ru", "user\x00@yandex.ru", "a" * 250 + "@yandex.ru",
])
def test_provider_email_invalid_is_none(raw):
    assert service._provider_email(raw) is None


@pytest.mark.parametrize("suggested,email,expected", [
    ("Иван  Петров", "ivan@yandex.ru", "Иван Петров"),
    (None, "ivan.petrov@yandex.ru", "ivan.petrov"),
    ("я", "ivan@yandex.ru", "ivan"),                      # слишком короткое → email
    ("Ив\x00ан", "ivan@yandex.ru", "ivan"),
    (None, "i@yandex.ru", "i@yandex.ru"),                 # крайний случай — сам email
])
def test_initial_name_fallbacks(suggested, email, expected):
    assert service._initial_name(suggested, email) == expected


# ── лимитер: только полный SHA-256 digest ────────────────────────────────────

@pytest.fixture
def clean_limiter():
    rate_limit.reset()
    yield
    rate_limit.reset()


@pytest.mark.parametrize("action", ["oauth_registration_init", "oauth_registration_confirm"])
def test_ticket_dimension_accepts_only_sha256_digest(clean_limiter, action):
    digest = hashlib.sha256(TICKET.encode()).hexdigest()
    rate_limit.enforce(action, ip="198.51.100.7", ticket_digest=digest)
    keys = list(rate_limit._limiter._hits)
    assert f"{action}:ticket:{digest}" in keys
    for raw in (TICKET, digest[:16], digest.upper(), digest + "0"):
        with pytest.raises(ValueError):
            rate_limit.enforce(action, ticket_digest=raw)
    assert all(TICKET not in key for key in rate_limit._limiter._hits)


def test_registration_rate_limit_rules():
    assert "oauth_registration_init:email" not in rate_limit.RULES
    assert rate_limit.RULES["oauth_registration_init:ip"] == (20, 900)
    assert rate_limit.RULES["oauth_registration_init:ticket"] == (3, 900)
    assert rate_limit.RULES["oauth_registration_confirm:ip"] == (30, 600)
    assert rate_limit.RULES["oauth_registration_confirm:ticket"] == (10, 600)


def test_ticket_limit_blocks_eleventh_attempt(clean_limiter):
    digest = hashlib.sha256(TICKET.encode()).hexdigest()
    for _ in range(10):
        rate_limit.enforce("oauth_registration_confirm", ticket_digest=digest)
    with pytest.raises(rate_limit.RateLimitExceeded) as ei:
        rate_limit.enforce("oauth_registration_confirm", ticket_digest=digest)
    assert digest not in str(ei.value)                # digest не уходит в исключение
