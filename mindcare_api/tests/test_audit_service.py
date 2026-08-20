"""
Stage 4A — no-DB тесты record_event: routing, actor/target mapping, tx modes,
sanitized error handling. Реальная БД не используется: ATOMIC → MagicMock caller db;
INDEPENDENT → monkeypatch service.SessionLocal.
"""
from unittest.mock import MagicMock

import pytest

from app.audit import service
from app.audit.service import record_event
from app.audit.contracts import (
    Actor, AuditError, AuditStorageError, Outcome, RequestContext, Target, WriteState,
)
from app.db.models import AuditLog, AuthLog


def _patch_session(monkeypatch) -> MagicMock:
    fake = MagicMock(name="session")
    monkeypatch.setattr(service, "SessionLocal", lambda: fake)
    return fake


def _added(mock) -> object:
    return mock.add.call_args.args[0]


# ── ATOMIC ───────────────────────────────────────────────────────────────────

def test_atomic_stages_row_actor_target_not_swapped():
    db = MagicMock(name="caller_db")
    res = record_event(
        event="supervisor_create_student",
        actor=Actor.user(500, "supervisor"),
        target=Target("user", 600),
        db=db,
    )
    assert res.state is WriteState.STAGED
    row = _added(db)
    assert isinstance(row, AuditLog)
    assert row.user_id == 500 and row.entity_id == 600      # actor≠target, не перепутаны
    assert row.user_role == "supervisor" and row.entity_type == "user"
    assert row.outcome == "success"
    assert not db.commit.called and not db.rollback.called and not db.close.called


def test_atomic_requires_db():
    with pytest.raises(AuditError):
        record_event(
            event="supervisor_create_student",
            actor=Actor.user(1, "supervisor"), target=Target("user", 2), db=None,
        )


def test_atomic_storage_error_sanitized():
    db = MagicMock(name="caller_db")
    db.add.side_effect = Exception("SECRET_sql_detail")
    with pytest.raises(AuditStorageError) as ei:
        record_event(
            event="supervisor_create_student",
            actor=Actor.user(1, "supervisor"), target=Target("user", 2), db=db,
        )
    assert "SECRET_sql_detail" not in str(ei.value)
    assert ei.value.__cause__ is None                       # raise ... from None
    assert isinstance(ei.value, AuditError)                 # единый базовый тип


# ── INDEPENDENT ──────────────────────────────────────────────────────────────

def test_independent_persists_and_owns_session(monkeypatch):
    fake = _patch_session(monkeypatch)
    res = record_event(
        event="chat_conversation_created",
        actor=Actor.user(1, "psychologist"),
        target=Target("chat_conversation", 9),
    )
    assert res.state is WriteState.PERSISTED
    assert fake.add.called and fake.commit.called and fake.close.called
    assert not fake.rollback.called
    assert isinstance(_added(fake), AuditLog) and _added(fake).entity_id == 9


def test_independent_forbids_caller_db(monkeypatch):
    _patch_session(monkeypatch)
    with pytest.raises(AuditError):
        record_event(
            event="chat_conversation_created",
            actor=Actor.user(1, "psychologist"),
            target=Target("chat_conversation", 9), db=MagicMock(),
        )


def test_independent_soft_fail_sanitized(monkeypatch, capsys):
    fake = _patch_session(monkeypatch)
    fake.commit.side_effect = Exception("SECRET_pw_leak")
    res = record_event(
        event="chat_conversation_created",
        actor=Actor.user(1, "psychologist"),
        target=Target("chat_conversation", 9),
    )
    assert res.state is WriteState.SOFT_FAILED
    assert res.error_class == "Exception"                   # только класс, без message
    assert fake.rollback.called and fake.close.called
    err = capsys.readouterr().err
    assert "SECRET_pw_leak" not in err
    assert "chat_conversation_created" in err               # только имя события


def test_system_actor_mapping(monkeypatch):
    fake = _patch_session(monkeypatch)
    record_event(
        event="system_conversation_created",
        actor=Actor.system(), target=Target("chat_conversation", 42),
    )
    row = _added(fake)
    assert row.user_id is None and row.user_role == "system" and row.entity_id == 42


# ── AUTH_LOG routing / mapping ───────────────────────────────────────────────

def test_auth_success_routes_to_authlog(monkeypatch):
    fake = _patch_session(monkeypatch)
    record_event(
        event="login", actor=Actor.user(3, "admin"),
        context=RequestContext(session_id_hash="a" * 64), user_email="X@Y.com",
    )
    row = _added(fake)
    assert isinstance(row, AuthLog)
    assert row.success is True and row.user_id == 3
    assert row.user_email == "x@y.com" and row.session_id == "a" * 64


def test_auth_failure_maps_to_success_false_and_code(monkeypatch):
    fake = _patch_session(monkeypatch)
    record_event(
        event="failed_login", actor=Actor.anonymous(),
        outcome=Outcome.FAILURE, failure_reason_code="invalid_credentials",
        user_email="a@b.com",
    )
    row = _added(fake)
    assert isinstance(row, AuthLog)
    assert row.success is False and row.failure_reason == "invalid_credentials"
    assert row.user_id is None and row.user_email == "a@b.com"


