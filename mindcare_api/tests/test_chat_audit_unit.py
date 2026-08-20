"""
Stage 4B-3 — no-DB unit-тесты переноса chat audit-writer'ов на record_event().

Мокаются storage-функции и record_event (spy на app.chat.service/app.chat.
system_publisher модульном уровне); реальная БД не используется. Проверяют:
actor/target/metadata/context mapping для всех 6 событий, registry-widening для
chat_conversation_created (4 роли) vs остальные (student/psychologist only),
internal attachment id (без утечки в публичный ответ, без повторного lookup),
race-safe conversation_created для system_conversation_created, SOFT_FAILED/
AuditError не меняют business-result, отсутствие чувствительных данных,
отсутствие legacy writer/import/маркера.
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audit.contracts import Actor, AuditResult, AuditStorageError, WriteState
from app.audit.registry import get_spec
from app.audit.validation import AuditError, validate_actor
from app.chat import service as chat_service
from app.chat import system_publisher


def _spy(monkeypatch, module):
    calls = []

    def _rec(**kw):
        calls.append(kw)
        return AuditResult(WriteState.PERSISTED, kw.get("event", "?"))
    monkeypatch.setattr(module, "record_event", _rec)
    return calls


_MSG_UUID_1 = "aaaaaaaa-0000-0000-0000-000000000001"
_MSG_UUID_2 = "aaaaaaaa-0000-0000-0000-000000000002"


def _cu(id_, role):
    return {"id": id_, "email": f"{role}@e.com", "roles": [role], "role": role}


def _conv(id_=1, uuid_="c0000000-0000-0000-0000-000000000001"):
    return SimpleNamespace(id=id_, uuid=uuid_, last_message_at=None)


def _eng(status="active", client_id=10, id_=100, psychologist_id=20):
    return SimpleNamespace(
        id=id_, status=status, client_id=client_id,
        psychologist_id=psychologist_id, ended_at=None,
    )


# ── Registry contract: chat_conversation_created 4 роли, остальные 2 ──────────

@pytest.mark.parametrize("role", ["student", "psychologist", "supervisor", "admin"])
def test_chat_conversation_created_accepts_all_four_roles(role):
    validate_actor(get_spec("chat_conversation_created"), Actor.user(1, role))


@pytest.mark.parametrize("event", [
    "chat_message_edited", "chat_message_deleted",
    "chat_attachment_uploaded", "chat_attachment_downloaded",
])
@pytest.mark.parametrize("role", ["supervisor", "admin"])
def test_other_chat_events_reject_supervisor_admin(event, role):
    with pytest.raises(AuditError):
        validate_actor(get_spec(event), Actor.user(1, role))


@pytest.mark.parametrize("event", [
    "chat_message_edited", "chat_message_deleted",
    "chat_attachment_uploaded", "chat_attachment_downloaded",
])
@pytest.mark.parametrize("role", ["student", "psychologist"])
def test_other_chat_events_accept_student_psychologist(event, role):
    validate_actor(get_spec(event), Actor.user(1, role))


# ── chat_conversation_created: lazy-create (student, get_my_conversation) ─────

def test_get_my_conversation_lazy_create_mapping(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    eng = _eng()
    conv = _conv()
    monkeypatch.setattr(chat_service.storage, "get_engagement_for_student", lambda sid: eng)
    monkeypatch.setattr(chat_service.storage, "get_conversation_for_engagement", lambda eid: None)
    monkeypatch.setattr(chat_service.storage, "get_or_create_conversation", lambda eid: (conv, True))
    monkeypatch.setattr(chat_service.storage, "get_user_brief", lambda uid: {"id": uid, "full_name": "X"})
    monkeypatch.setattr(chat_service.storage, "unread_count", lambda cid, user_id: 0)
    monkeypatch.setattr(chat_service.storage, "is_user_online", lambda uid: False)

    chat_service.get_my_conversation(
        _cu(5, "student"), ip="203.0.113.5", user_agent="pytest-ua",
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "chat_conversation_created"
    assert kw["actor"].kind == "user" and kw["actor"].user_id == 5
    assert kw["actor"].role == "student"
    assert kw["target"].entity_type == "chat_conversation"
    assert kw["target"].entity_id == conv.id
    assert kw.get("metadata") is None       # пустая metadata (не передаётся)
    assert kw["db"] is None
    assert kw["context"].ip_address == "203.0.113.5"
    assert kw["context"].user_agent == "pytest-ua"


def test_send_my_message_lazy_create_mapping(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    eng = _eng()
    conv = _conv(id_=2)
    monkeypatch.setattr(chat_service.storage, "get_engagement_for_student", lambda sid: eng)
    monkeypatch.setattr(chat_service.storage, "get_or_create_conversation", lambda eid: (conv, True))
    monkeypatch.setattr(
        chat_service.storage, "create_message",
        lambda *a, **k: {"id": 1, "uuid": "m1", "sender_id": 5, "sender_role": "student",
                         "is_mine": True, "content": "hi", "created_at": None,
                         "read_at": None, "edited_at": None, "attachments": []},
    )

    chat_service.send_my_message(
        _cu(5, "student"), "hi", ip="203.0.113.5", user_agent="pytest-ua",
    )

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "chat_conversation_created"
    assert kw["target"].entity_id == conv.id
    assert kw["context"].ip_address == "203.0.113.5"


def test_lazy_create_not_called_when_conversation_not_new(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    eng = _eng()
    conv = _conv()
    monkeypatch.setattr(chat_service.storage, "get_engagement_for_student", lambda sid: eng)
    monkeypatch.setattr(chat_service.storage, "get_or_create_conversation", lambda eid: (conv, False))
    monkeypatch.setattr(
        chat_service.storage, "create_message",
        lambda *a, **k: {"id": 1, "uuid": "m1", "sender_id": 5, "sender_role": "student",
                         "is_mine": True, "content": "hi", "created_at": None,
                         "read_at": None, "edited_at": None, "attachments": []},
    )
    chat_service.send_my_message(_cu(5, "student"), "hi")
    assert calls == []


# ── chat_message_edited / chat_message_deleted ─────────────────────────────────

def test_edit_message_mapping_psychologist(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    conv = _conv(id_=3)
    eng = _eng(client_id=10)
    monkeypatch.setattr(
        chat_service, "_resolve_psychologist_conversation", lambda pid, uuid_: (conv, eng)
    )
    monkeypatch.setattr(
        chat_service.storage, "update_message_content",
        lambda **k: {"status": "ok", "message": {
            "id": 77, "uuid": _MSG_UUID_1, "sender_id": 20, "sender_role": "psychologist",
            "is_mine": True, "content": "edited", "created_at": None, "read_at": None,
            "edited_at": None, "is_deleted": False, "attachments": [],
        }},
    )

    chat_service.edit_message(_cu(20, "psychologist"), "conv-uuid", _MSG_UUID_1, "edited")

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "chat_message_edited"
    assert kw["actor"].user_id == 20 and kw["actor"].role == "psychologist"
    assert kw["target"].entity_type == "chat_message" and kw["target"].entity_id == 77
    assert kw.get("metadata") is None
    assert kw["context"] is None
    assert kw["db"] is None


def test_delete_message_mapping_student(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    conv = _conv(id_=4)
    eng = _eng(client_id=5)
    monkeypatch.setattr(
        chat_service, "_resolve_student_conversation_by_uuid", lambda sid, uuid_: (conv, eng)
    )
    monkeypatch.setattr(
        chat_service.storage, "soft_delete_message",
        lambda **k: {"status": "ok", "message": {
            "id": 88, "uuid": _MSG_UUID_2, "sender_id": 5, "sender_role": "student",
            "is_mine": True, "content": "", "created_at": None, "read_at": None,
            "edited_at": None, "is_deleted": True,
        }},
    )

    chat_service.delete_student_conversation_message(_cu(5, "student"), "conv-uuid", _MSG_UUID_2)

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "chat_message_deleted"
    assert kw["actor"].user_id == 5 and kw["actor"].role == "student"
    assert kw["target"].entity_id == 88


def test_repeated_idempotent_delete_writes_second_row(monkeypatch):
    # Известное поведение (Stage 4B-3 plan §2.4): storage no-op на повторном
    # delete, но service всё равно вызывает record_event при status=="ok".
    calls = _spy(monkeypatch, chat_service)
    conv = _conv(id_=4)
    eng = _eng(client_id=5)
    monkeypatch.setattr(
        chat_service, "_resolve_student_conversation_by_uuid", lambda sid, uuid_: (conv, eng)
    )
    monkeypatch.setattr(
        chat_service.storage, "soft_delete_message",
        lambda **k: {"status": "ok", "message": {
            "id": 88, "uuid": _MSG_UUID_2, "sender_id": 5, "sender_role": "student",
            "is_mine": True, "content": "", "created_at": None, "read_at": None,
            "edited_at": None, "is_deleted": True,
        }},
    )
    chat_service.delete_student_conversation_message(_cu(5, "student"), "conv-uuid", _MSG_UUID_2)
    chat_service.delete_student_conversation_message(_cu(5, "student"), "conv-uuid", _MSG_UUID_2)
    assert len(calls) == 2   # документированное поведение, не считается багом


# ── chat_attachment_uploaded: internal id, без утечки наружу ───────────────────

def test_upload_uses_internal_id_without_leaking_publicly(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    conv = _conv(id_=5)
    eng = _eng(status="active")
    monkeypatch.setattr(
        chat_service, "_resolve_student_conversation_by_uuid", lambda sid, uuid_: (conv, eng)
    )
    monkeypatch.setattr(chat_service._att_svc, "validate_upload", lambda f, d: None)
    monkeypatch.setattr(chat_service._att_svc, "normalize_mime", lambda f: "image/png")
    monkeypatch.setattr(chat_service._att_svc, "is_image_mime", lambda m: True)

    public_dict = {
        "uuid": "att-uuid-1", "original_filename": "photo.png",
        "mime_type": "image/png", "file_size": 1234, "is_image": True,
        "created_at": None,
    }
    monkeypatch.setattr(chat_service.storage, "save_attachment", lambda **k: (public_dict, 777))

    fake_file = SimpleNamespace(filename="photo.png")
    result = chat_service.upload_attachment_student(
        _cu(5, "student"), "conv-uuid", fake_file, b"data",
    )

    assert result == public_dict           # публичный dict не изменён
    assert "id" not in result              # internal id не раскрыт
    assert 777 not in result.values()

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "chat_attachment_uploaded"
    assert kw["target"].entity_type == "chat_attachment" and kw["target"].entity_id == 777
    assert kw["metadata"] == {"file_size": 1234, "mime_type": "image/png"}
    assert kw["context"] is None


def test_download_uses_att_id_without_repeated_lookup(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    conv = _conv(id_=6)
    monkeypatch.setattr(
        chat_service, "_resolve_student_conversation_by_uuid",
        lambda sid, uuid_: (conv, _eng()),
    )
    att = SimpleNamespace(
        id=888, uuid="att-uuid-2", storage_key="k", original_filename="f.pdf",
        mime_type="application/pdf",
    )
    lookups = {"count": 0}

    def _get_att(uuid_, cid):
        lookups["count"] += 1
        return att
    monkeypatch.setattr(chat_service.storage, "get_attachment_for_download", _get_att)

    fake_path = Path("dummy")
    import app.chat.attachment_storage as fs
    monkeypatch.setattr(fs, "open_for_read", lambda key: fake_path)

    path, filename, mime = chat_service.download_attachment_student(
        _cu(5, "student"), "conv-uuid", "att-uuid-2",
    )

    assert path == fake_path
    assert filename == "f.pdf"
    assert lookups["count"] == 1            # ровно один DB lookup, без повтора ради audit

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "chat_attachment_downloaded"
    assert kw["target"].entity_id == 888
    assert kw.get("metadata") is None


# ── SOFT_FAILED не меняет business-result ──────────────────────────────────────

def test_soft_failed_does_not_break_send_my_message(monkeypatch):
    monkeypatch.setattr(
        chat_service, "record_event",
        lambda **kw: AuditResult(WriteState.SOFT_FAILED, kw["event"], "X"),
    )
    eng = _eng()
    conv = _conv()
    monkeypatch.setattr(chat_service.storage, "get_engagement_for_student", lambda sid: eng)
    monkeypatch.setattr(chat_service.storage, "get_or_create_conversation", lambda eid: (conv, True))
    expected = {"id": 1, "uuid": "m1", "sender_id": 5, "sender_role": "student",
                "is_mine": True, "content": "hi", "created_at": None,
                "read_at": None, "edited_at": None, "attachments": []}
    monkeypatch.setattr(chat_service.storage, "create_message", lambda *a, **k: expected)

    out = chat_service.send_my_message(_cu(5, "student"), "hi")
    assert out == expected


# ── Отсутствие чувствительных данных в kwargs record_event ─────────────────────

def test_no_sensitive_data_in_edit_delete_upload_download_calls(monkeypatch):
    calls = _spy(monkeypatch, chat_service)
    conv = _conv(id_=9, uuid_="secret-conv-uuid")
    eng = _eng(client_id=10, id_=999)
    monkeypatch.setattr(
        chat_service, "_resolve_psychologist_conversation", lambda pid, uuid_: (conv, eng)
    )
    monkeypatch.setattr(
        chat_service.storage, "update_message_content",
        lambda **k: {"status": "ok", "message": {
            "id": 1, "uuid": _MSG_UUID_1, "sender_id": 20, "sender_role": "psychologist",
            "is_mine": True, "content": "SECRET-PLAINTEXT", "created_at": None,
            "read_at": None, "edited_at": None, "is_deleted": False, "attachments": [],
        }},
    )
    chat_service.edit_message(_cu(20, "psychologist"), "conv-uuid", _MSG_UUID_1, "SECRET-PLAINTEXT")

    blob = repr(calls)
    for forbidden in (
        "SECRET-PLAINTEXT", "secret-conv-uuid", "msg-uuid", "999", "storage_key",
        "checksum", "original_filename", "enc:v1:",
    ):
        assert forbidden not in blob


# ── Статическая проверка: legacy writer/import/маркер удалены ─────────────────

def test_chat_audit_module_removed():
    with pytest.raises(ModuleNotFoundError):
        import app.chat.audit  # noqa: F401


def test_no_audit_fail_marker_in_chat_scope():
    import app.chat.service as _svc
    import app.chat.system_publisher as _pub
    import app.supervisor.service as _sup
    for mod in (_svc, _pub, _sup):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "[AUDIT FAIL]" not in src


def test_no_direct_auditlog_in_chat_scope():
    import app.chat.service as _svc
    import app.chat.storage as _storage
    import app.chat.system_publisher as _pub
    import app.supervisor.service as _sup
    for mod in (_svc, _storage, _pub, _sup):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "AuditLog(" not in src


# ── system_publisher: race-safe conversation_created ───────────────────────────

def test_system_publisher_writes_once_when_conversation_created_true(monkeypatch):
    calls = _spy(monkeypatch, system_publisher)
    monkeypatch.setattr(
        system_publisher.storage, "create_system_message",
        lambda recipient_id, *, event_key, text: (
            {"created": True, "conversation_id": 42}, True,
        ),
    )
    out = system_publisher.publish_system_message(5, "welcome:user:5", "hi")
    assert out == {"created": True, "conversation_id": 42}
    assert set(out.keys()) == {"created", "conversation_id"}   # внутренний флаг не просочился
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "system_conversation_created"
    assert kw["actor"].kind == "system"
    assert kw["actor"].user_id is None and kw["actor"].role is None
    assert kw["target"].entity_type == "chat_conversation" and kw["target"].entity_id == 42
    assert kw.get("metadata") is None
    assert kw["context"] is None
    assert kw["db"] is None
    assert "recipient_id" not in repr(kw) and "5" not in str(kw.get("metadata"))


def test_system_publisher_no_audit_when_conversation_created_false(monkeypatch):
    calls = _spy(monkeypatch, system_publisher)
    monkeypatch.setattr(
        system_publisher.storage, "create_system_message",
        lambda recipient_id, *, event_key, text: (
            {"created": True, "conversation_id": 42}, False,
        ),
    )
    out = system_publisher.publish_system_message(5, "welcome:user:5", "hi")
    assert out == {"created": True, "conversation_id": 42}
    assert calls == []


def test_system_publisher_race_loser_does_not_write_false_duplicate(monkeypatch):
    # Race-loser: сообщение создалось, но беседу создал конкурент (created=False).
    calls = _spy(monkeypatch, system_publisher)
    monkeypatch.setattr(
        system_publisher.storage, "create_system_message",
        lambda recipient_id, *, event_key, text: (
            {"created": True, "conversation_id": 100}, False,
        ),
    )
    system_publisher.publish_system_message(9, "welcome:user:9", "hi")
    assert calls == []


def test_system_publisher_actor_mapping_via_facade():
    # Facade-level: Actor.system() -> AuditLog.user_id IS NULL, user_role == "system".
    from app.audit.service import _actor_role, _actor_user_id
    sys_actor = Actor.system()
    assert _actor_user_id(sys_actor) is None
    assert _actor_role(sys_actor) == "system"


# ── system_publisher: business exception diagnostic minimized ─────────────────

def test_business_exception_returns_none_and_minimizes_diagnostic(monkeypatch, capsys):
    def _boom(recipient_id, *, event_key, text):
        raise RuntimeError("inject: system message backend down")
    monkeypatch.setattr(system_publisher.storage, "create_system_message", _boom)

    out = system_publisher.publish_system_message(5, "welcome:user:5:secret", "hi")
    assert out is None

    captured = capsys.readouterr()
    assert "recipient_id" not in captured.err
    assert "welcome:user:5:secret" not in captured.err
    assert "inject: system message backend down" not in captured.err
    assert "phase=publish" in captured.err
    assert "RuntimeError" in captured.err
    assert "[AUDIT FAIL]" not in captured.err
    assert "[SYSTEM MSG FAIL]" not in captured.err


def test_audit_error_after_success_does_not_change_result(monkeypatch, capsys):
    monkeypatch.setattr(
        system_publisher.storage, "create_system_message",
        lambda recipient_id, *, event_key, text: (
            {"created": True, "conversation_id": 42}, True,
        ),
    )

    def _boom(**kw):
        raise AuditStorageError("contract violation")
    # AuditStorageError — подкласс AuditError (contracts): узкий catch в
    # system_publisher (except AuditError) обязан ловить и его тоже.
    assert issubclass(AuditStorageError, AuditError)
    monkeypatch.setattr(system_publisher, "record_event", _boom)

    out = system_publisher.publish_system_message(5, "welcome:user:5", "hi")
    assert out == {"created": True, "conversation_id": 42}

    captured = capsys.readouterr()
    assert "recipient_id" not in captured.err
    assert "welcome:user:5" not in captured.err
    assert "42" not in captured.err
    assert "[CHAT SYSTEM AUDIT]" in captured.err
    assert "system_conversation_created" in captured.err
    assert "[AUDIT FAIL]" not in captured.err


def test_soft_failed_does_not_change_system_publisher_result(monkeypatch):
    monkeypatch.setattr(
        system_publisher.storage, "create_system_message",
        lambda recipient_id, *, event_key, text: (
            {"created": True, "conversation_id": 42}, True,
        ),
    )
    monkeypatch.setattr(
        system_publisher, "record_event",
        lambda **kw: AuditResult(WriteState.SOFT_FAILED, "system_conversation_created", "X"),
    )
    out = system_publisher.publish_system_message(5, "welcome:user:5", "hi")
    assert out == {"created": True, "conversation_id": 42}
