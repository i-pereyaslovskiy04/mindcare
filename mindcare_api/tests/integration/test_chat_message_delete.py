"""
Stage 31y (+ 31y-hotfix) — удаление своих сообщений Messenger (DELETE, soft delete).

Политика (как у edit): своё user-сообщение, только в active engagement;
system/чужие → 404; повторное удаление идемпотентно (200). DELETE-ответ —
технический (is_deleted=True, content=""), но в обычной выдаче GET messages
удалённое сообщение НЕ возвращается вовсе (без плейсхолдера). В БД остаётся
deleted_at + enc:v1: ciphertext (не перезаписан plaintext'ом).
Audit chat_message_deleted без текста.

Requires dev PostgreSQL on alembic head + DATA_ENCRYPTION_KEY.
"""

import uuid as _uuid
from datetime import datetime, timezone

import bcrypt

from app.auth import storage as auth_storage
from app.core.encryption import ENCRYPTION_PREFIX, decrypt_text, encrypt_text
from app.supervisor import service as sup
from app.db.session import SessionLocal
from app.db.models import AuditLog, ChatConversation, ChatMessage

PASSWORD = "SecurePass42!"


def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Del {role} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_del_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _assign(s_id, p_id, sup_id):
    return sup.assign_psychologist(
        client_id=s_id, psychologist_id=p_id, primary_concern=None,
        actor_id=sup_id, actor_role="supervisor",
    )


def _transfer(eng_id, new_p_id, sup_id):
    return sup.transfer_psychologist(
        engagement_id=eng_id, new_psychologist_id=new_p_id,
        transfer_reason=None, actor_id=sup_id, actor_role="supervisor",
    )


def _conv_uuid(eng_id) -> str:
    with SessionLocal() as db:
        c = db.query(ChatConversation).filter_by(engagement_id=eng_id).first()
        return str(c.uuid)


