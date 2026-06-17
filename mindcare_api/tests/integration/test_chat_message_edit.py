"""
Stage 31x-fix — редактирование своих сообщений Messenger (PATCH).

Политика: своё user-сообщение, только в active engagement, без time-limit;
system/чужие/удалённые — нельзя; content остаётся encrypted-at-rest; audit
chat_message_edited без plaintext.

Requires dev PostgreSQL on alembic head + DATA_ENCRYPTION_KEY.
"""

import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt

from app.auth import storage as auth_storage
from app.core.encryption import ENCRYPTION_PREFIX, encrypt_text
from app.supervisor import service as sup
from app.db.session import SessionLocal
from app.db.models import AuditLog, ChatConversation, ChatMessage

PASSWORD = "SecurePass42!"


def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Edit {role} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_edit_{role}_{_uuid.uuid4().hex[:10]}@example.com",
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


def _student_edit(client, token, conv, msg_uuid, text):
    return client.patch(
        f"/api/chat/student/conversations/{conv}/messages/{msg_uuid}",
        headers=_auth(token), json={"content": text},
    )


def _psych_edit(client, token, conv, msg_uuid, text):
    return client.patch(
        f"/api/chat/conversations/{conv}/messages/{msg_uuid}",
        headers=_auth(token), json={"content": text},
    )


def _setup_active(client):
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    _sv, sup_id = _make_user(client, "supervisor")
    eng = _assign(s_id, p_id, sup_id)
    conv = _conv_uuid(eng["id"])
    return s_token, s_id, p_token, p_id, sup_id, eng, conv


# ─── A / I / J. student edits own message → encrypted at rest, edited_at set ──

def test_student_edits_own_message(client):
    s_token, _s_id, *_rest, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "первый вариант")

    r = _student_edit(client, s_token, conv, sent["uuid"], "исправленный текст")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == "исправленный текст"   # J: decrypted updated content
    assert body["edited_at"] is not None             # A: edited_at not null
    assert body["uuid"] == sent["uuid"]

    # I: в БД хранится только enc:v1:, plaintext отсутствует
    with SessionLocal() as db:
        row = db.query(ChatMessage).filter(ChatMessage.uuid == sent["uuid"]).one()
        assert row.content.startswith(ENCRYPTION_PREFIX)
        assert "исправленный текст" not in row.content
        assert "первый вариант" not in row.content
        assert row.edited_at is not None


# ─── B. psychologist edits own message ────────────────────────────────────────

def test_psychologist_edits_own_message(client):
    _s_token, _s_id, p_token, _p_id, *_rest, conv = _setup_active(client)
    sent = _psych_send(client, p_token, conv, "psy v1")
    r = _psych_edit(client, p_token, conv, sent["uuid"], "psy v2")
    assert r.status_code == 200, r.text
    assert r.json()["content"] == "psy v2"
    assert r.json()["edited_at"] is not None


# ─── C. student cannot edit psychologist's message → 404 ──────────────────────

def test_student_cannot_edit_psychologist_message(client):
    s_token, _s_id, p_token, _p_id, *_rest, conv = _setup_active(client)
    psy_msg = _psych_send(client, p_token, conv, "сообщение психолога")
    r = _student_edit(client, s_token, conv, psy_msg["uuid"], "взлом")
    assert r.status_code == 404
    # содержимое не изменилось
    with SessionLocal() as db:
        from app.core.encryption import decrypt_text
        row = db.query(ChatMessage).filter(ChatMessage.uuid == psy_msg["uuid"]).one()
        assert decrypt_text(row.content) == "сообщение психолога"
        assert row.edited_at is None


# ─── D. psychologist cannot edit student's message → 404 ──────────────────────

def test_psychologist_cannot_edit_student_message(client):
    s_token, _s_id, p_token, _p_id, *_rest, conv = _setup_active(client)
    stu_msg = _student_send(client, s_token, conv, "сообщение студента")
    r = _psych_edit(client, p_token, conv, stu_msg["uuid"], "правка психологом")
    assert r.status_code == 404


# ─── E. cannot edit system message (даже если оно в engagement-беседе) → 404 ──

def test_cannot_edit_system_message(client):
    s_token, _s_id, *_rest, eng, conv = _setup_active(client)
    # Вставляем system-kind сообщение прямо в engagement-беседу (контрол-кейс guard).
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

    r = _student_edit(client, s_token, conv, sys_uuid, "правка системного")
    assert r.status_code == 404


# ─── F. cannot edit message in transferred (inactive) engagement → 409 ────────

def test_cannot_edit_in_closed_engagement(client):
    s_token, s_id, _p_token, p_id, sup_id, eng, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "до перевода")

    _y, y_id = _make_user(client, "psychologist")
    _transfer(eng["id"], y_id, sup_id)   # eng (X) становится transferred → не active

    r = _student_edit(client, s_token, conv, sent["uuid"], "после перевода")
    assert r.status_code == 409


# ─── G. cannot edit deleted message → 404 ─────────────────────────────────────

def test_cannot_edit_deleted_message(client):
    s_token, _s_id, *_rest, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "будет удалено")
    with SessionLocal() as db:
        db.query(ChatMessage).filter(ChatMessage.uuid == sent["uuid"]).update(
            {"deleted_at": datetime.now(timezone.utc)}, synchronize_session=False,
        )
        db.commit()
    r = _student_edit(client, s_token, conv, sent["uuid"], "поздно")
    assert r.status_code == 404


# ─── H. empty / too long content ────────────────────────────────────────────────
# Stage 32g: whitespace-only content без вложений → 400 from storage (would_be_empty);
# ранее было 422 от schema, теперь схема принимает "" и делегирует проверку storage.

def test_edit_validation(client):
    s_token, _s_id, *_rest, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "норм")
    assert _student_edit(client, s_token, conv, sent["uuid"], "   ").status_code == 400
    assert _student_edit(
        client, s_token, conv, sent["uuid"], "x" * 10001,
    ).status_code == 422


# ─── K. audit chat_message_edited без plaintext ───────────────────────────────

def test_audit_event_without_plaintext(client):
    s_token, _s_id, *_rest, conv = _setup_active(client)
    secret_old = "СЕКРЕТ-СТАРЫЙ-uniq"
    secret_new = "СЕКРЕТ-НОВЫЙ-uniq"
    sent = _student_send(client, s_token, conv, secret_old)
    r = _student_edit(client, s_token, conv, sent["uuid"], secret_new)
    assert r.status_code == 200
    msg_id = r.json()["id"]

    with SessionLocal() as db:
        logs = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "chat_message_edited",
                AuditLog.entity_id == msg_id,
            )
            .all()
        )
        assert logs, "audit chat_message_edited не создан"
        for log in logs:
            blob = f"{log.description} {log.log_metadata}"
            assert secret_old not in blob
            assert secret_new not in blob
            assert ENCRYPTION_PREFIX not in blob


# ─── L. edit «старого» сообщения в active chat — без ограничения по времени ───

def test_edit_old_message_no_time_limit(client):
    s_token, _s_id, *_rest, conv = _setup_active(client)
    sent = _student_send(client, s_token, conv, "старое")
    # искусственно состариваем сообщение на 30 дней
    with SessionLocal() as db:
        db.query(ChatMessage).filter(ChatMessage.uuid == sent["uuid"]).update(
            {"created_at": datetime.now(timezone.utc) - timedelta(days=30)},
            synchronize_session=False,
        )
        db.commit()
    r = _student_edit(client, s_token, conv, sent["uuid"], "правка старого")
    assert r.status_code == 200
    assert r.json()["content"] == "правка старого"
