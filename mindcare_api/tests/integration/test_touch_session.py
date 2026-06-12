"""
Integration tests for touch_session debounce (Stage 26).

Доказывает:
  - last_active обновляется, если старше debounce-окна;
  - last_active НЕ обновляется при свежем значении (нет лишних UPDATE);
  - revoked/expired сессии не «оживляются» touch'ем;
  - auth по raw token, hashed-семантика, logout — не сломаны
    (основное покрытие — в test_session_token_hashing.py).

Требования: dev PostgreSQL на alembic head.
"""

import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt

from app.auth import storage as auth_storage
from app.auth.security import hash_session_token
from app.auth.storage import TOUCH_SESSION_DEBOUNCE_SECONDS, touch_session
from app.db.session import SessionLocal
from app.db.models import UserSession

PASSWORD = "SecurePass42!"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _login(client) -> tuple[str, int]:
    """Создаёт студента, логинится. Возвращает (raw_token, user_id)."""
    user = auth_storage.save_user({
        "name":            "Touch Test User",
        "email":           f"integ_touch_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role":            "student",
    })
    r = client.post("/api/auth/login", json={
        "email": user["email"], "password": PASSWORD,
    })
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"])


def _get_last_active(raw_token: str) -> datetime:
    with SessionLocal() as db:
        return db.query(UserSession.last_active).filter(
            UserSession.id == hash_session_token(raw_token)
        ).scalar()


def _set_session_fields(raw_token: str, **fields) -> None:
    with SessionLocal() as db:
        db.query(UserSession).filter(
            UserSession.id == hash_session_token(raw_token)
        ).update(fields, synchronize_session=False)
        db.commit()


def _old_ts() -> datetime:
    """Timestamp заведомо старше debounce-окна."""
    return datetime.now(timezone.utc) - timedelta(
        seconds=TOUCH_SESSION_DEBOUNCE_SECONDS * 2
    )


# ─── 1. Debounce semantics ────────────────────────────────────────────────────

class TestTouchDebounce:
    def test_updates_when_last_active_old(self, client):
        raw, _ = _login(client)
        old = _old_ts()
        _set_session_fields(raw, last_active=old)

        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200

        refreshed = _get_last_active(raw)
        assert refreshed > old  # обновился до ~now

    def test_skips_update_when_fresh(self, client):
        raw, _ = _login(client)
        # last_active свежий (server_default now при создании сессии)
        before = _get_last_active(raw)

        # Несколько запросов внутри debounce-окна — UPDATE не должен происходить
        for _ in range(3):
            r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
            assert r.status_code == 200

        assert _get_last_active(raw) == before

    def test_updates_when_last_active_null(self, client):
        raw, _ = _login(client)
        _set_session_fields(raw, last_active=None)

        touch_session(raw)
        assert _get_last_active(raw) is not None

    def test_direct_touch_respects_debounce(self, client):
        """Повторный touch внутри окна не сдвигает timestamp."""
        raw, _ = _login(client)
        old = _old_ts()
        _set_session_fields(raw, last_active=old)

        touch_session(raw)
        first = _get_last_active(raw)
        assert first > old

        touch_session(raw)  # сразу же повторно — внутри окна
        assert _get_last_active(raw) == first


# ─── 2. Revoked / expired не оживляются ──────────────────────────────────────

class TestNoRevival:
    def test_revoked_session_not_touched(self, client):
        raw, _ = _login(client)
        old = _old_ts()
        _set_session_fields(raw, last_active=old, is_revoked=True)

        touch_session(raw)
        assert _get_last_active(raw) == old  # не изменился

    def test_expired_session_not_touched(self, client):
        raw, _ = _login(client)
        old = _old_ts()
        expired = datetime.now(timezone.utc) - timedelta(hours=1)
        _set_session_fields(raw, last_active=old, expires_at=expired)

        touch_session(raw)
        assert _get_last_active(raw) == old

    def test_expired_session_still_rejected_as_bearer(self, client):
        """Skip touch не продлевает expired session — валидация прежняя."""
        raw, _ = _login(client)
        _set_session_fields(
            raw, expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401


# ─── 3. Auth flow не сломан ──────────────────────────────────────────────────

class TestAuthFlowIntact:
    def test_raw_token_works_db_value_rejected(self, client):
        raw, user_id = _login(client)

        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200

        db_value = hash_session_token(raw)
        r = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {db_value}"},
        )
        assert r.status_code == 401

    def test_logout_still_works(self, client):
        raw, _ = _login(client)
        headers = {"Authorization": f"Bearer {raw}"}

        assert client.post("/api/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/auth/me", headers=headers).status_code == 401
