"""
Stage 4B-6 — no-DB unit-тесты переноса session_notes writer'ов на record_event():
session_note_created / session_note_updated (ATOMIC/RAISE в storage) и
session_note_content_read (INDEPENDENT/SOFT в service).

Покрывает: actor/target/metadata mapping всех трёх событий; единый actor id
(author_id одновременно SessionNote.author_id/owner-scope и Actor.user id, без
второго actor_id); fail-closed guard без скрытого role-default; AuditStorageError
на create/update → commit не достигнут; content-read SOFT_FAILED не ломает чтение;
sanitized context; отсутствие чувствительных данных в kwargs; static-проверки
удаления legacy log_note_event/helper-модуля и прямого AuditLog writer'а.
Реальная БД не используется.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import pytest

from app.audit.contracts import AuditResult, AuditStorageError, WriteState

import app.session_notes.storage as sn_storage
import app.session_notes.service as sn_service

AUTHOR_ID = 50
SUP_ID = 71


def _mock_session(mock_db):
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=mock_db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


def _boom_encrypt(*a, **k):
    raise AssertionError("encrypt_text must not run before actor guard")


# ══════════════════════════════════════════════════════════════════════════
# 1. create/update mapping — единый author_id, target, metadata, db
# ══════════════════════════════════════════════════════════════════════════

def test_create_mapping_single_actor_id(monkeypatch):
    calls = []
    monkeypatch.setattr(sn_storage, "record_event", lambda **kw: calls.append(kw))

    db = MagicMock(name="db")
    note_cls = MagicMock(name="SessionNote")
    note_cls.return_value = SimpleNamespace(id=777)
    monkeypatch.setattr(sn_storage, "SessionNote", note_cls)
    monkeypatch.setattr(sn_storage, "encrypt_text", lambda t: "enc:v1:x")
    monkeypatch.setattr(sn_storage, "_note_to_dict", lambda note: {"id": note.id})
    monkeypatch.setattr(sn_storage, "SessionLocal", _mock_session(db))

    sn_storage.create_note(
        author_id=AUTHOR_ID, appointment_id=None, engagement_id=None,
        note_type="general", content="терапевтический-секрет",
        is_shared_with_client=False,
        actor_role="psychologist", ip="203.0.113.7", user_agent="ua",
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "session_note_created"
    assert kw["actor"].user_id == AUTHOR_ID and kw["actor"].role == "psychologist"
    # единый id: actor.user_id == SessionNote.author_id (одна переменная)
    assert note_cls.call_args.kwargs["author_id"] == AUTHOR_ID
    assert note_cls.call_args.kwargs["author_id"] == kw["actor"].user_id
    assert kw["target"].entity_type == "session_note"
    assert kw["target"].entity_id == 777
    assert kw["metadata"] == {}
    assert kw["db"] is db
    db.flush.assert_called_once()
    db.commit.assert_called_once()
    # ни plaintext, ни ancillary id в kwargs аудита
    blob = repr(kw)
    for sensitive in ("секрет", "enc:v1:", "general", "engagement", "appointment"):
        assert sensitive not in blob


def test_update_mapping_single_actor_id(monkeypatch):
    calls = []
    monkeypatch.setattr(sn_storage, "record_event", lambda **kw: calls.append(kw))

    note = SimpleNamespace(id=777, version=1)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = note
    monkeypatch.setattr(sn_storage, "encrypt_text", lambda t: "enc:v1:x")
    monkeypatch.setattr(sn_storage, "_note_to_dict", lambda n: {"id": n.id})
    monkeypatch.setattr(sn_storage, "SessionLocal", _mock_session(db))

    sn_storage.update_note(
        777, {"content": "новый-секрет"},
        author_id=AUTHOR_ID, actor_role="psychologist",
        ip="203.0.113.7", user_agent="ua",
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "session_note_updated"
    # тот же author_id служит owner-scope (query) И audit actor id
    assert kw["actor"].user_id == AUTHOR_ID and kw["actor"].role == "psychologist"
    assert kw["target"].entity_type == "session_note"
    assert kw["target"].entity_id == 777
    assert kw["metadata"] == {}
    assert kw["db"] is db
    db.commit.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# 2. Fail-closed guard — до encrypt/мутации, без скрытого role-default
# ══════════════════════════════════════════════════════════════════════════

def test_create_requires_actor_role(monkeypatch):
    monkeypatch.setattr(sn_storage, "encrypt_text", _boom_encrypt)
    monkeypatch.setattr(sn_storage, "SessionLocal",
                        MagicMock(side_effect=AssertionError("no session")))
    with pytest.raises(RuntimeError):
        sn_storage.create_note(
            author_id=AUTHOR_ID, appointment_id=None, engagement_id=None,
            note_type="general", content="x", is_shared_with_client=False,
            actor_role=None,
        )
    with pytest.raises(RuntimeError):
        sn_storage.create_note(
            author_id=None, appointment_id=None, engagement_id=None,
            note_type="general", content="x", is_shared_with_client=False,
            actor_role="psychologist",
        )


def test_update_requires_actor_role(monkeypatch):
    monkeypatch.setattr(sn_storage, "encrypt_text", _boom_encrypt)
    monkeypatch.setattr(sn_storage, "SessionLocal",
                        MagicMock(side_effect=AssertionError("no session")))
    with pytest.raises(RuntimeError):
        sn_storage.update_note(1, {"content": "x"}, author_id=AUTHOR_ID,
                               actor_role=None)
    with pytest.raises(RuntimeError):
        sn_storage.update_note(1, {"content": "x"}, author_id=None,
                               actor_role="psychologist")


def test_actor_role_has_no_default_across_signatures():
    # actor_role обязателен (без default) во всех четырёх writer-сигнатурах,
    # чтобы заметку нельзя было создать/обновить без подтверждённой роли.
    import inspect
    for fn in (sn_storage.create_note, sn_storage.update_note,
               sn_service.create_note, sn_service.update_note):
        sig = inspect.signature(fn)
        assert "actor_role" in sig.parameters, fn.__qualname__
        assert sig.parameters["actor_role"].default is inspect.Parameter.empty, \
            fn.__qualname__


# ══════════════════════════════════════════════════════════════════════════
# 3. AuditStorageError (ATOMIC) → commit не достигнут, ошибка распространяется
# ══════════════════════════════════════════════════════════════════════════

def test_create_audit_failure_prevents_commit(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("audit storage failure for session_note_created")
    monkeypatch.setattr(sn_storage, "record_event", _boom)

    db = MagicMock(name="db")
    note_cls = MagicMock(name="SessionNote")
    note_cls.return_value = SimpleNamespace(id=1)
    monkeypatch.setattr(sn_storage, "SessionNote", note_cls)
    monkeypatch.setattr(sn_storage, "encrypt_text", lambda t: "enc:v1:x")
    monkeypatch.setattr(sn_storage, "SessionLocal", _mock_session(db))

    with pytest.raises(AuditStorageError):
        sn_storage.create_note(
            author_id=AUTHOR_ID, appointment_id=None, engagement_id=None,
            note_type="general", content="x", is_shared_with_client=False,
            actor_role="psychologist",
        )
    db.commit.assert_not_called()


def test_update_audit_failure_prevents_commit(monkeypatch):
    def _boom(**kw):
        raise AuditStorageError("audit storage failure for session_note_updated")
    monkeypatch.setattr(sn_storage, "record_event", _boom)

    note = SimpleNamespace(id=777, version=1)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = note
    monkeypatch.setattr(sn_storage, "encrypt_text", lambda t: "enc:v1:x")
    monkeypatch.setattr(sn_storage, "SessionLocal", _mock_session(db))

    with pytest.raises(AuditStorageError):
        sn_storage.update_note(777, {"content": "x"}, author_id=AUTHOR_ID,
                               actor_role="psychologist")
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 4. content_read — INDEPENDENT (без db), supervisor actor, SOFT не ломает read
# ══════════════════════════════════════════════════════════════════════════

def _sup_user():
    return {"id": str(SUP_ID), "roles": ["supervisor"]}


def test_content_read_mapping_supervisor_no_db(monkeypatch):
    calls = []
    monkeypatch.setattr(sn_service, "record_event", lambda **kw: calls.append(kw))
    note = {"id": 321, "author_id": 9}
    monkeypatch.setattr(sn_service.storage, "get_note_by_id",
                        lambda note_id, **kw: note)

    result = sn_service.get_note(
        321, current_user=_sup_user(), ip="203.0.113.7", user_agent="ua",
    )

    assert result is note
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "session_note_content_read"
    assert kw["actor"].user_id == SUP_ID and kw["actor"].role == "supervisor"
    assert kw["target"].entity_type == "session_note"
    assert kw["target"].entity_id == 321
    assert kw["metadata"] == {}
    assert "db" not in kw          # INDEPENDENT: caller db не передаётся


def test_content_read_soft_failed_does_not_break_read(monkeypatch):
    monkeypatch.setattr(
        sn_service, "record_event",
        lambda **kw: AuditResult(state=WriteState.SOFT_FAILED,
                                 event="session_note_content_read"),
    )
    note = {"id": 321, "author_id": 9}
    monkeypatch.setattr(sn_service.storage, "get_note_by_id",
                        lambda note_id, **kw: note)

    result = sn_service.get_note(321, current_user=_sup_user())
    assert result is note          # content-read остаётся успешным


def test_content_read_sanitizes_context(monkeypatch):
    calls = []
    monkeypatch.setattr(sn_service, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(sn_service.storage, "get_note_by_id",
                        lambda note_id, **kw: {"id": 321, "author_id": 9})

    sn_service.get_note(
        321, current_user=_sup_user(), ip="not-an-ip", user_agent="x" * 600,
    )
    ctx = calls[0]["context"]
    assert ctx.ip_address is None and ctx.user_agent is None


def test_admin_and_psychologist_get_no_content_read_audit(monkeypatch):
    calls = []
    monkeypatch.setattr(sn_service, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(sn_service.storage, "get_note_by_id",
                        lambda note_id, **kw: {"id": 321, "author_id": 9})

    sn_service.get_note(321, current_user={"id": "5", "roles": ["admin"]})
    sn_service.get_note(321, current_user={"id": "9", "roles": ["psychologist"]})
    assert calls == []


# ══════════════════════════════════════════════════════════════════════════
# 5. Static: legacy helper удалён, нет log_note_event / прямого AuditLog writer
# ══════════════════════════════════════════════════════════════════════════

_APP = Path(__file__).resolve().parents[1] / "app"


def test_legacy_note_audit_helper_removed():
    with pytest.raises(ModuleNotFoundError):
        import app.session_notes.audit  # noqa: F401


def test_session_notes_has_no_log_note_event():
    for rel in ("session_notes/storage.py", "session_notes/service.py",
                "session_notes/routes.py"):
        src = (_APP / rel).read_text(encoding="utf-8")
        assert "log_note_event" not in src, rel
        assert "session_notes.audit" not in src, rel


def test_no_log_note_event_anywhere_in_app():
    hits = [str(p) for p in _APP.rglob("*.py")
            if "log_note_event" in p.read_text(encoding="utf-8")]
    assert hits == []


def test_no_direct_auditlog_writer_outside_facade():
    hits = []
    for path in _APP.rglob("*.py"):
        rel = path.relative_to(_APP).as_posix()
        if rel in ("audit/service.py", "db/models/audit.py"):
            continue
        if "AuditLog(" in path.read_text(encoding="utf-8"):
            hits.append(rel)
    assert hits == []
