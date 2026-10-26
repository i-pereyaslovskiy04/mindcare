"""
Подтверждение регистрации по ссылке из письма (unit, без БД).

Контракт POST /api/auth/register/confirm:
  {email, code}                  - шаг кода в исходной вкладке;
  {registration_reference, code} - ссылка /register/confirm#r=<uuid>.
Ровно один идентификатор, код - 6 ASCII-цифр, посторонние поля - 422.
Ошибки - {detail, code} со стабильным машинным кодом. Ответ по ссылке
содержит email, по email - нет. Rate limit по email сохраняется и тогда,
когда клиент email не передаёт. В журнал не попадают reference и код.

DB-уровень (новый UUID на каждый выпуск, замена, cooldown, параллельные
запросы) - tests/integration/test_registration_continuation.py.
"""

import json
from types import SimpleNamespace

import pytest
from pydantic import TypeAdapter, ValidationError

from app.audit.contracts import AuditResult, WriteState
from app.audit.registry import REGISTRY
from app.auth import routes, service, storage
from app.auth.errors import (
    OtpAttemptsExhaustedError, OtpExpiredError, OtpInvalidError,
    RegistrationReferenceInvalidError,
)
from app.auth.schemas import (
    RegisterConfirmByEmailRequest,
    RegisterConfirmByReferenceRequest,
    RegisterConfirmRequest,
    RegisterConfirmResponse,
)

REF = "8a62d590-71a1-4b17-90f7-4a5ff0c9d782"
EMAIL = "student@example.org"
CODE = "012345"

_adapter = TypeAdapter(RegisterConfirmRequest)


# ── Схема запроса ────────────────────────────────────────────────────────────

class TestRequestContract:
    def test_inline_email_and_code(self):
        body = _adapter.validate_python({"email": EMAIL, "code": CODE})
        assert isinstance(body, RegisterConfirmByEmailRequest)
        assert body.code == CODE                       # ведущий ноль сохранён

    def test_continuation_reference_and_code(self):
        body = _adapter.validate_python({"registration_reference": REF, "code": CODE})
        assert isinstance(body, RegisterConfirmByReferenceRequest)
        assert str(body.registration_reference) == REF
        assert body.code == CODE

    def test_both_identifiers_rejected(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python(
                {"email": EMAIL, "registration_reference": REF, "code": CODE},
            )

    def test_no_identifier_rejected(self):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"code": CODE})

    @pytest.mark.parametrize("ref", [
        "not-a-uuid", "", "8a62d590-71a1-1b17-90f7-4a5ff0c9d782",   # UUIDv1
        "00000000-0000-0000-0000-000000000000",
    ])
    def test_non_uuid4_reference_rejected(self, ref):
        with pytest.raises(ValidationError):
            _adapter.validate_python({"registration_reference": ref, "code": CODE})

    @pytest.mark.parametrize("code", [
        "12345", "1234567", "12a456", " 12345", "123456\n", "١٢٣٤٥٦", "", 123456,
    ])
    @pytest.mark.parametrize("ident", [{"email": EMAIL}, {"registration_reference": REF}])
    def test_code_must_be_six_ascii_digits(self, ident, code):
        with pytest.raises(ValidationError):
            _adapter.validate_python({**ident, "code": code})

    @pytest.mark.parametrize("ident", [{"email": EMAIL}, {"registration_reference": REF}])
    def test_extra_fields_forbidden(self, ident):
        with pytest.raises(ValidationError):
            _adapter.validate_python({**ident, "code": CODE, "password": "x"})

    def test_response_email_optional(self):
        inline = RegisterConfirmResponse(message="Регистрация завершена")
        assert inline.model_dump(exclude_none=True) == {"message": "Регистрация завершена"}


# ── Service: тип исключения → audit_code и машинный код клиента ──────────────