# ── INDEPENDENT full lifecycle: factory/add/commit/rollback/close (пункт 1) ────
#
# Ошибка ЖУРНАЛА никогда не становится business outcome напрямую: результат
# определяется ПЕРВИЧНЫМ сбоем (factory/add/commit) и failure_policy; rollback/
# close — best-effort, их ошибки не заменяют уже определённый результат.

_SECRET = "SECRET_leak_marker_9f3a"


def _call_independent(**kw):
    return record_event(
        event="chat_conversation_created",
        actor=Actor.user(1, "psychologist"),
        target=Target("chat_conversation", 9),
        **kw,
    )


def test_independent_factory_raises_soft(monkeypatch, capsys):
    def _boom():
        raise RuntimeError(_SECRET)
    monkeypatch.setattr(service, "SessionLocal", _boom)

    res = _call_independent()
    assert res.state is WriteState.SOFT_FAILED
    assert res.error_class == "RuntimeError"
    assert _SECRET not in repr(res)
    err = capsys.readouterr().err
    assert _SECRET not in err
    assert "phase=factory" in err


def test_independent_add_raises_soft(monkeypatch, capsys):
    fake = _patch_session(monkeypatch)
    fake.add.side_effect = ValueError(_SECRET)

    res = _call_independent()
    assert res.state is WriteState.SOFT_FAILED
    assert res.error_class == "ValueError"
    assert fake.rollback.called and fake.close.called
    assert not fake.commit.called
    err = capsys.readouterr().err
    assert _SECRET not in err
    assert "phase=add" in err


def test_independent_commit_raises_soft(monkeypatch, capsys):
    fake = _patch_session(monkeypatch)
    fake.commit.side_effect = ValueError(_SECRET)

    res = _call_independent()
    assert res.state is WriteState.SOFT_FAILED
    assert res.error_class == "ValueError"
    assert fake.rollback.called and fake.close.called
    err = capsys.readouterr().err
    assert _SECRET not in err
    assert "phase=commit" in err


def test_independent_rollback_raises_after_original_error_does_not_replace_it(
    monkeypatch, capsys,
):
    fake = _patch_session(monkeypatch)
    fake.commit.side_effect = ValueError(_SECRET + "_commit")
    fake.rollback.side_effect = RuntimeError(_SECRET + "_rollback")

    res = _call_independent()
    # Итоговый результат определяется ИСХОДНОЙ ошибкой (ValueError), не rollback.
    assert res.state is WriteState.SOFT_FAILED
    assert res.error_class == "ValueError"
    assert fake.close.called                       # close всё равно best-effort вызван
    err = capsys.readouterr().err
    assert _SECRET not in err                       # ни один из secret-текстов не утёк
    assert "phase=commit" in err and "phase=rollback" in err


def test_independent_close_raises_after_original_error_does_not_replace_it(
    monkeypatch, capsys,
):
    fake = _patch_session(monkeypatch)
    fake.commit.side_effect = ValueError(_SECRET + "_commit")
    fake.close.side_effect = RuntimeError(_SECRET + "_close")

    res = _call_independent()
    assert res.state is WriteState.SOFT_FAILED
    assert res.error_class == "ValueError"          # не подменено close-ошибкой
    assert fake.rollback.called
    err = capsys.readouterr().err
    assert _SECRET not in err
    assert "phase=commit" in err and "phase=close" in err


def test_independent_close_raises_after_successful_commit_stays_persisted(
    monkeypatch, capsys,
):
    fake = _patch_session(monkeypatch)
    fake.close.side_effect = RuntimeError(_SECRET)

    res = _call_independent()
    # commit прошёл успешно → запись уже зафиксирована; сбой close НЕ откатывает
    # PERSISTED в SOFT_FAILED и не вызывает повторный add/commit.
    assert res.state is WriteState.PERSISTED
    assert res.error_class is None
    assert fake.commit.call_count == 1
    assert not fake.rollback.called                 # rollback после успешного commit не нужен
    err = capsys.readouterr().err
    assert _SECRET not in err
    assert "phase=close" in err                     # диагностика есть, но не влияет на результат


def test_independent_raise_policy_via_synthetic_spec(monkeypatch):
    # Production registry не содержит INDEPENDENT+RAISE событий; проверяем эту
    # ветку через безопасный synthetic EventSpec (не публикуется в REGISTRY).
    from types import MappingProxyType
    from app.audit.contracts import (
        ActorPolicy, Destination, EventSpec, FailurePolicy, TargetPolicy, TxMode,
    )

    synthetic = EventSpec(
        name="synthetic_independent_raise",
        destination=Destination.AUDIT_LOG,
        actor_policy=ActorPolicy.SYSTEM,
        allowed_actor_roles=frozenset(),
        target_policy=TargetPolicy.FORBIDDEN,
        entity_type=None,
        allowed_outcomes=frozenset({Outcome.SUCCESS}),
        allowed_failure_codes=frozenset(),
        metadata_schema=MappingProxyType({}),
        tx_mode=TxMode.INDEPENDENT,
        failure_policy=FailurePolicy.RAISE,
    )
    monkeypatch.setattr(service, "get_spec", lambda name: synthetic)
    fake = _patch_session(monkeypatch)
    fake.commit.side_effect = RuntimeError(_SECRET)

    with pytest.raises(AuditStorageError) as ei:
        record_event(event="synthetic_independent_raise", actor=Actor.system())
    assert _SECRET not in str(ei.value)
    assert ei.value.__cause__ is None
    assert fake.rollback.called and fake.close.called
