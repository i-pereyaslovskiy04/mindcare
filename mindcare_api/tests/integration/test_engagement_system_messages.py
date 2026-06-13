"""
Integration tests: system messages для событий therapy engagement (Stage 29d).

Проверяет, что назначение/смена/закрытие психолога публикуют read-only
system-сообщение студенту через app/chat/system_publisher.py:
  engagement_assigned / engagement_transferred / engagement_closed.

Идемпотентность по event_key, encryption-at-rest, доступ только получателю.

Требования: dev PostgreSQL на alembic head (c4f7a2e9d1b8), DATA_ENCRYPTION_KEY.
"""

import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.chat.system_publisher import publish_system_message
from app.core.encryption import ENCRYPTION_PREFIX
from app.supervisor import service as supervisor_service
from app.db.session import SessionLocal
from app.db.models import ChatConversation, ChatMessage, User

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str) -> tuple[str, int]:
    user = auth_storage.save_user({
        "name":            f"Eng {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_engsys_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _full_name(user_id: int) -> str:
    with SessionLocal() as db:
        return db.query(User.full_name).filter(User.id == user_id).scalar()


def _system_rows(recipient_id: int) -> list[ChatMessage]:
    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(
                ChatConversation.type == "system",
                ChatConversation.recipient_id == recipient_id,
            )
            .first()
        )
        if conv is None:
            return []
        return (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conv.id)
            .all()
        )


def _api_messages(client, token: str) -> list[dict]:
    r = client.get("/api/chat/system-conversation/messages", headers=_auth(token))
    assert r.status_code == 200
    return r.json()["items"]


def _assign(client):
    s_token, s_id = _make_user(client, "student")
    p_token, p_id = _make_user(client, "psychologist")
    _sv_token, sv_id = _make_user(client, "supervisor")
    eng = supervisor_service.assign_psychologist(
        client_id=s_id, psychologist_id=p_id,
        primary_concern=None, actor_id=sv_id, actor_role="supervisor",
    )
    return {
        "s_token": s_token, "s_id": s_id,
        "p_token": p_token, "p_id": p_id,
        "sv_id": sv_id, "eng_id": eng["id"],
    }


# ─── Assignment ─────────────────────────────────────────────────────────────────

class TestAssignment:
    def test_assignment_creates_system_message(self, client):
        ctx = _assign(client)
        key = f"engagement_assigned:engagement:{ctx['eng_id']}"
        rows = _system_rows(ctx["s_id"])
        assert len(rows) == 1
        assert rows[0].event_key == key
        assert rows[0].message_kind == "system"
        assert rows[0].sender_id is None

    def test_assignment_encrypted_at_rest(self, client):
        ctx = _assign(client)
        psych_name = _full_name(ctx["p_id"])
        rows = _system_rows(ctx["s_id"])
        assert rows[0].content.startswith(ENCRYPTION_PREFIX)
        assert psych_name not in rows[0].content        # plaintext имени нет в БД

    def test_student_sees_assignment_plaintext(self, client):
        ctx = _assign(client)
        psych_name = _full_name(ctx["p_id"])
        items = _api_messages(client, ctx["s_token"])
        assert len(items) == 1
        assert items[0]["sender_role"] == "system"
        assert items[0]["content"] == f"Вам назначен психолог: {psych_name}."

    def test_assignment_idempotent(self, client):
        ctx = _assign(client)
        key = f"engagement_assigned:engagement:{ctx['eng_id']}"
        # повторная публикация того же event_key не создаёт дубль
        res = publish_system_message(ctx["s_id"], event_key=key, text="дубль")
        assert res["created"] is False
        assert len(_system_rows(ctx["s_id"])) == 1


# ─── Transfer ───────────────────────────────────────────────────────────────────

class TestTransfer:
    def test_transfer_creates_system_message(self, client):
        ctx = _assign(client)
        _np_token, np_id = _make_user(client, "psychologist")
        new = supervisor_service.transfer_psychologist(
            engagement_id=ctx["eng_id"], new_psychologist_id=np_id,
            transfer_reason=None, actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        new_name = _full_name(np_id)
        items = _api_messages(client, ctx["s_token"])
        texts = [m["content"] for m in items]
        assert f"Ваш психолог изменён: {new_name}." in texts
        keys = {r.event_key for r in _system_rows(ctx["s_id"])}
        assert f"engagement_transferred:engagement:{new['id']}" in keys

    def test_transfer_idempotent(self, client):
        ctx = _assign(client)
        _np_token, np_id = _make_user(client, "psychologist")
        new = supervisor_service.transfer_psychologist(
            engagement_id=ctx["eng_id"], new_psychologist_id=np_id,
            transfer_reason=None, actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        key = f"engagement_transferred:engagement:{new['id']}"
        before = len(_system_rows(ctx["s_id"]))
        res = publish_system_message(ctx["s_id"], event_key=key, text="дубль")
        assert res["created"] is False
        assert len(_system_rows(ctx["s_id"])) == before


# ─── Close ──────────────────────────────────────────────────────────────────────

class TestClose:
    def test_close_creates_system_message(self, client):
        ctx = _assign(client)
        supervisor_service.close_engagement(
            engagement_id=ctx["eng_id"], reason="по завершении",
            actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        items = _api_messages(client, ctx["s_token"])
        texts = [m["content"] for m in items]
        assert "Консультационная связь с психологом закрыта." in texts
        # reason не раскрывается в тексте
        assert all("завершении" not in t for t in texts)
        keys = {r.event_key for r in _system_rows(ctx["s_id"])}
        assert f"engagement_closed:engagement:{ctx['eng_id']}" in keys

    def test_close_idempotent(self, client):
        ctx = _assign(client)
        supervisor_service.close_engagement(
            engagement_id=ctx["eng_id"], reason=None,
            actor_id=ctx["sv_id"], actor_role="supervisor",
        )
        key = f"engagement_closed:engagement:{ctx['eng_id']}"
        before = len(_system_rows(ctx["s_id"]))
        res = publish_system_message(ctx["s_id"], event_key=key, text="дубль")
        assert res["created"] is False
        assert len(_system_rows(ctx["s_id"])) == before


# ─── Access / privacy ───────────────────────────────────────────────────────────

class TestAccessPrivacy:
    def test_other_student_does_not_see_assignment(self, client):
        ctx = _assign(client)
        other_token, _other_id = _make_user(client, "student")
        r = client.get("/api/chat/system-conversation", headers=_auth(other_token))
        assert r.json()["conversation"] is None
        assert _api_messages(client, other_token) == []

    def test_psychologist_does_not_see_student_assignment(self, client):
        ctx = _assign(client)
        # У психолога своей system-беседы нет → null, и текста назначения он не видит.
        r = client.get("/api/chat/system-conversation", headers=_auth(ctx["p_token"]))
        assert r.json()["conversation"] is None
        assert _api_messages(client, ctx["p_token"]) == []

    def test_supervisor_actor_does_not_see_student_assignment(self, client):
        ctx = _assign(client)
        items = _api_messages(client, _sv_login(client, ctx["sv_id"]))
        assert all("назначен психолог" not in m["content"] for m in items)


def _sv_login(client, sv_id: int) -> str:
    """Логин супервизора по его id (нужен свежий токен в рамках теста)."""
    with SessionLocal() as db:
        email = db.query(User.email).filter(User.id == sv_id).scalar()
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"]