@pytest.mark.parametrize("exc,audit_code,error_code", [
    (RegistrationReferenceInvalidError("x"),
     "registration_reference_invalid", "registration_reference_invalid"),
    (OtpExpiredError("x"), "otp_expired", "otp_expired"),
    (OtpAttemptsExhaustedError("x"), "otp_invalid", "otp_attempts_exhausted"),
    (OtpInvalidError("x"), "otp_invalid", "otp_invalid"),
])
def test_service_maps_errors(monkeypatch, exc, audit_code, error_code):
    def _raise(**kw):
        raise exc
    monkeypatch.setattr(storage, "register_confirm_atomic", _raise)
    with pytest.raises(service.AuthError) as ei:
        service.register_confirm(code=CODE, registration_reference=REF)
    assert (ei.value.status_code, ei.value.audit_code, ei.value.error_code) == (
        400, audit_code, error_code,
    )


def test_service_passes_reference_not_email(monkeypatch):
    seen = {}

    def _ok(**kw):
        seen.update(kw)
        return {"id": 5, "email": EMAIL}
    monkeypatch.setattr(storage, "register_confirm_atomic", _ok)
    monkeypatch.setattr(service, "run_post_registration_actions", lambda *a, **k: None)
    service.register_confirm(code=CODE, registration_reference=REF)
    assert seen["email"] is None and seen["registration_reference"] == REF
    assert seen["code"] == CODE


def test_storage_requires_exactly_one_identifier():
    with pytest.raises(ValueError):
        storage.register_confirm_atomic(None, CODE, [])
    with pytest.raises(ValueError):
        storage.register_confirm_atomic(EMAIL, CODE, [], registration_reference=REF)


def test_reference_invalid_code_in_registry():
    spec = REGISTRY["registration_failed"]
    assert "registration_reference_invalid" in spec.allowed_failure_codes


# ── Route: ответ, rate limit, аудит ──────────────────────────────────────────

def _request():
    return SimpleNamespace(
        client=SimpleNamespace(host="192.0.2.10"), headers={"user-agent": "pytest"},
    )


@pytest.fixture
def route(monkeypatch):
    calls = SimpleNamespace(audit=[], limits=[], resolved=[])

    def _rec(**kw):
        calls.audit.append(kw)
        return AuditResult(WriteState.PERSISTED, kw.get("event", "?"))

    def _limit(action, request, email=None, *, by_ip=True):
        calls.limits.append((action, email, by_ip))

    def _resolve(ref):
        calls.resolved.append(ref)
        return calls.resolve_to
    calls.resolve_to = EMAIL
    monkeypatch.setattr(routes, "record_event", _rec)
    monkeypatch.setattr(routes, "_check_rate_limit", _limit)
    monkeypatch.setattr(routes.service, "resolve_registration_reference", _resolve)
    return calls


def _by_ref():
    return RegisterConfirmByReferenceRequest(registration_reference=REF, code=CODE)


def test_continuation_success_returns_email(route, monkeypatch):
    seen = {}

    def _ok(**kw):
        seen.update(kw)
        return {"id": 11, "email": EMAIL}
    monkeypatch.setattr(routes.service, "register_confirm", _ok)
    out = routes.register_confirm(body=_by_ref(), request=_request())
    assert out == {"message": "Регистрация завершена", "email": EMAIL}
    assert seen["email"] is None and seen["registration_reference"] == REF
    ok = route.audit[-1]
    assert ok["event"] == "registration_succeeded" and ok["user_email"] == EMAIL
    assert REF not in repr(route.audit) and CODE not in repr(route.audit)


def test_inline_success_has_no_email(route, monkeypatch):
    monkeypatch.setattr(routes.service, "register_confirm",
                        lambda **kw: {"id": 11, "email": EMAIL})
    out = routes.register_confirm(
        body=RegisterConfirmByEmailRequest(email=EMAIL, code=CODE), request=_request(),
    )
    assert out == {"message": "Регистрация завершена"}
    assert route.resolved == []
    assert route.limits == [("confirm", EMAIL, True)]


