"""
API/integration tests for Chat MVP backend (Stage 28c).

Покрывает: lazy-create беседы, access control по engagement,
encryption-at-rest, send/read/unread, before/after пагинацию,
закрытый engagement (read-only), запрет staff-доступа, анти-spoofing
sender_id, audit без plaintext, rate limit на отправку.

Требования: dev PostgreSQL на alembic head (d8f3a6c1e9b4),
DATA_ENCRYPTION_KEY в .env.
"""

import json
import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.core.encryption import ENCRYPTION_PREFIX
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, ChatConversation, ChatMessage, TherapyEngagement,
)

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str) -> tuple[str, int]:
    """(token, user_id) для пользователя с ролью."""
    user = auth_storage.save_user({
        "name":            f"Chat {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_chatapi_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={
        "email": user["email"], "password": PASSWORD,
    })
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_engagement(student_id: int, psychologist_id: int, status: str = "active") -> int:
    with SessionLocal() as db:
        eng = TherapyEngagement(
            client_id=student_id,
            psychologist_id=psychologist_id,
            status=status,
        )
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _pair(client) -> dict:
    """student + psychologist + active engagement."""
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    eng_id = _make_engagement(s_id, p_id)
    return {
        "s_token": s_token, "s_id": s_id,
        "p_token": p_token, "p_id": p_id,
        "eng_id": eng_id,
    }


def _close_engagement(eng_id: int) -> None:
    with SessionLocal() as db:
        db.query(TherapyEngagement).filter(TherapyEngagement.id == eng_id).update(
            {"status": "completed"}, synchronize_session=False,
        )
        db.commit()


def _send_student(client, token: str, text: str) -> dict:
    r = client.post(
        "/api/chat/my-conversation/messages",
        headers=_auth(token), json={"content": text},
    )
    assert r.status_code == 201
    return r.json()


# ─── 1. Conversation lifecycle ────────────────────────────────────────────────

