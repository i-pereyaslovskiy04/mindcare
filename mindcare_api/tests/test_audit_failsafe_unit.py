"""
Stage 5A-2 — unit-тесты record_secondary_failure (independently committed
best-effort failure audit). Реальная БД не используется.
"""
import app.audit.failsafe as failsafe
from app.audit import Actor, AuditResult, Outcome, RequestContext, WriteState
from app.audit.contracts import AuditError, AuditStorageError

ADMIN = Actor.user(101, "admin")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")


def _call(**over):
    kw = dict(event="admin_user_create_failed", actor=ADMIN,
              failure_reason_code="internal_error", context=CTX)
    kw.update(over)
    return failsafe.record_secondary_failure(**kw)


def test_success_returns_persisted(monkeypatch):
    monkeypatch.setattr(
        failsafe, "record_event",
        lambda **kw: AuditResult(state=WriteState.PERSISTED, event=kw["event"]),
    )
    res = _call()
    assert res.state is WriteState.PERSISTED


def test_facade_storage_soft_failure_returns_soft_failed(monkeypatch):
    # record_event сам вернул SOFT_FAILED (storage-сбой INDEPENDENT/SOFT).
    monkeypatch.setattr(
        failsafe, "record_event",
        lambda **kw: AuditResult(state=WriteState.SOFT_FAILED, event=kw["event"],
                                 error_class="OperationalError"),
    )
    res = _call()
    assert res.state is WriteState.SOFT_FAILED


def test_validation_audit_error_swallowed_to_soft_failed(monkeypatch):
    def _boom(**kw):
        raise AuditError("bad contract")
    monkeypatch.setattr(failsafe, "record_event", _boom)
    res = _call()
    assert res.state is WriteState.SOFT_FAILED       # не бросает наружу


def test_audit_storage_error_swallowed(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("storage down")
    monkeypatch.setattr(failsafe, "record_event", _boom)
    assert _call().state is WriteState.SOFT_FAILED


def test_unexpected_exception_swallowed_to_soft_failed(monkeypatch):
    def _boom(**kw):
        raise RuntimeError("unexpected in secondary writer")
    monkeypatch.setattr(failsafe, "record_event", _boom)
    assert _call().state is WriteState.SOFT_FAILED   # не бросает наружу


def test_real_facade_invalid_actor_role_is_soft_failed():
    # Реальный facade: actor с невалидной ролью → validation AuditError ДО
    # записи (без обращения к БД). failsafe поглощает → SOFT_FAILED.
    res = failsafe.record_secondary_failure(
        event="admin_user_create_failed",
        actor=Actor.user(1, "not-a-role"),
        failure_reason_code="internal_error", context=CTX,
    )
    assert res.state is WriteState.SOFT_FAILED


def test_forwards_exact_contract_to_record_event(monkeypatch):
    # Spy: record_event получает точный failure-контракт без изменений.
    seen = {}

    def _spy(**kw):
        seen.update(kw)
        return AuditResult(state=WriteState.PERSISTED, event=kw["event"])
    monkeypatch.setattr(failsafe, "record_event", _spy)

    failsafe.record_secondary_failure(
        event="admin_user_delete_failed", actor=ADMIN,
        failure_reason_code="user_not_found", context=CTX,
    )
    assert seen["event"] == "admin_user_delete_failed"
    assert seen["actor"] is ADMIN
    assert seen["outcome"] is Outcome.FAILURE
    assert seen["metadata"] == {}
    assert seen["failure_reason_code"] == "user_not_found"   # без изменения
    assert seen["context"] is CTX
    assert "target" not in seen        # target не передаётся (FORBIDDEN)
    assert "db" not in seen            # INDEPENDENT — без caller db


def test_diagnostics_contain_no_sensitive_payload(monkeypatch, capsys):
    def _boom(**kw):
        raise AuditError("contract")
    monkeypatch.setattr(failsafe, "record_event", _boom)
    failsafe.record_secondary_failure(
        event="admin_user_update_failed", actor=Actor.user(4242, "admin"),
        failure_reason_code="self_admin_protected",
        context=RequestContext(ip_address="198.51.100.9", user_agent="secret-ua"),
    )
    err = capsys.readouterr().err
    assert "event=admin_user_update_failed" in err
    assert "phase=secondary" in err
    assert "AuditError" in err
    # без actor id / code / ip / ua / str(exc)
    for leak in ("4242", "self_admin_protected", "198.51.100.9", "secret-ua",
                 "contract"):
        assert leak not in err