def test_continuation_rate_limit_by_ip_and_resolved_email(route, monkeypatch):
    monkeypatch.setattr(routes.service, "register_confirm",
                        lambda **kw: {"id": 11, "email": EMAIL})
    routes.register_confirm(body=_by_ref(), request=_request())
    # IP - сразу; email - по записи выпуска (без повторного учёта IP).
    assert route.limits == [("confirm", None, True), ("confirm", EMAIL, False)]


def test_rate_limit_counts_continuation_and_inline_in_one_email_bucket(monkeypatch):
    from app.core import rate_limit
    rate_limit._limiter.reset()
    monkeypatch.setattr(routes.service, "resolve_registration_reference", lambda r: EMAIL)
    monkeypatch.setattr(routes, "record_event", lambda **kw: None)
    monkeypatch.setattr(
        routes.service, "register_confirm",
        lambda **kw: (_ for _ in ()).throw(service.AuthError("x", 400, "otp_invalid")),
    )
    limit, _ = rate_limit.RULES["confirm:email"]
    try:
        for i in range(limit):
            req = SimpleNamespace(client=SimpleNamespace(host=f"198.51.100.{i}"), headers={})
            body = _by_ref() if i % 2 else RegisterConfirmByEmailRequest(email=EMAIL, code=CODE)
            assert routes.register_confirm(body=body, request=req).status_code == 400
        req = SimpleNamespace(client=SimpleNamespace(host="198.51.100.250"), headers={})
        with pytest.raises(routes.HTTPException) as ei:
            routes.register_confirm(body=_by_ref(), request=req)
        assert ei.value.status_code == 429
    finally:
        rate_limit._limiter.reset()


def test_unknown_reference_failure_without_email(route, monkeypatch):
    route.resolve_to = None

    def _fail(**kw):
        raise service.AuthError(
            storage.REGISTRATION_REFERENCE_INVALID_MESSAGE, 400,
            audit_code="registration_reference_invalid",
            error_code="registration_reference_invalid",
        )
    monkeypatch.setattr(routes.service, "register_confirm", _fail)
    resp = routes.register_confirm(body=_by_ref(), request=_request())
    assert resp.status_code == 400
    assert json.loads(resp.body) == {
        "detail": storage.REGISTRATION_REFERENCE_INVALID_MESSAGE,
        "code": "registration_reference_invalid",
    }
    assert route.limits == [("confirm", None, True)]      # email неизвестен
    fail = route.audit[-1]
    assert fail["event"] == "registration_failed"
    assert fail["failure_reason_code"] == "registration_reference_invalid"
    assert fail["user_email"] is None
    assert REF not in repr(route.audit) and CODE not in repr(route.audit)


@pytest.mark.parametrize("error_code", [
    "otp_invalid", "otp_expired", "otp_attempts_exhausted",
])
def test_known_reference_failure_has_code_and_email_in_audit(route, monkeypatch, error_code):
    def _fail(**kw):
        raise service.AuthError("Текст", 400, audit_code="otp_invalid", error_code=error_code)
    monkeypatch.setattr(routes.service, "register_confirm", _fail)
    resp = routes.register_confirm(body=_by_ref(), request=_request())
    assert json.loads(resp.body) == {"detail": "Текст", "code": error_code}
    assert route.audit[-1]["user_email"] == EMAIL
    assert REF not in repr(route.audit)


def test_failure_without_error_code_keeps_plain_detail(route, monkeypatch):
    def _fail(**kw):
        raise service.AuthError("Email уже зарегистрирован", 409,
                                audit_code="email_already_exists")
    monkeypatch.setattr(routes.service, "register_confirm", _fail)
    resp = routes.register_confirm(body=_by_ref(), request=_request())
    assert resp.status_code == 409
    assert json.loads(resp.body) == {"detail": "Email уже зарегистрирован"}
