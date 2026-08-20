"""
Stage 4A — no-DB тесты валидации actor/target/outcome/metadata/context/email.
"""
import pytest

from app.audit import validation
from app.audit.contracts import Actor, AuditError, Outcome, RequestContext, Target
from app.audit.registry import REGISTRY

ROLE = REGISTRY["admin_role_add"]          # USER_REQUIRED {admin}, target user
LOGIN = REGISTRY["login"]                   # USER_REQUIRED all roles
FAILED_LOGIN = REGISTRY["failed_login"]     # ANONYMOUS_ONLY, FAILURE
SYS = REGISTRY["system_conversation_created"]  # SYSTEM
ATTACH = REGISTRY["chat_attachment_uploaded"]  # metadata file_size/mime_type
PROFILE = REGISTRY["profile_updated"]


# ── Actor ──────────────────────────────────────────────────────────────────

def test_user_required_needs_user():
    with pytest.raises(AuditError):
        validation.validate_actor(ROLE, Actor.anonymous())
    with pytest.raises(AuditError):
        validation.validate_actor(ROLE, Actor.system())
    validation.validate_actor(ROLE, Actor.user(5, "admin"))   # ok


def test_wrong_role_rejected():
    with pytest.raises(AuditError):
        validation.validate_actor(ROLE, Actor.user(5, "student"))  # admin-event от student


def test_bool_user_id_rejected():
    with pytest.raises(AuditError):
        validation.validate_actor(LOGIN, Actor.user(True, "admin"))
    with pytest.raises(AuditError):
        validation.validate_actor(LOGIN, Actor.user(0, "admin"))
    with pytest.raises(AuditError):
        validation.validate_actor(LOGIN, Actor.user(-1, "admin"))


def test_auth_log_accepts_user_actor_without_active_role():
    """ADR-018: аккаунт без активных ролей всё ещё аутентифицируется.

    auth_log роль актора не хранит, поэтому login/logout такого пользователя
    обязаны проходить валидацию, а не превращаться в 500 на живом входе.
    """
    validation.validate_actor(LOGIN, Actor.user(5, None))
    validation.validate_actor(REGISTRY["logout"], Actor.user(5, None))


def test_audit_log_still_requires_role():
    """Послабление строго ограничено AUTH_LOG: audit_log пишет user_role."""
    with pytest.raises(AuditError):
        validation.validate_actor(ROLE, Actor.user(5, None))
    with pytest.raises(AuditError):
        validation.validate_actor(PROFILE, Actor.user(5, None))


def test_auth_log_still_rejects_invalid_role_string():
    """Послабление касается ТОЛЬКО None, а не произвольной строки роли."""
    with pytest.raises(AuditError):
        validation.validate_actor(LOGIN, Actor.user(5, "not_a_role"))
    with pytest.raises(AuditError):
        validation.validate_actor(LOGIN, Actor.user(5, ""))


def test_anonymous_only_rejects_user():
    with pytest.raises(AuditError):
        validation.validate_actor(FAILED_LOGIN, Actor.user(1, "admin"))
    validation.validate_actor(FAILED_LOGIN, Actor.anonymous())    # ok


def test_system_only_accepts_system():
    with pytest.raises(AuditError):
        validation.validate_actor(SYS, Actor.user(1, "admin"))
    validation.validate_actor(SYS, Actor.system())               # ok


# ── Target ─────────────────────────────────────────────────────────────────

def test_target_required_and_type_match():
    with pytest.raises(AuditError):
        validation.validate_target(ROLE, None)
    with pytest.raises(AuditError):
        validation.validate_target(ROLE, Target("wrong_type", 1))
    with pytest.raises(AuditError):
        validation.validate_target(ROLE, Target("user", True))    # bool id
    validation.validate_target(ROLE, Target("user", 7))


def test_target_forbidden_for_auth():
    with pytest.raises(AuditError):
        validation.validate_target(LOGIN, Target("user", 1))
    validation.validate_target(LOGIN, None)


# ── Outcome / failure code ──────────────────────────────────────────────────

def test_success_forbids_code():
    with pytest.raises(AuditError):
        validation.validate_outcome(LOGIN, Outcome.SUCCESS, "x")
    validation.validate_outcome(LOGIN, Outcome.SUCCESS, None)


def test_failure_requires_registered_code():
    with pytest.raises(AuditError):
        validation.validate_outcome(FAILED_LOGIN, Outcome.FAILURE, None)
    with pytest.raises(AuditError):
        validation.validate_outcome(FAILED_LOGIN, Outcome.FAILURE, "not_registered")
    validation.validate_outcome(FAILED_LOGIN, Outcome.FAILURE, "invalid_credentials")


def test_failed_login_accepts_no_active_roles_reason():
    """ADR-018: отказ по отсутствию активных ролей — исход того же события."""
    validation.validate_outcome(FAILED_LOGIN, Outcome.FAILURE, "no_active_roles")
    assert FAILED_LOGIN.allowed_failure_codes == frozenset({
        "invalid_credentials", "no_active_roles", "internal_error",
    })


def test_no_active_roles_reason_is_not_leaked_to_other_events():
    """Код не расползается по другим auth-событиям."""
    for name in ("registration_failed", "password_reset"):
        assert "no_active_roles" not in REGISTRY[name].allowed_failure_codes


def test_disallowed_outcome():
    with pytest.raises(AuditError):
        validation.validate_outcome(LOGIN, Outcome.FAILURE, "x")


# ── Metadata ─────────────────────────────────────────────────────────────────

