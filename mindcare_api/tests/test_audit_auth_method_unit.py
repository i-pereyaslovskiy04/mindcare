"""
Stage Social Auth 3A — контракт auth_log.auth_method без БД.

AuthMethod (enum, не строка) + политика EventSpec.auth_method_policy:
login — REQUIRED, failed_login — OPTIONAL, остальные события — FORBIDDEN.
Значения enum совпадают с CHECK ck_auth_log_auth_method и OAUTH_PROVIDERS.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import CheckConstraint, String

from app.audit import service as audit_service
from app.audit import validation
from app.audit.contracts import (
    Actor, ActorPolicy, AuditError, AuthMethod, AuthMethodPolicy, Destination,
    FailurePolicy, Outcome, Target, TargetPolicy, TxMode,
)
from app.audit.registry import REGISTRY, _auth, _spec, build_registry
from app.db.models.audit import AUTH_LOG_AUTH_METHODS, AuthLog
from app.db.models.oauth import OAUTH_PROVIDERS

API_DIR = Path(__file__).resolve().parents[1]
MIGRATION = API_DIR / "alembic" / "versions" / "b8d2f6a3c9e4_auth_log_auth_method.py"


def _patch_session(monkeypatch) -> MagicMock:
    fake = MagicMock(name="session")
    monkeypatch.setattr(audit_service, "SessionLocal", lambda: fake)
    return fake


# ── выравнивание enum ↔ БД ↔ провайдеры ─────────────────────────────────────

def test_auth_method_values_match_db_check():
    assert {m.value for m in AuthMethod} == set(AUTH_LOG_AUTH_METHODS)


def test_oauth_providers_are_auth_methods():
    assert set(OAUTH_PROVIDERS) <= {m.value for m in AuthMethod}
    assert {m.value for m in AuthMethod} == {"password"} | set(OAUTH_PROVIDERS)


def test_orm_column_and_check_constraint():
    col = AuthLog.__table__.c.auth_method
    assert isinstance(col.type, String) and col.type.length == 20
    assert col.nullable is True
    checks = [
        c for c in AuthLog.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_auth_log_auth_method"
    ]
    assert len(checks) == 1
    text = str(checks[0].sqltext)
    for value in AUTH_LOG_AUTH_METHODS:
        assert f"'{value}'" in text


def test_migration_check_text_matches_orm():
    source = MIGRATION.read_text(encoding="utf-8")
    orm_text = str(next(
        c for c in AuthLog.__table__.constraints
        if isinstance(c, CheckConstraint) and c.name == "ck_auth_log_auth_method"
    ).sqltext)
    assert f"CHECK ({orm_text})" in source


def test_migration_downgrade_is_strict_and_fail_closed():
    source = MIGRATION.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade", 1)[1]
    ddl = [line for line in downgrade.splitlines() if "op.execute(" in line]
    assert len(ddl) == 2
    assert all("IF EXISTS" not in line for line in ddl)
    assert "auth_method IN ('yandex', 'vk')" in downgrade
    assert "raise RuntimeError" in downgrade


def test_migration_never_guesses_provider_for_history():
    upgrade = MIGRATION.read_text(encoding="utf-8").split("def upgrade", 1)[1]
    upgrade = upgrade.split("def downgrade", 1)[0]
    assert "'yandex'" not in upgrade.split("ADD CONSTRAINT", 1)[0]
    assert "'vk'" not in upgrade.split("ADD CONSTRAINT", 1)[0]


# ── политика registry ────────────────────────────────────────────────────────

def test_registry_policies():
    assert REGISTRY["login"].auth_method_policy is AuthMethodPolicy.REQUIRED
    assert REGISTRY["failed_login"].auth_method_policy is AuthMethodPolicy.OPTIONAL
    for name in ("logout", "registration_succeeded", "registration_failed",
                 "password_change", "password_reset"):
        assert REGISTRY[name].auth_method_policy is AuthMethodPolicy.FORBIDDEN


def test_only_auth_log_events_may_carry_auth_method():
    for spec in REGISTRY.values():
        if spec.destination is not Destination.AUTH_LOG:
            assert spec.auth_method_policy is AuthMethodPolicy.FORBIDDEN, spec.name


def test_registry_rejects_auth_method_on_audit_log_event():
    bad = _spec(
        "synthetic_event", Destination.AUDIT_LOG, ActorPolicy.SYSTEM, frozenset(),
        TargetPolicy.FORBIDDEN, None, {Outcome.SUCCESS}, frozenset(), {},
        TxMode.INDEPENDENT, FailurePolicy.SOFT,
        auth_method_policy=AuthMethodPolicy.OPTIONAL,
    )
    with pytest.raises(AuditError, match="auth_method only for AUTH_LOG"):
        build_registry([bad])


def test_registry_rejects_non_enum_policy():
    bad = _auth("synthetic_auth", ActorPolicy.ANONYMOUS_ONLY, frozenset(),
                {Outcome.SUCCESS}, frozenset(), auth_method="optional")
    with pytest.raises(AuditError, match="AuthMethodPolicy"):
        build_registry([bad])


# ── валидация значения ───────────────────────────────────────────────────────

def test_required_rejects_missing():
    with pytest.raises(AuditError, match="required"):
        validation.validate_auth_method(REGISTRY["login"], None)


@pytest.mark.parametrize("method", list(AuthMethod))
def test_required_and_optional_accept_every_member(method):
    assert validation.validate_auth_method(REGISTRY["login"], method) == method.value
    assert validation.validate_auth_method(REGISTRY["failed_login"], method) == method.value


def test_optional_accepts_none():
    assert validation.validate_auth_method(REGISTRY["failed_login"], None) is None


@pytest.mark.parametrize("raw", ["password", "yandex", "google", "", 1, True])
def test_arbitrary_values_rejected(raw):
    with pytest.raises(AuditError, match="AuthMethod member"):
        validation.validate_auth_method(REGISTRY["login"], raw)


@pytest.mark.parametrize("event", ["logout", "password_change", "password_reset",
                                   "registration_succeeded", "registration_failed"])
def test_forbidden_events_reject_value_and_accept_none(event):
    assert validation.validate_auth_method(REGISTRY[event], None) is None
    with pytest.raises(AuditError, match="not allowed"):
        validation.validate_auth_method(REGISTRY[event], AuthMethod.PASSWORD)


def test_error_messages_do_not_echo_value():
    with pytest.raises(AuditError) as ei:
        validation.validate_auth_method(REGISTRY["login"], "SECRET_marker_x")
    assert "SECRET_marker_x" not in str(ei.value)


# ── facade: значение доходит до строки, ошибка — до записи ───────────────────

def test_record_event_writes_auth_method(monkeypatch):
    fake = _patch_session(monkeypatch)
    audit_service.record_event(
        event="failed_login", actor=Actor.anonymous(), outcome=Outcome.FAILURE,
        failure_reason_code="oauth_identity_unknown", auth_method=AuthMethod.YANDEX,
    )
    row = fake.add.call_args.args[0]
    assert isinstance(row, AuthLog) and row.auth_method == "yandex"


def test_record_event_login_without_method_fails_before_session(monkeypatch):
    fake = _patch_session(monkeypatch)
    with pytest.raises(AuditError):
        audit_service.record_event(
            event="login", actor=Actor.user(3, "student"), user_email="a@b.com",
        )
    fake.add.assert_not_called()


def test_record_event_logout_with_method_rejected(monkeypatch):
    fake = _patch_session(monkeypatch)
    with pytest.raises(AuditError):
        audit_service.record_event(
            event="logout", actor=Actor.user(3, "student"),
            auth_method=AuthMethod.PASSWORD,
        )
    fake.add.assert_not_called()


def test_audit_log_row_has_no_auth_method_field(monkeypatch):
    fake = _patch_session(monkeypatch)
    audit_service.record_event(
        event="system_conversation_created", actor=Actor.system(),
        target=Target("chat_conversation", 1),
    )
    row = fake.add.call_args.args[0]
    assert not hasattr(row, "auth_method")
