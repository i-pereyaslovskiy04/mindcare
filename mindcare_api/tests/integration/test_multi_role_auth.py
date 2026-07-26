"""
API/integration tests: multi-role auth payload + require_role пересечением
(ADR-018, backend foundation).

Покрывает:
  - login / /me / /profile возвращают roles[] + legacy role (primary);
  - require_role проверяет пересечение активных ролей с allowed;
  - пользователь без нужной membership-роли → 403;
  - primary role детерминирован по глобальному приоритету;
  - нет активных ролей → role=None, roles=[], 403 (НЕ маскируется как student);
  - просроченная роль (expires_at в прошлом) не попадает в roles.

Требования: dev PostgreSQL на alembic head с seed-данными (роли).
"""

import uuid as _uuid
from datetime import datetime, timezone, timedelta

import bcrypt
import pytest

from app.auth import storage as auth_storage
from tests.integration.conftest import (
    add_user_role, create_multi_role_user, remove_all_user_roles,
)

PASSWORD = "SecurePass42!"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login_user(client, roles):
    return create_multi_role_user(client, roles, password=PASSWORD)


# ─── 1. Auth payload содержит roles[] + legacy role ──────────────────────────

class TestAuthPayloadRoles:
    def test_login_returns_roles_and_primary(self, client):
        token, _uid, _email = _login_user(client, ["psychologist", "supervisor"])
        # повторный login, чтобы проверить тело ответа
        r = client.post("/api/auth/login", json={"email": _email, "password": PASSWORD})
        assert r.status_code == 200
        body = r.json()
        assert set(body["roles"]) == {"psychologist", "supervisor"}
        assert body["role"] == "supervisor"  # primary по приоритету

    def test_me_returns_roles(self, client):
        token, _uid, _email = _login_user(client, ["admin", "psychologist"])
        r = client.get("/api/auth/me", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert set(body["roles"]) == {"admin", "psychologist"}
        assert body["role"] == "admin"

    def test_profile_returns_roles(self, client):
        token, _uid, _email = _login_user(client, ["supervisor", "psychologist"])
        r = client.get("/api/auth/profile", headers=_auth(token))
        assert r.status_code == 200
        body = r.json()
        assert set(body["roles"]) == {"supervisor", "psychologist"}
        assert body["role"] == "supervisor"


# ─── 2. require_role проверяет пересечение ───────────────────────────────────

class TestRequireRoleIntersection:
    def test_multi_role_user_passes_all_cabinets(self, client):
        token, _uid, _email = _login_user(
            client, ["admin", "supervisor", "psychologist"],
        )
        # admin endpoint
        assert client.get("/api/admin/users/", headers=_auth(token)).status_code == 200
        # supervisor endpoint (admin|supervisor)
        assert client.get(
            "/api/supervisor/students", headers=_auth(token),
        ).status_code == 200
        # psychologist endpoint
        assert client.get(
            "/api/psychologist/students", headers=_auth(token),
        ).status_code == 200

    def test_supervisor_psychologist_denied_admin(self, client):
        token, _uid, _email = _login_user(client, ["supervisor", "psychologist"])
        # нет admin membership → 403 на admin endpoint
        assert client.get("/api/admin/users/", headers=_auth(token)).status_code == 403
        # но проходит в supervisor и psychologist
        assert client.get(
            "/api/supervisor/students", headers=_auth(token),
        ).status_code == 200
        assert client.get(
            "/api/psychologist/students", headers=_auth(token),
        ).status_code == 200

    def test_pure_student_denied_staff_endpoints(self, client):
        token, _uid, _email = _login_user(client, ["student"])
        assert client.get("/api/admin/users/", headers=_auth(token)).status_code == 403
        assert client.get(
            "/api/supervisor/students", headers=_auth(token),
        ).status_code == 403
        assert client.get(
            "/api/psychologist/students", headers=_auth(token),
        ).status_code == 403


# ─── 3. Детерминизм primary role ─────────────────────────────────────────────

class TestPrimaryDeterminism:
    @pytest.mark.parametrize("roles,expected", [
        (["supervisor", "psychologist"], "supervisor"),
        (["psychologist", "supervisor"], "supervisor"),
        (["admin", "student"], "admin"),
        (["admin", "supervisor", "psychologist"], "admin"),
    ])
    def test_primary_is_highest_priority(self, client, roles, expected):
        token, _uid, _email = _login_user(client, roles)
        r = client.get("/api/auth/me", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["role"] == expected
        assert set(r.json()["roles"]) == set(roles)


# ─── 4. Нет активных ролей ≠ student ─────────────────────────────────────────

class TestNoActiveRoles:
    def _make_student(self, client):
        email = f"integ_noroles_{_uuid.uuid4().hex[:10]}@example.com"
        pw = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
        user = auth_storage.save_user({
            "name": "No Roles", "email": email,
            "hashed_password": pw, "role": "student",
        })
        return int(user["id"]), email

    def test_no_roles_me_role_none_roles_empty(self, client):
        uid, email = self._make_student(client)
        token = client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD},
        ).json()["session_token"]
        remove_all_user_roles(uid)

        r = client.get("/api/auth/me", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["roles"] == []
        assert r.json()["role"] is None

    def test_no_roles_denied_everywhere_not_student(self, client):
        uid, email = self._make_student(client)
        token = client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD},
        ).json()["session_token"]
        remove_all_user_roles(uid)

        # student-only endpoint тоже 403 — отсутствие ролей НЕ трактуется как student
        assert client.get(
            "/api/diary/today", headers=_auth(token),
        ).status_code == 403
        assert client.get(
            "/api/psychologist/students", headers=_auth(token),
        ).status_code == 403

    def test_login_no_roles_payload(self, client):
        uid, email = self._make_student(client)
        remove_all_user_roles(uid)
        r = client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD},
        )
        assert r.status_code == 200
        assert r.json()["roles"] == []
        assert r.json()["role"] is None


# ─── 5. Просроченная роль исключается ────────────────────────────────────────

class TestExpiredRole:
    def test_expired_role_not_in_roles(self, client):
        token, uid, _email = _login_user(client, ["student"])
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "psychologist", expires_at=past)

        r = client.get("/api/auth/me", headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["roles"] == ["student"]
        # просроченная psychologist не даёт доступа
        assert client.get(
            "/api/psychologist/students", headers=_auth(token),
        ).status_code == 403

    def test_active_role_alongside_expired(self, client):
        token, uid, _email = _login_user(client, ["psychologist"])
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "supervisor", expires_at=past)  # просрочена
        future = datetime.now(timezone.utc) + timedelta(days=30)
        add_user_role(uid, "admin", expires_at=future)     # активна

        r = client.get("/api/auth/me", headers=_auth(token))
        assert r.status_code == 200
        assert set(r.json()["roles"]) == {"psychologist", "admin"}
        assert r.json()["role"] == "admin"
