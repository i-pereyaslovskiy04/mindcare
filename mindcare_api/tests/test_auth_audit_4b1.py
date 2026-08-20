"""
Stage 4B-1 — no-DB unit-тесты переноса auth-событий на record_event() и stable
failure-code contract. Service-mapping через mock storage; route-mapping через spy
record_event + fake request. Реальная БД не используется.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.auth import routes, service, storage
from app.auth.errors import OtpExpiredError, OtpInvalidError
from app.auth.schemas import (
    ChangePasswordRequest, LoginRequest, PasswordResetConfirmRequest,
    RegisterConfirmRequest, RegisterInitRequest, PasswordResetInitRequest,
)
from app.auth.security import hash_session_token
from app.audit import validation as audit_validation
from app.audit.contracts import AuditResult, RequestContext, WriteState
from app.email_domains.errors import EmailDomainNotAllowedError


def _raiser(exc):
    def _fn(*a, **k):
        raise exc
    return _fn


def _fake_request(ip="192.0.2.10", ua="pytest-agent"):
    return SimpleNamespace(
        client=SimpleNamespace(host=ip),
        headers={"user-agent": ua},
    )


# ── Typed OTP errors — подклассы ValueError (обратная совместимость) ──────────

def test_otp_errors_are_valueerror_subclasses():
    assert issubclass(OtpInvalidError, ValueError)
    assert issubclass(OtpExpiredError, ValueError)


# ── Service: exception → audit_code mapping (по типу, не по тексту) ────────────

@pytest.mark.parametrize("exc,expected", [
    (OtpExpiredError("x"), "otp_expired"),
    (OtpInvalidError("x"), "otp_invalid"),
    (EmailDomainNotAllowedError("x"), "domain_not_allowed"),
    (storage.RegistrationDataError("x"), "internal_error"),
])
def test_register_confirm_audit_code(monkeypatch, exc, expected):
    monkeypatch.setattr(storage, "register_confirm_atomic", _raiser(exc))
    with pytest.raises(service.AuthError) as ei:
        service.register_confirm(email="a@b.com", code="123456")
    assert ei.value.audit_code == expected
    assert ei.value.audit_code is not None


@pytest.mark.parametrize("exc,expected", [
    (OtpExpiredError("x"), "otp_expired"),
    (OtpInvalidError("x"), "otp_invalid"),
    (storage.UserNotFoundError("x"), "user_not_found"),
])
def test_password_reset_confirm_audit_code(monkeypatch, exc, expected):
    monkeypatch.setattr(storage, "password_reset_confirm_atomic", _raiser(exc))
    with pytest.raises(service.AuthError) as ei:
        service.password_reset_confirm(
            email="a@b.com", code="123456", new_password="Secret123",
        )
    assert ei.value.audit_code == expected


def test_register_confirm_generic_valueerror_not_masked(monkeypatch):
    # Неожиданный (не типизированный OTP) ValueError НЕ превращается в
    # AuthError/otp_invalid: распространяется как есть → внутренняя ошибка.
    monkeypatch.setattr(storage, "register_confirm_atomic",
                        _raiser(ValueError("unexpected")))
    with pytest.raises(ValueError) as ei:
        service.register_confirm(email="a@b.com", code="123456")
    assert not isinstance(ei.value, service.AuthError)


def test_password_reset_generic_valueerror_not_masked(monkeypatch):
    monkeypatch.setattr(storage, "password_reset_confirm_atomic",
                        _raiser(ValueError("unexpected")))
    with pytest.raises(ValueError) as ei:
        service.password_reset_confirm(
            email="a@b.com", code="123456", new_password="Secret123",
        )
    assert not isinstance(ei.value, service.AuthError)


def test_register_confirm_registration_data_error_safe_message(monkeypatch):
    # Внутреннее сообщение storage-исключения называет роль/таблицу/consent-
    # политику — оно НЕ должно долетать до HTTP-клиента как есть.
    internal_message = (
        "Политика 'privacy_policy' не найдена в БД (consent table roles seed)."
        " Обратитесь к администратору."
    )
    monkeypatch.setattr(
        storage, "register_confirm_atomic",
        _raiser(storage.RegistrationDataError(internal_message)),
    )
    with pytest.raises(service.AuthError) as ei:
        service.register_confirm(email="a@b.com", code="123456")

    assert ei.value.status_code == 500
    assert ei.value.audit_code == "internal_error"
    assert internal_message not in ei.value.message
    lowered = ei.value.message.lower()
    for leaked_term in (
        "role", "роль", "table", "таблиц", "seed", "consent",
        "policy", "политик", "database", "бд",
    ):
        assert leaked_term not in lowered


def test_password_reset_policy_code():
    with pytest.raises(service.AuthError) as ei:
        service.password_reset_confirm(email="a@b.com", code="1", new_password="short")
    assert ei.value.audit_code == "password_policy"


def test_failed_login_audit_code(monkeypatch):
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: None)
    with pytest.raises(service.AuthError) as ei:
        service.authenticate_user("a@b.com", "whatever")
    assert ei.value.audit_code == "invalid_credentials"


# ── Login role invariant (fail-closed) ───────────────────────────────────────

@pytest.mark.parametrize("roles,role", [
    ([], None),
    ([], "student"),
    (["student"], None),
    (["student"], "admin"),   # role ∉ roles
    (["student"], 123),       # role — не строка
    (["bogus"], "bogus"),     # role ∈ roles, но не каноническая (не в ROLE_PRIORITY)
])
def test_login_role_invariant_blocks_session(monkeypatch, roles, role):
    called = {"last_login": False}
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: {
        "id": 5, "email": "u@e.com", "hashed_password": "h",
        "roles": roles, "role": role,
    })
    monkeypatch.setattr(service, "_verify", lambda p, h: True)
    monkeypatch.setattr(
        storage, "update_last_login",
        lambda uid: called.__setitem__("last_login", True),
    )
    with pytest.raises(service.AuthError) as ei:
        service.authenticate_user("u@e.com", "pw")
    # ADR-018: штатный доменный отказ, а не внутренняя авария
    assert ei.value.status_code == 403
    assert ei.value.audit_code == "no_active_roles"
    assert called["last_login"] is False          # сессия/last_login не создаётся
    # безопасное сообщение — без ролей/DB-деталей
    assert "student" not in ei.value.message and "admin" not in ei.value.message


def test_no_active_roles_is_not_internal_error(monkeypatch):
    """`internal_error` остаётся только за настоящими внутренними сбоями.

    Иначе штатный отказ неотличим от аварии и шумит в мониторинге.
    """
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: {
        "id": 5, "email": "u@e.com", "hashed_password": "h",
        "roles": [], "role": None,
    })
    monkeypatch.setattr(service, "_verify", lambda p, h: True)
    monkeypatch.setattr(storage, "update_last_login", lambda uid: None)
    with pytest.raises(service.AuthError) as ei:
        service.authenticate_user("u@e.com", "pw")
    assert ei.value.audit_code != "internal_error"
    assert ei.value.status_code != 500


def test_wrong_password_keeps_invalid_credentials(monkeypatch):
    """Новый код не подменяет отказ по паролю у пользователя С ролями."""
    called = {"last_login": False}
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: {
        "id": 5, "email": "u@e.com", "hashed_password": "h",
        "roles": ["student"], "role": "student",
    })
    monkeypatch.setattr(service, "_verify", lambda p, h: False)
    monkeypatch.setattr(
        storage, "update_last_login",
        lambda uid: called.__setitem__("last_login", True),
    )
    with pytest.raises(service.AuthError) as ei:
        service.authenticate_user("u@e.com", "wrong")
    assert ei.value.status_code == 401
    assert ei.value.audit_code == "invalid_credentials"
    assert called["last_login"] is False


def test_login_role_invariant_ok(monkeypatch):
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: {
        "id": 5, "email": "u@e.com", "hashed_password": "h",
        "roles": ["student"], "role": "student",
    })
    monkeypatch.setattr(service, "_verify", lambda p, h: True)
    monkeypatch.setattr(storage, "update_last_login", lambda uid: None)
    user = service.authenticate_user("u@e.com", "pw")
    assert user["role"] == "student"


# ── Route-level record_event mapping (spy + fake request) ─────────────────────

def _spy(monkeypatch):
    calls = []

    def _rec(**kw):
        calls.append(kw)
        return AuditResult(WriteState.PERSISTED, kw.get("event", "?"))
    monkeypatch.setattr(routes, "record_event", _rec)
    monkeypatch.setattr(routes, "_check_rate_limit", lambda *a, **k: None)
    return calls


def test_route_login_success_mapping(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(routes.service, "authenticate_user", lambda email, password: {
        "id": 7, "email": "u@e.com", "role": "student", "roles": ["student"],
    })
    monkeypatch.setattr(routes.service, "create_session",
                        lambda **k: ("rawtok123", None))
    routes.login(body=LoginRequest(email="u@e.com", password="Secret123"),
                 request=_fake_request())
    kw = calls[-1]
    assert kw["event"] == "login"
    assert kw["actor"].kind == "user" and kw["actor"].user_id == 7
    assert kw["actor"].role == "student"
    assert kw["user_email"] == "u@e.com"
    assert kw["context"].session_id_hash == hash_session_token("rawtok123")
    blob = repr(kw)
    assert "rawtok123" not in blob and "Secret123" not in blob  # raw token/password не переданы


def test_route_login_soft_failed_does_not_break(monkeypatch):
    monkeypatch.setattr(routes, "_check_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(routes, "record_event",
                        lambda **kw: AuditResult(WriteState.SOFT_FAILED, "login", "X"))
    monkeypatch.setattr(routes.service, "authenticate_user", lambda email, password: {
        "id": 7, "email": "u@e.com", "role": "student", "roles": ["student"],
    })
    monkeypatch.setattr(routes.service, "create_session", lambda **k: ("t", None))
    out = routes.login(body=LoginRequest(email="u@e.com", password="Secret123"),
                       request=_fake_request())
    assert out["session_token"] == "t"            # SOFT_FAILED не ломает HTTP-результат


def test_route_failed_login_mapping(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(
        routes.service, "authenticate_user",
        _raiser(service.AuthError("Неверный email или пароль", 401,
                                  audit_code="invalid_credentials")),
    )
    with pytest.raises(HTTPException):
        routes.login(body=LoginRequest(email="u@e.com", password="bad"),
                     request=_fake_request())
    kw = calls[-1]
    assert kw["event"] == "failed_login" and kw["actor"].kind == "anonymous"
    assert kw["failure_reason_code"] == "invalid_credentials"
    assert kw["user_email"] == "u@e.com"
    assert "Неверный" not in repr(kw)             # raw message не передан facade


def test_route_logout_no_user_email(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(routes.service, "terminate_session", lambda t: None)
    routes.logout(request=_fake_request(), token="rawtok",
                  current_user={"id": 9, "role": "admin", "email": "a@e.com"})
    kw = calls[-1]
    assert kw["event"] == "logout" and kw["actor"].user_id == 9
    assert kw.get("user_email") is None           # user_email НЕ передаётся
    assert kw["context"].session_id_hash == hash_session_token("rawtok")
    assert "rawtok" not in repr(kw)


def test_route_password_change_no_user_email(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(routes.service, "change_password", lambda **k: None)
    routes.change_password(
        body=ChangePasswordRequest(
            current_password="OldPass12", new_password="NewPass123",
            new_password_confirm="NewPass123",
        ),
        request=_fake_request(),
        current_user={"id": 3, "role": "psychologist", "email": "p@e.com"},
    )
    kw = calls[-1]
    assert kw["event"] == "password_change" and kw["actor"].role == "psychologist"
    assert kw.get("user_email") is None
    assert "NewPass123" not in repr(kw) and "OldPass12" not in repr(kw)


def test_route_register_confirm_success(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(routes.service, "register_confirm",
                        lambda **k: {"id": 11, "email": "n@e.com"})
    routes.register_confirm(
        body=RegisterConfirmRequest(email="n@e.com", code="123456"),
        request=_fake_request(),
    )
    kw = calls[-1]
    assert kw["event"] == "registration_succeeded"
    assert kw["actor"].user_id == 11 and kw["actor"].role == "student"
    assert kw["user_email"] == "n@e.com"


def test_route_register_confirm_failure(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(
        routes.service, "register_confirm",
        _raiser(service.AuthError("Срок действия кода истёк", 400,
                                  audit_code="otp_expired")),
    )
    with pytest.raises(HTTPException):
        routes.register_confirm(
            body=RegisterConfirmRequest(email="n@e.com", code="000000"),
            request=_fake_request(),
        )
    kw = calls[-1]
    assert kw["event"] == "registration_failed" and kw["actor"].kind == "anonymous"
    assert kw["failure_reason_code"] == "otp_expired"
    assert kw["user_email"] == "n@e.com"


def test_route_password_reset_success_and_failure(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(routes.service, "password_reset_confirm", lambda **k: None)
    routes.password_reset_confirm(
        body=PasswordResetConfirmRequest(
            email="u@e.com", code="123456", new_password="NewPass123",
        ),
        request=_fake_request(),
    )
    assert calls[-1]["event"] == "password_reset"
    assert calls[-1]["actor"].kind == "anonymous"
    assert calls[-1].get("failure_reason_code") is None

    monkeypatch.setattr(
        routes.service, "password_reset_confirm",
        _raiser(service.AuthError("bad", 400, audit_code="otp_invalid")),
    )
    with pytest.raises(HTTPException):
        routes.password_reset_confirm(
            body=PasswordResetConfirmRequest(
                email="u@e.com", code="000000", new_password="NewPass123",
            ),
            request=_fake_request(),
        )
    assert calls[-1]["event"] == "password_reset"
    assert calls[-1]["failure_reason_code"] == "otp_invalid"


# ── Email max_length=255 на всех auth request-схемах ───────────────────────────

_EMAIL_SCHEMAS = [
    (RegisterInitRequest, {"name": "Integ User", "password": "Secret123"}),
    (RegisterConfirmRequest, {"code": "123456"}),
    (LoginRequest, {"password": "Secret123"}),
    (PasswordResetInitRequest, {}),
    (PasswordResetConfirmRequest, {"code": "123456", "new_password": "Secret123"}),
]


@pytest.mark.parametrize("model_cls,extra_fields", _EMAIL_SCHEMAS)
def test_auth_schema_email_has_max_length_255(model_cls, extra_fields):
    field = model_cls.model_fields["email"]
    assert field.metadata, f"{model_cls.__name__}.email has no constraints"
    max_lens = [
        c.max_length for c in field.metadata if hasattr(c, "max_length")
    ]
    assert 255 in max_lens, f"{model_cls.__name__}.email missing max_length=255"


@pytest.mark.parametrize("model_cls,extra_fields", _EMAIL_SCHEMAS)
def test_auth_schema_email_accepts_normal_address(model_cls, extra_fields):
    model_cls(email="normal.user@example.com", **extra_fields)


@pytest.mark.parametrize("model_cls,extra_fields", _EMAIL_SCHEMAS)
def test_auth_schema_email_rejects_too_long(model_cls, extra_fields):
    too_long_local = "a" * 250
    too_long_email = f"{too_long_local}@example.com"     # > 255 символов
    assert len(too_long_email) > 255
    with pytest.raises(Exception) as ei:
        model_cls(email=too_long_email, **extra_fields)
    assert "ValidationError" in type(ei.value).__name__


# ── Point 3: недоверенный User-Agent / IP не ломает audit-контекст ────────────

_BAD_UA_LONG = "x" * 600                 # > 512 → facade отверг бы
_BAD_UA_CTRL = "Mozilla\x00\x1f evil"    # control chars → facade отверг бы


def test_raw_bad_user_agent_would_fail_facade():
    # Контроль: несанитизированный UA действительно отвергается facade — поэтому
    # helper обязателен (иначе успешная бизнес-операция завершилась бы 500).
    with pytest.raises(audit_validation.AuditError):
        audit_validation.validate_context(RequestContext(user_agent=_BAD_UA_LONG))
    with pytest.raises(audit_validation.AuditError):
        audit_validation.validate_context(RequestContext(user_agent=_BAD_UA_CTRL))


def test_audit_context_sanitizes_bad_user_agent():
    for bad in (_BAD_UA_LONG, _BAD_UA_CTRL):
        ctx = routes._audit_context(_fake_request(ua=bad))
        assert ctx.user_agent is None
        audit_validation.validate_context(ctx)   # facade больше НЕ бросает


def test_audit_context_sanitizes_bad_ip():
    ctx = routes._audit_context(_fake_request(ip="testclient"))
    assert ctx.ip_address is None
    audit_validation.validate_context(ctx)


def test_route_login_bad_user_agent_not_500(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(routes.service, "authenticate_user", lambda email, password: {
        "id": 7, "email": "u@e.com", "role": "student", "roles": ["student"],
    })
    monkeypatch.setattr(routes.service, "create_session",
                        lambda **k: ("tok", None))
    out = routes.login(body=LoginRequest(email="u@e.com", password="Secret123"),
                       request=_fake_request(ua=_BAD_UA_LONG, ip="testclient"))
    assert out["session_token"] == "tok"           # успешная операция не падает
    kw = calls[-1]
    assert kw["event"] == "login"
    assert kw["context"].user_agent is None         # недоверенный UA не в журнале
    assert kw["context"].ip_address is None          # невалидный IP не в журнале
    # session hash при этом по-прежнему передаётся (raw token — нет)
    assert kw["context"].session_id_hash == hash_session_token("tok")


def test_route_failed_login_bad_user_agent_keeps_http(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(
        routes.service, "authenticate_user",
        _raiser(service.AuthError("Неверный email или пароль", 401,
                                  audit_code="invalid_credentials")),
    )
    with pytest.raises(HTTPException) as ei:
        routes.login(body=LoginRequest(email="u@e.com", password="bad"),
                     request=_fake_request(ua=_BAD_UA_CTRL))
    assert ei.value.status_code == 401              # исходный 401, не 500
    assert calls[-1]["event"] == "failed_login"
    assert calls[-1]["context"].user_agent is None


# ── Static: миграция убрала log_auth_event из auth/routes.py (Stage 4B-1+4B-4) ─

def test_auth_routes_no_log_auth_event_for_migrated():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app" / "auth" / "routes.py"
           ).read_text(encoding="utf-8")
    assert "record_event(" in src
    # Stage 4B-4: profile_update (последний оставшийся log_auth_event в этом
    # файле) перенесён на record_event("profile_updated", ...) внутри
    # app/auth/storage.py::update_profile_atomic — ни одного log_auth_event
    # не остаётся в routes.py.
    assert src.count("log_auth_event(") == 0
    # Старые auth log_auth_event event-строки больше не используются как его аргумент.
    assert 'event="register"' not in src          # → registration_succeeded/failed