def _student_send(client, token, conv, text):
    r = client.post(
        f"/api/chat/student/conversations/{conv}/messages",
        headers=_auth(token), json={"content": text},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _psych_send(client, token, conv, text):
    r = client.post(
        f"/api/chat/conversations/{conv}/messages",
        headers=_auth(token), json={"content": text},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _student_delete(client, token, conv, msg_uuid):
    return client.delete(
        f"/api/chat/student/conversations/{conv}/messages/{msg_uuid}",
        headers=_auth(token),
    )


def _psych_delete(client, token, conv, msg_uuid):
    return client.delete(
        f"/api/chat/conversations/{conv}/messages/{msg_uuid}",
        headers=_auth(token),
    )


def _student_messages(client, token, conv):
    r = client.get(
        f"/api/chat/student/conversations/{conv}/messages",
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _setup_active(client):
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")
    eng = _assign(s_id, p_id, sup_id)
    conv = _conv_uuid(eng["id"])
    return s_token, s_id, p_token, p_id, sup_id, eng, conv


# ─── A. author deletes own message → hidden from GET, ciphertext preserved ────

def test_student_deletes_own_message(client):
    s_token, *_rest, conv = _setup_active(client)
    secret = "СЕКРЕТ-удаляемый-uniq"
    sent = _student_send(client, s_token, conv, secret)

    r = _student_delete(client, s_token, conv, sent["uuid"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_deleted"] is True   # технический ответ операции
    assert body["content"] == ""
    assert body["uuid"] == sent["uuid"]

    # В БД: deleted_at проставлен, content остался enc:v1:, plaintext не утёк.
    with SessionLocal() as db:
        row = db.query(ChatMessage).filter(ChatMessage.uuid == sent["uuid"]).one()
        assert row.deleted_at is not None
        assert row.content.startswith(ENCRYPTION_PREFIX)
        assert secret not in row.content

    # В обычной выдаче удалённое сообщение отсутствует (без плейсхолдера/текста).
    items = _student_messages(client, s_token, conv)
    assert all(m["uuid"] != sent["uuid"] for m in items)
    assert secret not in str(items)
    assert "удал" not in str(items).lower()


def test_psychologist_deletes_own_message(client):
    _s_token, _s_id, p_token, *_rest, conv = _setup_active(client)
    sent = _psych_send(client, p_token, conv, "psy удалю")
    r = _psych_delete(client, p_token, conv, sent["uuid"])
    assert r.status_code == 200, r.text
    assert r.json()["is_deleted"] is True


# ─── B. cannot delete other's message → 404, content intact ───────────────────

def test_student_cannot_delete_psychologist_message(client):
    s_token, _s_id, p_token, *_rest, conv = _setup_active(client)
    psy_msg = _psych_send(client, p_token, conv, "сообщение психолога")
    r = _student_delete(client, s_token, conv, psy_msg["uuid"])
    assert r.status_code == 404
    with SessionLocal() as db:
        row = db.query(ChatMessage).filter(ChatMessage.uuid == psy_msg["uuid"]).one()
        assert row.deleted_at is None
        assert decrypt_text(row.content) == "сообщение психолога"


def test_psychologist_cannot_delete_student_message(client):
    s_token, _s_id, p_token, *_rest, conv = _setup_active(client)
    stu_msg = _student_send(client, s_token, conv, "сообщение студента")
    r = _psych_delete(client, p_token, conv, stu_msg["uuid"])
    assert r.status_code == 404
    with SessionLocal() as db:
        row = db.query(ChatMessage).filter(ChatMessage.uuid == stu_msg["uuid"]).one()
        assert row.deleted_at is None


# ─── C. cannot delete system message → 404 ────────────────────────────────────

def test_cannot_delete_system_message(client):
    s_token, _s_id, *_rest, eng, conv = _setup_active(client)
    with SessionLocal() as db:
        c = db.query(ChatConversation).filter_by(engagement_id=eng["id"]).one()
        sys_msg = ChatMessage(
            conversation_id=c.id,
            message_kind="system",
            sender_id=None,
            content=encrypt_text("служебное"),
        )
        db.add(sys_msg)
        db.commit()
        db.refresh(sys_msg)
        sys_uuid = str(sys_msg.uuid)

    r = _student_delete(client, s_token, conv, sys_uuid)
    assert r.status_code == 404
    with SessionLocal() as db:
        row = db.query(ChatMessage).filter(ChatMessage.uuid == sys_uuid).one()
        assert row.deleted_at is None


# ─── D. repeated delete is idempotent (stable) → 200 ──────────────────────────

def test_repeated_delete_is_idempotent(client):
    s_token, *_rest, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "дважды удалю")

    r1 = _student_delete(client, s_token, conv, sent["uuid"])
    assert r1.status_code == 200
    r2 = _student_delete(client, s_token, conv, sent["uuid"])
    assert r2.status_code == 200
    assert r2.json()["is_deleted"] is True


# ─── D2. deleting the last message: feed falls back to previous, no placeholder ─

def test_deleting_last_message_falls_back_to_previous(client):
    s_token, *_rest, conv = _setup_active(client)
    first = _student_send(client, s_token, conv, "первое")
    last = _student_send(client, s_token, conv, "последнее-уд")

    r = _student_delete(client, s_token, conv, last["uuid"])
    assert r.status_code == 200

    items = _student_messages(client, s_token, conv)
    uuids = [m["uuid"] for m in items]
    assert last["uuid"] not in uuids          # удалённое скрыто
    assert first["uuid"] in uuids             # предыдущее осталось
    assert items[-1]["uuid"] == first["uuid"]  # последнее видимое — предыдущее
    assert "удал" not in str(items).lower()    # никакого «Сообщение удалено»


# ─── E. cannot delete in closed (transferred) engagement → 409 ────────────────

def test_cannot_delete_in_closed_engagement(client):
    s_token, _s_id, _p_token, _p_id, sup_id, eng, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "до перевода")

    _y, y_id = _make_user(client, "psychologist")
    _transfer(eng["id"], y_id, sup_id)   # eng становится transferred → не active

    r = _student_delete(client, s_token, conv, sent["uuid"])
    assert r.status_code == 409
    with SessionLocal() as db:
        row = db.query(ChatMessage).filter(ChatMessage.uuid == sent["uuid"]).one()
        assert row.deleted_at is None


# ─── F. delete does not create unread for peer ────────────────────────────────

def test_delete_does_not_create_unread(client):
    s_token, _s_id, p_token, _p_id, *_rest, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "видно психологу")
    # психолог читает (mark read), затем студент удаляет — unread не должен вырасти.
    client.post(f"/api/chat/conversations/{conv}/read", headers=_auth(p_token))
    _student_delete(client, s_token, conv, sent["uuid"])

    r = client.get(f"/api/chat/conversations/{conv}", headers=_auth(p_token))
    assert r.status_code == 200
    assert r.json()["unread_count"] == 0


# ─── G. audit chat_message_deleted без plaintext ──────────────────────────────

def test_audit_event_without_plaintext(client):
    s_token, s_id, *_rest, conv = _setup_active(client)
    secret = "СЕКРЕТ-для-удаления-uniq"
    sent = _student_send(client, s_token, conv, secret)
    r = _student_delete(client, s_token, conv, sent["uuid"])
    assert r.status_code == 200
    msg_id = r.json()["id"]

    with SessionLocal() as db:
        logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "chat_message_deleted",
                AuditLog.entity_id == msg_id,
            )
            .all()
        )
        assert len(logs) == 1, "ожидается ровно одна строка chat_message_deleted"
        log = logs[0]
        # Stage 4B-3: metadata пуста, description не пишется, actor == sender.
        assert (log.log_metadata or {}) == {}
        assert log.description is None
        assert log.user_id == s_id
        assert log.user_role == "student"
        blob = f"{log.description} {log.log_metadata}"
        assert secret not in blob
        assert ENCRYPTION_PREFIX not in blob


def test_repeated_idempotent_delete_writes_second_audit_row(client):
    # Stage 4B-3 plan §2.4 (документированное поведение, не баг): storage
    # no-op на повторном удалении уже удалённого сообщения (deleted_at не
    # трогается повторно), но service всё равно вызывает record_event при
    # status=="ok" — повторный DELETE того же сообщения пишет ВТОРУЮ
    # audit-строку chat_message_deleted на тот же entity_id.
    s_token, s_id, *_rest, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "сообщение для повторного удаления")
    msg_id = sent["id"]

    r1 = _student_delete(client, s_token, conv, sent["uuid"])
    assert r1.status_code == 200
    r2 = _student_delete(client, s_token, conv, sent["uuid"])
    assert r2.status_code == 200          # идемпотентно на уровне HTTP-ответа

    with SessionLocal() as db:
        logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "chat_message_deleted",
                AuditLog.entity_id == msg_id,
            )
            .all()
        )
        assert len(logs) == 2             # документированное поведение, не баг
        for log in logs:
            assert log.user_id == s_id
            assert (log.log_metadata or {}) == {}
            assert log.description is None
