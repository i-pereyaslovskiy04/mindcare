"""
Stage 4B-2 — no-DB unit-тесты supervisor audit-writer'ов.

Проверяют writer mapping (record_event получает Actor.user с int ID, правильный
Target/event/db) и failure semantics (оба пути §6) на самой простой по запросам
операции close_engagement. SessionLocal и record_event замоканы; реальная БД не
используется. Плюс структурная проверка, что _log_event и broad swallow удалены.
"""
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.supervisor.service as svc
from app.audit.contracts import AuditStorageError
from app.db.models import TherapyEngagement, User


class _FakeQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._result


class _FakeDB:
    def __init__(self, engagement, user, commit_exc=None):
        self._engagement = engagement
        self._user = user
        self._commit_exc = commit_exc
        self.committed = False
        self.refreshed = False
        self.added = []

    def query(self, model):
        if model is TherapyEngagement:
            return _FakeQuery(self._engagement)
        if model is User:
            return _FakeQuery(self._user)
        return _FakeQuery(None)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass

    def commit(self):
        if self._commit_exc is not None:
            raise self._commit_exc
        self.committed = True

    def refresh(self, obj):
        self.refreshed = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _engagement():
    return SimpleNamespace(
        id=555, status="active", client_id=10, psychologist_id=20,
        primary_concern=None, started_at=None, ended_at=None,
        transfer_reason=None, updated_at=None,
    )


def _patch(monkeypatch, db):
    monkeypatch.setattr(svc, "SessionLocal", lambda: db)
    # post-commit system-уведомления не нужны в unit-е.
    monkeypatch.setattr(svc, "publish_system_message", lambda **k: None)
    monkeypatch.setattr(svc, "_publish_chat_event", lambda **k: None)


# ── Структурная проверка: swallow удалён ──────────────────────────────────────

def test_log_event_removed():
    assert not hasattr(svc, "_log_event")
    from pathlib import Path
    src = Path(svc.__file__).read_text(encoding="utf-8")
    assert "[AUDIT FAIL]" not in src        # broad swallow-print удалён


# ── Writer mapping: record_event получает int actor / правильный target ───────

@pytest.mark.parametrize("actor_role", ["supervisor", "admin"])
def test_close_engagement_record_event_mapping(monkeypatch, actor_role):
    db = _FakeDB(_engagement(), SimpleNamespace(full_name="X", email="x@e.com"))
    _patch(monkeypatch, db)
    captured = {}
    monkeypatch.setattr(svc, "record_event", lambda **kw: captured.update(kw))

    svc.close_engagement(
        engagement_id=555, reason="секретная причина",
        actor_id=42, actor_role=actor_role,
    )

    assert captured["event"] == "supervisor_close_engagement"
    assert captured["actor"].kind == "user"
    assert type(captured["actor"].user_id) is int and captured["actor"].user_id == 42
    assert captured["actor"].role == actor_role
    assert captured["target"].entity_type == "therapy_engagement"
    assert captured["target"].entity_id == 555
    assert captured["db"] is db
    assert captured["context"] is None
    assert captured.get("metadata") is None       # metadata пуста
    # reason (может быть ПДн) в audit не передаётся
    assert "секретная причина" not in repr(captured)
    assert db.committed is True


# ── Failure path A: record_event падает до commit → commit не вызван ──────────

def test_close_engagement_audit_failure_before_commit(monkeypatch):
    db = _FakeDB(_engagement(), SimpleNamespace(full_name="X", email="x@e.com"))
    _patch(monkeypatch, db)

    def _boom(**kw):
        raise AuditStorageError("audit storage failure for supervisor_close_engagement")
    monkeypatch.setattr(svc, "record_event", _boom)

    with pytest.raises(AuditStorageError):
        svc.close_engagement(
            engagement_id=555, reason=None, actor_id=42, actor_role="supervisor",
        )
    assert db.committed is False       # сбой аудита НЕ проглочен, commit не достигнут
    assert db.refreshed is False


# ── Failure path B: SQLAlchemyError на commit → success/refresh не выполнены ──

def test_close_engagement_commit_failure(monkeypatch):
    db = _FakeDB(
        _engagement(), SimpleNamespace(full_name="X", email="x@e.com"),
        commit_exc=SQLAlchemyError("audit insert failed on commit"),
    )
    _patch(monkeypatch, db)
    monkeypatch.setattr(svc, "record_event", lambda **kw: None)

    with pytest.raises(SQLAlchemyError):
        svc.close_engagement(
            engagement_id=555, reason=None, actor_id=42, actor_role="supervisor",
        )
    assert db.refreshed is False       # success-ветка (refresh/return) не выполнена