class TestConversationLifecycle:
    def test_student_without_engagement_gets_null(self, client):
        token, _ = _make_user(client, "student")
        r = client.get("/api/chat/my-conversation", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["conversation"] is None

    def test_student_with_engagement_gets_conversation(self, client):
        p = _pair(client)
        r = client.get("/api/chat/my-conversation", headers=_auth(p["s_token"]))
        assert r.status_code == 200
        conv = r.json()["conversation"]
        assert conv is not None
        assert conv["engagement_status"] == "active"
        assert conv["unread_count"] == 0
        assert conv["partner"]["id"] == p["p_id"]

    def test_lazy_create_no_duplicates(self, client):
        p = _pair(client)
        r1 = client.get("/api/chat/my-conversation", headers=_auth(p["s_token"]))
        r2 = client.get("/api/chat/my-conversation", headers=_auth(p["s_token"]))
        assert r1.json()["conversation"]["uuid"] == r2.json()["conversation"]["uuid"]

        with SessionLocal() as db:
            count = db.query(ChatConversation).filter(
                ChatConversation.engagement_id == p["eng_id"]
            ).count()
        assert count == 1

    def test_conversation_created_audit_without_plaintext(self, client):
        p = _pair(client)
        r = client.get("/api/chat/my-conversation", headers=_auth(p["s_token"]))
        conv_uuid = r.json()["conversation"]["uuid"]

        with SessionLocal() as db:
            conv = (
                db.query(ChatConversation)
                .filter(ChatConversation.uuid == conv_uuid)
                .first()
            )
            events = db.query(AuditLog).filter(
                AuditLog.event_type == "chat_conversation_created",
                AuditLog.user_id == p["s_id"],
            ).all()
            assert len(events) == 1
            ev = events[0]
            assert ev.entity_type == "chat_conversation"
            # Stage 4B-3: metadata больше не пишется (engagement_id удалён из
            # metadata) — target определяется только через entity_id.
            assert ev.entity_id == conv.id
            assert (ev.log_metadata or {}) == {}
            assert ev.description is None
            assert ev.user_role == "student"

    def test_psychologist_cannot_trigger_conversation_creation(self, client):
        # Stage 4B-3: psychologist-инициированного создания беседы не существует
        # (_resolve_psychologist_conversation только ищет существующую — 404
        # если её нет). Без визита студента на my-conversation беседа не
        # создаётся вовсе, поэтому chat_conversation_created с actor role
        # "psychologist" никогда не пишется.
        p = _pair(client)
        r = client.get("/api/chat/conversations", headers=_auth(p["p_token"]))
        assert r.status_code == 200
        assert r.json()["total"] == 0

        with SessionLocal() as db:
            count = db.query(ChatConversation).filter(
                ChatConversation.engagement_id == p["eng_id"]
            ).count()
            assert count == 0
            events = db.query(AuditLog).filter(
                AuditLog.event_type == "chat_conversation_created",
                AuditLog.user_id == p["p_id"],
            ).all()
            assert events == []


# ─── 2. Messaging + encryption ────────────────────────────────────────────────

class TestMessaging:
    def test_student_sends_and_db_stores_ciphertext(self, client):
        p = _pair(client)
        secret = f"приватное-сообщение-{_uuid.uuid4().hex[:8]}"
        msg = _send_student(client, p["s_token"], secret)

        assert msg["content"] == secret        # отправителю — plaintext
        assert msg["is_mine"] is True
        assert msg["sender_role"] == "student"

        with SessionLocal() as db:
            stored = db.query(ChatMessage.content).filter(
                ChatMessage.uuid == msg["uuid"]
            ).scalar()
        assert stored.startswith(ENCRYPTION_PREFIX)
        assert secret not in stored

    def test_participant_reads_decrypted_content(self, client):
        p = _pair(client)
        secret = f"для-психолога-{_uuid.uuid4().hex[:8]}"
        _send_student(client, p["s_token"], secret)

        r = client.get("/api/chat/conversations", headers=_auth(p["p_token"]))
        conv_uuid = r.json()["items"][0]["uuid"]

        r = client.get(
            f"/api/chat/conversations/{conv_uuid}/messages",
            headers=_auth(p["p_token"]),
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert items[-1]["content"] == secret
        assert items[-1]["is_mine"] is False
        assert items[-1]["sender_role"] == "student"

    def test_psychologist_sends_message(self, client):
        p = _pair(client)
        _send_student(client, p["s_token"], "привет")  # создаёт беседу

        r = client.get("/api/chat/conversations", headers=_auth(p["p_token"]))
        conv_uuid = r.json()["items"][0]["uuid"]

        r = client.post(
            f"/api/chat/conversations/{conv_uuid}/messages",
            headers=_auth(p["p_token"]), json={"content": "Здравствуйте!"},
        )
        assert r.status_code == 201
        assert r.json()["sender_role"] == "psychologist"

        # студент видит ответ
        r = client.get(
            "/api/chat/my-conversation/messages", headers=_auth(p["s_token"]),
        )
        contents = [m["content"] for m in r.json()["items"]]
        assert "Здравствуйте!" in contents

    def test_sender_id_cannot_be_spoofed(self, client):
        p = _pair(client)
        r = client.post(
            "/api/chat/my-conversation/messages",
            headers=_auth(p["s_token"]),
            json={"content": "spoof", "sender_id": p["p_id"]},  # лишнее поле
        )
        assert r.status_code == 201
        assert r.json()["sender_id"] == p["s_id"]   # всегда из сессии

    def test_empty_content_rejected(self, client):
        p = _pair(client)
        r = client.post(
            "/api/chat/my-conversation/messages",
            headers=_auth(p["s_token"]), json={"content": "   "},
        )
        assert r.status_code == 422


# ─── 3. Access control ────────────────────────────────────────────────────────

class TestAccessControl:
    def test_foreign_student_cannot_see_conversation(self, client):
        p = _pair(client)
        _send_student(client, p["s_token"], "моё")

        other_token, _ = _make_user(client, "student")
        r = client.get("/api/chat/my-conversation", headers=_auth(other_token))
        assert r.json()["conversation"] is None
        r = client.get(
            "/api/chat/my-conversation/messages", headers=_auth(other_token),
        )
        assert r.status_code == 404

    def test_foreign_psychologist_cannot_see_conversation(self, client):
        p = _pair(client)
        _send_student(client, p["s_token"], "моё")
        conv_uuid = client.get(
            "/api/chat/conversations", headers=_auth(p["p_token"]),
        ).json()["items"][0]["uuid"]

        other_token, _ = _make_user(client, "psychologist")
        r = client.get("/api/chat/conversations", headers=_auth(other_token))
        assert r.json()["total"] == 0
        r = client.get(
            f"/api/chat/conversations/{conv_uuid}", headers=_auth(other_token),
        )
        assert r.status_code == 404
        r = client.get(
            f"/api/chat/conversations/{conv_uuid}/messages",
            headers=_auth(other_token),
        )
        assert r.status_code == 404

    @pytest.mark.parametrize("role", ["admin", "supervisor"])
    def test_staff_has_no_chat_access(self, client, role):
        token, _ = _make_user(client, role)
        assert client.get(
            "/api/chat/my-conversation", headers=_auth(token),
        ).status_code == 403
        assert client.get(
            "/api/chat/conversations", headers=_auth(token),
        ).status_code == 403
        assert client.get(
            f"/api/chat/conversations/{_uuid.uuid4()}/messages",
            headers=_auth(token),
        ).status_code == 403


# ─── 4. Closed engagement: read-only ─────────────────────────────────────────

class TestClosedEngagement:
    def test_history_readable_but_writes_409(self, client):
        p = _pair(client)
        _send_student(client, p["s_token"], "до закрытия")
        conv_uuid = client.get(
            "/api/chat/conversations", headers=_auth(p["p_token"]),
        ).json()["items"][0]["uuid"]

        _close_engagement(p["eng_id"])

        # читать можно обоим
        r = client.get(
            "/api/chat/my-conversation/messages", headers=_auth(p["s_token"]),
        )
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1
        r = client.get(
            f"/api/chat/conversations/{conv_uuid}/messages",
            headers=_auth(p["p_token"]),
        )
        assert r.status_code == 200

        # писать нельзя никому
        r = client.post(
            "/api/chat/my-conversation/messages",
            headers=_auth(p["s_token"]), json={"content": "после"},
        )
        assert r.status_code == 409
        r = client.post(
            f"/api/chat/conversations/{conv_uuid}/messages",
            headers=_auth(p["p_token"]), json={"content": "после"},
        )
        assert r.status_code == 409


# ─── 5. Read / unread ─────────────────────────────────────────────────────────

class TestReadUnread:
    def test_read_marks_only_incoming_and_unread_drops(self, client):
        p = _pair(client)
        _send_student(client, p["s_token"], "раз")
        _send_student(client, p["s_token"], "два")

        # у психолога 2 непрочитанных
        items = client.get(
            "/api/chat/conversations", headers=_auth(p["p_token"]),
        ).json()["items"]
        assert items[0]["unread_count"] == 2
        conv_uuid = items[0]["uuid"]

        r = client.post(
            f"/api/chat/conversations/{conv_uuid}/read", headers=_auth(p["p_token"]),
        )
        assert r.json()["updated_count"] == 2

        # unread обнулился; свои сообщения студента не тронуты (read_at у
        # них проставлен прочтением психолога — это и есть входящие)
        items = client.get(
            "/api/chat/conversations", headers=_auth(p["p_token"]),
        ).json()["items"]
        assert items[0]["unread_count"] == 0

        # повторный read — ничего не обновляет
        r = client.post(
            f"/api/chat/conversations/{conv_uuid}/read", headers=_auth(p["p_token"]),
        )
        assert r.json()["updated_count"] == 0

    def test_own_messages_not_marked_by_own_read(self, client):
        p = _pair(client)
        msg = _send_student(client, p["s_token"], "своё сообщение")

        r = client.post(
            "/api/chat/my-conversation/read", headers=_auth(p["s_token"]),
        )
        assert r.json()["updated_count"] == 0   # входящих нет

        with SessionLocal() as db:
            read_at = db.query(ChatMessage.read_at).filter(
                ChatMessage.uuid == msg["uuid"]
            ).scalar()
        assert read_at is None


# ─── 6. Pagination ────────────────────────────────────────────────────────────

class TestPagination:
    def test_after_returns_only_new_messages(self, client):
        p = _pair(client)
        m1 = _send_student(client, p["s_token"], "первое")
        m2 = _send_student(client, p["s_token"], "второе")
        m3 = _send_student(client, p["s_token"], "третье")

        r = client.get(
            f"/api/chat/my-conversation/messages?after={m2['id']}",
            headers=_auth(p["s_token"]),
        )
        items = r.json()["items"]
        assert [m["uuid"] for m in items] == [m3["uuid"]]

        # poll без новых сообщений — пусто
        r = client.get(
            f"/api/chat/my-conversation/messages?after={m3['id']}",
            headers=_auth(p["s_token"]),
        )
        assert r.json()["items"] == []
        assert m1["id"] < m2["id"] < m3["id"]

    def test_before_returns_history(self, client):
        p = _pair(client)
        m1 = _send_student(client, p["s_token"], "старое-1")
        m2 = _send_student(client, p["s_token"], "старое-2")
        m3 = _send_student(client, p["s_token"], "новое")

        r = client.get(
            f"/api/chat/my-conversation/messages?before={m3['id']}&limit=2",
            headers=_auth(p["s_token"]),
        )
        items = r.json()["items"]
        assert [m["uuid"] for m in items] == [m1["uuid"], m2["uuid"]]

    def test_default_returns_latest_ascending(self, client):
        p = _pair(client)
        for i in range(3):
            _send_student(client, p["s_token"], f"msg-{i}")

        r = client.get(
            "/api/chat/my-conversation/messages?limit=2",
            headers=_auth(p["s_token"]),
        )
        contents = [m["content"] for m in r.json()["items"]]
        assert contents == ["msg-1", "msg-2"]   # последние, по возрастанию


# ─── 7. Rate limit на отправку ───────────────────────────────────────────────

class TestSendRateLimit:
    def test_send_limit_429(self, client, monkeypatch):
        monkeypatch.setattr("app.chat.routes.CHAT_SEND_LIMIT", (3, 60))
        p = _pair(client)

        for i in range(3):
            _send_student(client, p["s_token"], f"ok-{i}")

        r = client.post(
            "/api/chat/my-conversation/messages",
            headers=_auth(p["s_token"]), json={"content": "превышение"},
        )
        assert r.status_code == 429
