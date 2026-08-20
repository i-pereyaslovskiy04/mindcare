"""
API/integration tests for hashed session tokens (Stage 22b).

Доказывает:
  - клиент получает raw token, в БД хранится только SHA-256;
  - значение из user_sessions.id НЕ работает как Bearer (главный фикс C1);
  - logout/change-password отзывают hashed-сессии по raw token;
  - auth_log.session_id содержит hash, не raw token;
  - legacy plaintext-сессии контролируемо инвалидированы.

Требования те же, что у остальных integration-тестов: dev PostgreSQL
на alembic head с seed-данными.
"""

import re
from datetime import datetime, timedelta, timezone

from app.auth.security import hash_session_token
from app.db.session import SessionLocal
from app.db.models import AuthLog, UserSession
from tests.integration.conftest import create_test_user

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
PASSWORD = "SecurePass42!"   # default password в conftest.create_test_user


def _login(client, email: str, password: str = PASSWORD) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return r.json()["session_token"]


def _db_session_ids(user_id: int) -> list[str]:
    with SessionLocal() as db:
        rows = db.query(UserSession.id).filter(
            UserSession.user_id == user_id
        ).all()
        return [row.id for row in rows]


# ─── 1. Хранение: raw у клиента, hash в БД ───────────────────────────────────

class TestTokenStorage:
    def test_client_receives_raw_token_not_hash(self, client, test_email):
        create_test_user(test_email)
        raw = _login(client, test_email)
        # raw — 43 urlsafe-символа, не похож на SHA-256 hex
        assert len(raw) == 43
        assert not _HEX64.fullmatch(raw)

    def test_db_stores_sha256_not_raw(self, client, test_email):
        user = create_test_user(test_email)
        raw = _login(client, test_email)

        stored = _db_session_ids(int(user["id"]))
        assert len(stored) == 1
        assert stored[0] == hash_session_token(raw)
        assert _HEX64.fullmatch(stored[0])
        assert raw not in stored


# ─── 2. Bearer: raw работает, значение из БД — нет ───────────────────────────

class TestBearerSemantics:
    def test_raw_token_works_as_bearer(self, client, test_email):
        create_test_user(test_email)
        raw = _login(client, test_email)
        r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 200
        assert r.json()["email"] == test_email

    def test_db_value_rejected_as_bearer(self, client, test_email):
        """Главное доказательство C1-фикса: дамп user_sessions бесполезен."""
        user = create_test_user(test_email)
        _login(client, test_email)

        db_value = _db_session_ids(int(user["id"]))[0]
        r = client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {db_value}"},
        )
        assert r.status_code == 401


# ─── 3. Logout / change-password ─────────────────────────────────────────────

class TestRevocation:
    def test_logout_revokes_by_raw_token(self, client, test_email):
        create_test_user(test_email)
        raw = _login(client, test_email)
        headers = {"Authorization": f"Bearer {raw}"}

        r = client.post("/api/auth/logout", headers=headers)
        assert r.status_code == 200

        r = client.get("/api/auth/me", headers=headers)
        assert r.status_code == 401

    def test_change_password_revokes_all_hashed_sessions(self, client, test_email):
        create_test_user(test_email)
        raw1 = _login(client, test_email)
        raw2 = _login(client, test_email)

        r = client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {raw1}"},
            json={
                "current_password":     PASSWORD,
                "new_password":         "EvenBetter4242!",
                "new_password_confirm": "EvenBetter4242!",
            },
        )
        assert r.status_code == 200

        for raw in (raw1, raw2):
            r = client.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {raw}"},
            )
            assert r.status_code == 401


# ─── 4. Auth log не содержит raw token ───────────────────────────────────────

class TestAuthLogHashing:
    def _last_event(self, *, event: str, user_id: int) -> AuthLog:
        """Ищет строку по user_id, а не по user_email.

        `user_email` пишется не всеми auth-событиями: logout его намеренно НЕ
        передаёт (субъект восстановим по user_id) — это минимизация ПДн, а не
        пропажа события. Поиск по email находил бы только часть журнала.
        """
        with SessionLocal() as db:
            row = (
                db.query(AuthLog)
                .filter(AuthLog.user_id == user_id, AuthLog.event == event)
                .order_by(AuthLog.created_at.desc(), AuthLog.id.desc())
                .first()
            )
            assert row is not None, f"auth_log has no '{event}' for user {user_id}"
            db.expunge(row)
            return row

    def test_login_event_stores_hash_not_raw(self, client, test_email):
        user = create_test_user(test_email)
        raw = _login(client, test_email)

        entry = self._last_event(event="login", user_id=int(user["id"]))
        assert entry.session_id == hash_session_token(raw)
        assert entry.session_id != raw
        assert raw not in (entry.session_id or "")

    def test_logout_event_stores_hash_not_raw(self, client, test_email):
        user = create_test_user(test_email)
        raw = _login(client, test_email)
        client.post(
            "/api/auth/logout", headers={"Authorization": f"Bearer {raw}"},
        )

        entry = self._last_event(event="logout", user_id=int(user["id"]))
        assert entry.session_id == hash_session_token(raw)
        assert entry.session_id != raw
        # минимизация: logout не дублирует email — субъект известен по user_id
        assert entry.user_email is None


# ─── 5. Legacy plaintext sessions инвалидированы ─────────────────────────────

class TestLegacyPlaintextInvalidation:
    def test_plaintext_session_row_rejected(self, client, test_email):
        """
        Строка с raw token в user_sessions.id (как до Stage 22b) больше
        не аутентифицирует: lookup хеширует presented token и не находит её.
        Это ожидаемая controlled invalidation старых сессий.
        """
        user = create_test_user(test_email)
        legacy_raw = "legacy-plaintext-token-0123456789abcdefXYZ"

        with SessionLocal() as db:
            db.add(UserSession(
                id=legacy_raw,   # plaintext, как писал старый код
                user_id=int(user["id"]),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            ))
            db.commit()

        r = client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {legacy_raw}"},
        )
        assert r.status_code == 401
