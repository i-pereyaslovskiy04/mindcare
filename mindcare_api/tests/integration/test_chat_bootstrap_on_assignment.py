"""
Stage 31o — Messenger conversation bootstrap on psychologist assign/transfer.

assign_psychologist / transfer_psychologist теперь создают engagement-беседу
в той же транзакции, что и engagement. Новый психолог видит пустой диалог
сразу, без ленивого bootstrap со стороны студента.

Requires dev PostgreSQL on alembic head + DATA_ENCRYPTION_KEY.
cleanup_test_records (conftest) удаляет integ_*@example.com и их беседы.
"""

import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.supervisor import service as sup_service
from app.db.session import SessionLocal
from app.db.models import ChatConversation, ChatMessage, TherapyEngagement

PASSWORD = "SecurePass42!"


def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Boot {role} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_boot_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ─── A. Assignment creates an empty, immediately-visible conversation ─────────

def test_assignment_creates_empty_conversation_visible_to_psychologist(client):
    _s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    _sup_token, sup_id = _make_user(client, "supervisor")

    result = sup_service.assign_psychologist(
        client_id=s_id, psychologist_id=p_id, primary_concern=None,
        actor_id=sup_id, actor_role="supervisor",
    )
    eng_id = result["id"]

    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.engagement_id == eng_id)
            .first()
        )
        assert conv is not None
        assert conv.type == "engagement"
        conv_uuid = str(conv.uuid)
        msg_count = (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv.id)
            .count()
        )
        assert msg_count == 0                       # пустой диалог

    # C: psychologist list endpoint возвращает пустой диалог (last_message_at null)
    r = client.get("/api/chat/conversations", headers=_auth(p_token))
    assert r.status_code == 200
    items = r.json()["items"]
    item = next((it for it in items if it["uuid"] == conv_uuid), None)
    assert item is not None
    assert item["last_message_at"] is None
    assert item["unread_count"] == 0
    assert item["engagement_status"] == "active"
    assert item["student"]["id"] == s_id


# ─── B. Transfer creates a new conversation for the new psychologist ──────────

def test_transfer_creates_new_conversation_for_new_psychologist(client):
    _s_token, s_id = _make_user(client, "student")
    _p1_token, p1_id = _make_user(client, "psychologist")
    p2_token, p2_id = _make_user(client, "psychologist")
    _sup_token, sup_id = _make_user(client, "supervisor")

    assigned = sup_service.assign_psychologist(
        client_id=s_id, psychologist_id=p1_id, primary_concern="тревога",
        actor_id=sup_id, actor_role="supervisor",
    )
    old_eng_id = assigned["id"]

    transferred = sup_service.transfer_psychologist(
        engagement_id=old_eng_id, new_psychologist_id=p2_id,
        transfer_reason="смена специалиста", actor_id=sup_id, actor_role="supervisor",
    )
    new_eng_id = transferred["id"]
    assert transferred["status"] == "active"
    assert new_eng_id != old_eng_id

    with SessionLocal() as db:
        old = db.query(TherapyEngagement).filter_by(id=old_eng_id).first()
        new = db.query(TherapyEngagement).filter_by(id=new_eng_id).first()
        assert old.status == "transferred"
        assert new.status == "active"
        new_conv = (
            db.query(ChatConversation)
            .filter(ChatConversation.engagement_id == new_eng_id)
            .first()
        )
        assert new_conv is not None
        new_conv_uuid = str(new_conv.uuid)

    # новый психолог сразу видит новый пустой диалог
    r = client.get("/api/chat/conversations", headers=_auth(p2_token))
    assert r.status_code == 200
    uuids = [it["uuid"] for it in r.json()["items"]]
    assert new_conv_uuid in uuids


# ─── D. Old psychologist cannot write to transferred engagement ───────────────

def test_old_psychologist_cannot_write_after_transfer(client):
    _s_token, s_id = _make_user(client, "student")
    p1_token, p1_id = _make_user(client, "psychologist")
    _p2_token, p2_id = _make_user(client, "psychologist")
    _sup_token, sup_id = _make_user(client, "supervisor")

    assigned = sup_service.assign_psychologist(
        client_id=s_id, psychologist_id=p1_id, primary_concern=None,
        actor_id=sup_id, actor_role="supervisor",
    )
    old_eng_id = assigned["id"]
    with SessionLocal() as db:
        old_conv_uuid = str(
            db.query(ChatConversation)
            .filter(ChatConversation.engagement_id == old_eng_id)
            .first().uuid
        )

    sup_service.transfer_psychologist(
        engagement_id=old_eng_id, new_psychologist_id=p2_id,
        transfer_reason=None, actor_id=sup_id, actor_role="supervisor",
    )

    # старую (transferred) беседу старый психолог ещё может читать (история)
    r_read = client.get(
        f"/api/chat/conversations/{old_conv_uuid}/messages", headers=_auth(p1_token),
    )
    assert r_read.status_code == 200

    # но запись в transferred engagement запрещена → 409
    r_write = client.post(
        f"/api/chat/conversations/{old_conv_uuid}/messages",
        headers=_auth(p1_token), json={"content": "после перевода"},
    )
    assert r_write.status_code == 409


# ─── E. Rollback safety: conversation failure rolls back the engagement ───────

def test_assign_rolls_back_engagement_when_conversation_fails(client, monkeypatch):
    _s_token, s_id = _make_user(client, "student")
    _p_token, p_id = _make_user(client, "psychologist")
    _sup_token, sup_id = _make_user(client, "supervisor")

    def boom(db, engagement_id):
        raise RuntimeError("inject: conversation creation failed")

    # supervisor.service вызывает chat_storage.ensure_engagement_conversation
    monkeypatch.setattr(
        "app.chat.storage.ensure_engagement_conversation", boom,
    )

    with pytest.raises(RuntimeError, match="inject: conversation"):
        sup_service.assign_psychologist(
            client_id=s_id, psychologist_id=p_id, primary_concern=None,
            actor_id=sup_id, actor_role="supervisor",
        )

    # engagement НЕ должен остаться созданным без беседы (откатился вместе с tx)
    with SessionLocal() as db:
        eng = (
            db.query(TherapyEngagement)
            .filter(TherapyEngagement.client_id == s_id)
            .first()
        )
        assert eng is None