def test_unknown_metadata_key():
    with pytest.raises(AuditError):
        validation.validate_metadata(ROLE, {"nope": []})


def test_role_metadata_enum_and_system_rejected():
    ok = validation.validate_metadata(ROLE, {"added": ["supervisor"]})
    assert ok == {"added": ["supervisor"]}
    with pytest.raises(AuditError):
        validation.validate_metadata(ROLE, {"added": ["system"]})   # system не USER_ROLE


def test_attachment_int_bounds_and_bool_rejected():
    ok = validation.validate_metadata(ATTACH, {"file_size": 100, "mime_type": "image/png"})
    assert ok == {"file_size": 100, "mime_type": "image/png"}
    with pytest.raises(AuditError):
        validation.validate_metadata(ATTACH, {"file_size": True})   # bool не int
    with pytest.raises(AuditError):
        validation.validate_metadata(ATTACH, {"file_size": -1})
    with pytest.raises(AuditError):
        validation.validate_metadata(ATTACH, {"mime_type": "not a mime"})


def test_metadata_deep_copy_isolation():
    src = {"added": ["supervisor"]}
    out = validation.validate_metadata(ROLE, src)
    src["added"].append("admin")            # мутируем исходный список
    assert out["added"] == ["supervisor"]   # результат не затронут


def test_denylist_key_scan_positive_and_negative():
    assert validation.is_denylisted_key("full_name")
    assert validation.is_denylisted_key("session_token")
    assert validation.is_denylisted_key("userEmail")
    assert validation.is_denylisted_key("original_filename")
    assert validation.is_denylisted_key("error_message")
    # безопасные технические ключи не должны срабатывать
    assert not validation.is_denylisted_key("role_name")
    assert not validation.is_denylisted_key("field_name")
    assert not validation.is_denylisted_key("event_name")
    assert not validation.is_denylisted_key("mime_type")
    assert not validation.is_denylisted_key("conversation_id")


def test_profile_fields_enum():
    ok = validation.validate_metadata(PROFILE, {"fields": ["full_name", "phone"]})
    assert ok == {"fields": ["full_name", "phone"]}
    with pytest.raises(AuditError):
        validation.validate_metadata(PROFILE, {"fields": ["email"]})


# ── Context ──────────────────────────────────────────────────────────────────

def test_context_validation():
    validation.validate_context(RequestContext(
        ip_address="192.0.2.1", user_agent="Mozilla",
        session_id_hash="a" * 64, request_path="/api/x", request_method="POST",
    ))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(ip_address="not-an-ip"))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(user_agent="bad\r\ninjection"))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(session_id_hash="short"))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(request_path="/x?token=1"))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(request_method="FETCH"))


# ── Email (auth-only) ────────────────────────────────────────────────────────

def test_email_normalized_and_gated():
    assert validation.validate_email(LOGIN, "  User@Example.COM ") == "user@example.com"
    assert validation.validate_email(LOGIN, None) is None
    with pytest.raises(AuditError):
        validation.validate_email(ROLE, "user@example.com")     # audit-событие
    with pytest.raises(AuditError):
        validation.validate_email(LOGIN, "a" * 250 + "@example.com")  # >255


def test_email_input_not_mutated():
    src = "  User@Example.COM "
    validation.validate_email(LOGIN, src)
    assert src == "  User@Example.COM "                          # неизменён


def test_email_rejects_empty_after_normalize():
    with pytest.raises(AuditError):
        validation.validate_email(LOGIN, "   ")


def test_email_rejects_control_characters():
    with pytest.raises(AuditError):
        validation.validate_email(LOGIN, "user@example.com\r\ninjected")


# ── Actor: anonymous/system не несут user_id/role (пункт 4) ───────────────────

def test_anonymous_actor_must_not_carry_user_id_or_role():
    bad = Actor(kind="anonymous", user_id=5, role=None)
    with pytest.raises(AuditError):
        validation.validate_actor(FAILED_LOGIN, bad)
    bad2 = Actor(kind="anonymous", user_id=None, role="admin")
    with pytest.raises(AuditError):
        validation.validate_actor(FAILED_LOGIN, bad2)
    validation.validate_actor(FAILED_LOGIN, Actor.anonymous())   # ok


def test_system_actor_must_not_carry_user_id_or_role():
    bad = Actor(kind="system", user_id=1, role=None)
    with pytest.raises(AuditError):
        validation.validate_actor(SYS, bad)
    bad2 = Actor(kind="system", user_id=None, role="admin")
    with pytest.raises(AuditError):
        validation.validate_actor(SYS, bad2)
    validation.validate_actor(SYS, Actor.system())               # ok


# ── RequestContext: неверный тип поля → AuditError, не TypeError (пункт 4) ─────

def test_context_wrong_types_raise_audit_error_not_type_error():
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(ip_address=12345))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(user_agent=999))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(session_id_hash=b"bytes"))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(request_path=["not", "a", "str"]))
    with pytest.raises(AuditError):
        validation.validate_context(RequestContext(request_method=404))


def test_context_error_messages_do_not_leak_value():
    # Неверный тип (не str) не должен попадать в текст сообщения об ошибке.
    with pytest.raises(AuditError) as ei:
        validation.validate_context(RequestContext(user_agent=1234567890))
    assert "1234567890" not in str(ei.value)
    with pytest.raises(AuditError) as ei2:
        validation.validate_context(RequestContext(ip_address="not-an-ip-address"))
    assert "not-an-ip-address" not in str(ei2.value)
