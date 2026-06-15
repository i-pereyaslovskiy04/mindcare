"""
API/integration tests for chat presence (online/offline) — Stage 30c.

Презенс — приблизительный MVP по user_sessions.last_active (без real-time):
пользователь online, если у него есть активная (не revoked, не expired) сессия
с last_active не старше ONLINE_THRESHOLD_SECONDS (10 минут).

Требования: dev PostgreSQL на alembic head, DATA_ENCRYPTION_KEY в .env.
"""

import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt

from app.auth import storage as auth_storage
from app.chat import storage as chat_storage
from app.db.session import SessionLocal
from app.db.models import TherapyEngagement, UserSession

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str, *, login: bool = True) -> tuple[str | None, int]:
    """(token|None, user_id). login=False — пользователь без сессии (offline)."""
    user = auth_storage.save_user({
        "name":            f"Presence {role} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_presence_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            role,
    })
    if not login:
        return None, int(user["id"])
    r = client.post("/api/auth/login", json={"email": user["email"], "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_engagement(student_id: int, psychologist_id: int, status: str = "active") -> int:
    with SessionLocal() as db:
        eng = TherapyEngagement(
            client_id=student_id, psychologist_id=psychologist_id, status=status,
        )
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _age_sessions(user_id: int, *, seconds_ago: int) -> None:
    """Состарить last_active всех сессий пользователя (имитация неактивности)."""
    old = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    with SessionLocal() as db:
        db.query(UserSession).filter(UserSession.user_id == user_id).update(
            {"last_active": old}, synchronize_session=False,
        )
        db.commit()


def _revoke_sessions(user_id: int) -> None:
    with SessionLocal() as db:
        db.query(UserSession).filter(UserSession.user_id == user_id).update(
            {"is_revoked": True}, synchronize_session=False,
        )
        db.commit()


# ─── 1. Storage helper (правило вычисления) ──────────────────────────────────

class TestPresenceRule:
    def test_fresh_session_is_online(self, client):
        _, uid = _make_user(client, "student")
        assert chat_storage.is_user_online(uid) is True

    def test_old_last_active_is_offline(self, client):
        _, uid = _make_user(client, "student")
        _age_sessions(uid, seconds_ago=chat_storage.ONLINE_THRESHOLD_SECONDS + 120)
        assert chat_storage.is_user_online(uid) is False

    def test_no_session_is_offline(self, client):
        _, uid = _make_user(client, "student", login=False)
        assert chat_storage.is_user_online(uid) is False

    def test_revoked_session_is_offline(self, client):
        _, uid = _make_user(client, "student")
        _revoke_sessions(uid)
        assert chat_storage.is_user_online(uid) is False

    def test_batch_returns_only_online(self, client):
        _, online_id = _make_user(client, "student")
        _, offline_id = _make_user(client, "student")
        _age_sessions(offline_id, seconds_ago=chat_storage.ONLINE_THRESHOLD_SECONDS + 120)
        result = chat_storage.get_online_user_ids([online_id, offline_id])
        assert online_id in result
        assert offline_id not in result

    def test_empty_input(self, client):
        assert chat_storage.get_online_user_ids([]) == set()


# ─── 2. Student sees psychologist presence ───────────────────────────────────

class TestStudentSeesPsychologist:
    def test_my_conversation_peer_online(self, client):
        s_token, s_id = _make_user(client, "student")
        _, p_id = _make_user(client, "psychologist")
        _make_engagement(s_id, p_id)

        r = client.get("/api/chat/my-conversation", headers=_auth(s_token))
        assert r.status_code == 200
        conv = r.json()["conversation"]
        assert conv is not None
        assert conv["peer_is_online"] is True

    def test_my_conversation_peer_offline(self, client):
        s_token, s_id = _make_user(client, "student")
        _, p_id = _make_user(client, "psychologist")
        _make_engagement(s_id, p_id)
        _age_sessions(p_id, seconds_ago=chat_storage.ONLINE_THRESHOLD_SECONDS + 120)

        r = client.get("/api/chat/my-conversation", headers=_auth(s_token))
        conv = r.json()["conversation"]
        assert conv["peer_is_online"] is False


# ─── 3. Psychologist sees client presence ────────────────────────────────────

class TestPsychologistSeesClient:
    def test_list_peer_online(self, client):
        s_token, s_id = _make_user(client, "student")
        p_token, p_id = _make_user(client, "psychologist")
        _make_engagement(s_id, p_id)
        # беседа создаётся лениво — инициируем её обращением студента
        client.get("/api/chat/my-conversation", headers=_auth(s_token))

        r = client.get("/api/chat/conversations", headers=_auth(p_token))
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["peer_is_online"] is True

    def test_list_peer_offline(self, client):
        s_token, s_id = _make_user(client, "student")
        p_token, p_id = _make_user(client, "psychologist")
        _make_engagement(s_id, p_id)
        client.get("/api/chat/my-conversation", headers=_auth(s_token))
        _age_sessions(s_id, seconds_ago=chat_storage.ONLINE_THRESHOLD_SECONDS + 120)

        items = client.get(
            "/api/chat/conversations", headers=_auth(p_token),
        ).json()["items"]
        assert items[0]["peer_is_online"] is False

    def test_get_conversation_peer_online(self, client):
        s_token, s_id = _make_user(client, "student")
        p_token, p_id = _make_user(client, "psychologist")
        _make_engagement(s_id, p_id)
        conv_uuid = client.get(
            "/api/chat/my-conversation", headers=_auth(s_token),
        ).json()["conversation"]["uuid"]

        r = client.get(
            f"/api/chat/conversations/{conv_uuid}", headers=_auth(p_token),
        )
        assert r.status_code == 200
        assert r.json()["peer_is_online"] is True


# ─── 4. System conversation has no human presence ────────────────────────────

class TestSystemConversationNoPresence:
    def test_system_conversation_has_no_peer_online(self, client):
        token, uid = _make_user(client, "student")
        # создаём system-беседу с одним сообщением напрямую через storage
        chat_storage.create_system_message(
            uid, event_key=f"welcome:user:{uid}", text="Добро пожаловать",
        )

        r = client.get("/api/chat/system-conversation", headers=_auth(token))
        assert r.status_code == 200
        conv = r.json()["conversation"]
        assert conv is not None
        assert conv["type"] == "system"
        assert "peer_is_online" not in conv
