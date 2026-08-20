"""
Stage 4B-2 — no-DB unit-тесты audit-writer'а email-доменов: fail-closed actor guard
и failure semantics (оба пути §6). SessionLocal и record_event замоканы, реальная
БД не используется.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

import app.email_domains.storage as storage
from app.audit.contracts import AuditStorageError


class _FakeCtx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *a):
        return False


def _patch_session(monkeypatch) -> MagicMock:
    db = MagicMock(name="db")
    monkeypatch.setattr(storage, "SessionLocal", lambda: _FakeCtx(db))
    return db


# ── Fail-closed actor guard (до мутации) ──────────────────────────────────────

@pytest.mark.parametrize("actor_id,actor_role", [(None, "admin"), (1, None)])
def test_create_domain_requires_actor(monkeypatch, actor_id, actor_role):
    called = {"session": False}
    monkeypatch.setattr(
        storage, "SessionLocal",
        lambda: called.__setitem__("session", True) or _FakeCtx(MagicMock()),
    )
    with pytest.raises(RuntimeError):
        storage.create_domain(
            domain="x.ru", comment=None,
            actor_id=actor_id, actor_role=actor_role, ip=None, user_agent=None,
        )
    assert called["session"] is False   # guard до открытия транзакции


@pytest.mark.parametrize("actor_id,actor_role", [(None, "admin"), (1, None)])
def test_set_domain_state_requires_actor(actor_id, actor_role):
    with pytest.raises(RuntimeError):
        storage.set_domain_state(
            domain_id=1, new_is_active=False, comment_provided=False,
            new_comment=None, actor_id=actor_id, actor_role=actor_role,
            ip=None, user_agent=None,
        )


# ── Path A: record_event падает до commit → commit не вызван ───────────────────

def test_create_domain_audit_failure_before_commit(monkeypatch):
    db = _patch_session(monkeypatch)

    def _boom(**kw):
        raise AuditStorageError("audit storage failure for email_domain_add")
    monkeypatch.setattr(storage, "record_event", _boom)

    with pytest.raises(AuditStorageError):
        storage.create_domain(
            domain="x.ru", comment=None,
            actor_id=1, actor_role="admin", ip=None, user_agent=None,
        )
    db.commit.assert_not_called()       # commit не достигнут
    db.refresh.assert_not_called()


# ── Path B: SQLAlchemyError на commit → success/refresh/return не выполняются ──

def test_create_domain_commit_failure(monkeypatch):
    db = _patch_session(monkeypatch)
    monkeypatch.setattr(storage, "record_event", lambda **kw: None)
    db.commit.side_effect = SQLAlchemyError("insert failed on commit")

    with pytest.raises(SQLAlchemyError):
        storage.create_domain(
            domain="x.ru", comment=None,
            actor_id=1, actor_role="admin", ip=None, user_agent=None,
        )
    db.refresh.assert_not_called()      # success-ветка (refresh/return) не выполнена


# ── record_event получает корректный Actor/Target/event (writer mapping) ──────

def test_create_domain_record_event_mapping(monkeypatch):
    db = _patch_session(monkeypatch)
    # flush проставляет id как реальная БД — эмулируем, чтобы Target получил int.
    fake_row = SimpleNamespace(id=777, domain="x.ru", is_active=True, comment=None,
                               created_at=None, updated_at=None)

    captured = {}
    monkeypatch.setattr(storage, "record_event",
                        lambda **kw: captured.update(kw))
    monkeypatch.setattr(storage, "_row_to_dict", lambda row: {"id": 777})
    # Подменяем конструктор строки, чтобы row.id был известен без реального flush.
    monkeypatch.setattr(storage, "AllowedEmailDomain", lambda **kw: fake_row)

    storage.create_domain(
        domain="x.ru", comment=None,
        actor_id=42, actor_role="admin", ip="203.0.113.7", user_agent="ua",
    )
    assert captured["event"] == "email_domain_add"
    assert captured["actor"].kind == "user"
    assert captured["actor"].user_id == 42 and captured["actor"].role == "admin"
    assert captured["target"].entity_type == "allowed_email_domain"
    assert captured["target"].entity_id == 777
    assert captured["db"] is db
    # metadata не передаётся (пусто); ip/ua санитизированы helper'ом
    assert captured.get("metadata") is None
    assert captured["context"].ip_address == "203.0.113.7"
