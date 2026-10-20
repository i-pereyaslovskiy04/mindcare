"""
API/integration tests для System Conversation (Stage 29b).

Покрывает: lazy-create, idempotency event_key, encryption-at-rest,
system-маппинг (_message_to_dict), read-only API, доступ только своему
получателю (включая admin/supervisor к своей беседе, но не чужой).

Требования: dev PostgreSQL на alembic head (c4f7a2e9d1b8),
DATA_ENCRYPTION_KEY в .env.
"""

import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.chat import storage as chat_storage
from app.chat.system_publisher import publish_system_message
from app.core.encryption import ENCRYPTION_PREFIX
from app.db.session import SessionLocal
from app.db.models import ChatConversation, ChatMessage

PASSWORD = "SecurePass42!"
MARKER = "СИСТЕМНОЕ-УВЕДОМЛЕНИЕ"   # кириллица: проверяем отсутствие plaintext в БД


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str = "student") -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Sys {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_sys_{role}_{_uuid.uuid4().hex[:10]}@example.com",
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


# ─── 1-3. Lazy-create / no duplicates / one per recipient ──────────────────────

class TestSystemConversationLifecycle:
    def test_lazy_create(self, client):
        _token, uid = _make_user(client)
        conv, created = chat_storage.get_or_create_system_conversation(uid)
        assert created is True
        assert conv.type == "system"
        assert conv.recipient_id == uid

    def test_get_or_create_no_duplicate(self, client):
        _token, uid = _make_user(client)
        c1, created1 = chat_storage.get_or_create_system_conversation(uid)
        c2, created2 = chat_storage.get_or_create_system_conversation(uid)
        assert created1 is True and created2 is False
        assert c1.uuid == c2.uuid

    def test_one_system_conversation_per_recipient(self, client):
        _token, uid = _make_user(client)
        publish_system_message(uid, event_key="welcome:user:x", text="A")
        publish_system_message(uid, event_key="other:event:y", text="B")
        with SessionLocal() as db:
            count = db.query(ChatConversation).filter(
                ChatConversation.type == "system",
                ChatConversation.recipient_id == uid,
            ).count()
        assert count == 1


# ─── 4. Idempotency ────────────────────────────────────────────────────────────

class TestEventKeyIdempotency:
    def test_same_event_key_no_duplicate(self, client):
        _token, uid = _make_user(client)
        key = f"welcome:user:{uid}"
        r1 = publish_system_message(uid, event_key=key, text="Привет")
        r2 = publish_system_message(uid, event_key=key, text="Привет снова")
        assert r1["created"] is True
        assert r2["created"] is False
        with SessionLocal() as db:
            conv = db.query(ChatConversation).filter(
                ChatConversation.recipient_id == uid,
            ).one()
            count = db.query(ChatMessage).filter(
                ChatMessage.conversation_id == conv.id,
            ).count()
        assert count == 1

    def test_different_event_keys_create_separate(self, client):
        _token, uid = _make_user(client)
        publish_system_message(uid, event_key="welcome:user:1", text="A")
        publish_system_message(uid, event_key="password_changed:user:1:ts", text="B")
        msgs = chat_storage.get_system_messages(uid, limit=50, before_id=None, after_id=None)
        assert len(msgs) == 2


# ─── 5. Encryption-at-rest ──────────────────────────────────────────────────────

class TestEncryptionAtRest:
    def test_db_stores_ciphertext_only(self, client):
        _token, uid = _make_user(client)
        publish_system_message(uid, event_key="welcome:user:enc", text=MARKER)
        with SessionLocal() as db:
            conv = db.query(ChatConversation).filter(
                ChatConversation.recipient_id == uid,
            ).one()
            row = db.query(ChatMessage).filter(
                ChatMessage.conversation_id == conv.id,
            ).one()
        assert row.content.startswith(ENCRYPTION_PREFIX)
        assert MARKER not in row.content
        assert row.sender_id is None
        assert row.message_kind == "system"


# ─── 6. _message_to_dict mapping ────────────────────────────────────────────────

class TestSystemMessageMapping:
    def test_system_mapping(self, client):
        _token, uid = _make_user(client)
        publish_system_message(uid, event_key="welcome:user:map", text="Текст уведомления")
        msgs = chat_storage.get_system_messages(uid, limit=50, before_id=None, after_id=None)
        assert len(msgs) == 1
        m = msgs[0]
        assert m["sender_role"] == "system"
        assert m["is_mine"] is False
        assert m["sender_id"] is None
        assert m["content"] == "Текст уведомления"   # decrypt корректный


# ─── 7-9. API: empty / messages / read ──────────────────────────────────────────

class TestSystemApi:
    def test_get_conversation_without_any_is_null(self, client):
        token, _uid = _make_user(client)
        r = client.get("/api/chat/system-conversation", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["conversation"] is None

    def test_get_messages_returns_own(self, client):
        token, uid = _make_user(client)
        publish_system_message(uid, event_key="welcome:user:api", text="Добро пожаловать")
        r = client.get(
            "/api/chat/system-conversation/messages", headers=_auth(token),
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["sender_role"] == "system"
        assert items[0]["content"] == "Добро пожаловать"

    def test_conversation_reports_unread(self, client):
        token, uid = _make_user(client)
        publish_system_message(uid, event_key="welcome:user:unread", text="X")
        r = client.get("/api/chat/system-conversation", headers=_auth(token))
        assert r.json()["conversation"]["unread_count"] == 1

    def test_read_marks_messages(self, client):
        token, uid = _make_user(client)
        publish_system_message(uid, event_key="welcome:user:read", text="X")
        r = client.post("/api/chat/system-conversation/read", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["updated_count"] == 1
        # повторно — уже 0
        r2 = client.post("/api/chat/system-conversation/read", headers=_auth(token))
        assert r2.json()["updated_count"] == 0
        r3 = client.get("/api/chat/system-conversation", headers=_auth(token))
        assert r3.json()["conversation"]["unread_count"] == 0

    def test_read_without_conversation_does_not_crash(self, client):
        token, _uid = _make_user(client)
        r = client.post("/api/chat/system-conversation/read", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["updated_count"] == 0


# ─── 10. Foreign isolation ──────────────────────────────────────────────────────

class TestForeignIsolation:
    def test_other_user_does_not_see_foreign_messages(self, client):
        token_a, uid_a = _make_user(client)
        token_b, _uid_b = _make_user(client)
        publish_system_message(uid_a, event_key="welcome:user:a", text="Только для A")

        # B запрашивает свою system-беседу — она пуста / null, чужого не видит.
        r_conv = client.get("/api/chat/system-conversation", headers=_auth(token_b))
        assert r_conv.json()["conversation"] is None
        r_msg = client.get(
            "/api/chat/system-conversation/messages", headers=_auth(token_b),
        )
        assert r_msg.json()["items"] == []


# ─── 11. No write endpoint ──────────────────────────────────────────────────────

class TestNoWriteEndpoint:
    def test_post_message_not_allowed(self, client):
        token, _uid = _make_user(client)
        r = client.post(
            "/api/chat/system-conversation/messages",
            headers=_auth(token), json={"content": "нельзя"},
        )
        # Маршрута POST .../messages нет → 405 Method Not Allowed.
        assert r.status_code == 405


# ─── 12. Staff read OWN system conversation, not foreign ────────────────────────

class TestStaffSelfAccess:
    @pytest.mark.parametrize("role", ["admin", "supervisor"])
    def test_staff_reads_own_system_conversation(self, client, role):
        token, uid = _make_user(client, role)
        publish_system_message(uid, event_key="welcome:user:staff", text="Стафф")
        r = client.get("/api/chat/system-conversation", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["conversation"] is not None
        r_msg = client.get(
            "/api/chat/system-conversation/messages", headers=_auth(token),
        )
        assert r_msg.status_code == 200
        assert len(r_msg.json()["items"]) == 1

    def test_staff_cannot_see_foreign_system_via_engagement_routes(self, client):
        # Подтверждаем: engagement-чат остаётся 403 для staff (не путь к чужому content).
        token, _uid = _make_user(client, "admin")
        r = client.get("/api/chat/conversations", headers=_auth(token))
        assert r.status_code == 403
