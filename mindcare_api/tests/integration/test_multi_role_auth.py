"""
API/integration tests: multi-role auth payload + require_role пересечением
(ADR-018, backend foundation).

Покрывает:
  - login / /me / /profile возвращают roles[] + legacy role (primary);
  - require_role проверяет пересечение активных ролей с allowed;
  - пользователь без нужной membership-роли → 403;
  - primary role детерминирован по глобальному приоритету;
  - нет активных ролей → НОВЫЙ вход отклоняется контролируемым 403 с
    failure_reason `no_active_roles` (ADR-018), сессия не создаётся; уже
    выданная сессия отдаёт role=None, roles=[], 403 на прикладных эндпоинтах
    (НЕ маскируется как student) и корректно закрывается через logout;
  - просроченная роль (expires_at в прошлом) не попадает в roles.

Требования: dev PostgreSQL на alembic head с seed-данными (роли).
"""

import uuid as _uuid
from datetime import datetime, timezone, timedelta

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.models import AuthLog, User, UserSession
from app.db.session import SessionLocal
from tests.integration.conftest import (
    add_user_role, create_multi_role_user, remove_all_user_roles,
)

PASSWORD = "SecurePass42!"


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _login_user(client, roles):
    return create_multi_role_user(client, roles, password=PASSWORD)


def _session_count(user_id: int) -> int:
    with SessionLocal() as db:
        return db.query(UserSession).filter(
            UserSession.user_id == user_id).count()


def _last_login(user_id: int):
    with SessionLocal() as db:
        return db.query(User.last_login).filter(User.id == user_id).scalar()


def _last_auth_event(email: str, event: str):
    """Последняя строка auth_log по email (failed_login пишет user_email)."""
    with SessionLocal() as db:
        row = (
            db.query(AuthLog)
            .filter(AuthLog.user_email == email, AuthLog.event == event)
            .order_by(AuthLog.created_at.desc(), AuthLog.id.desc())
            .first()
        )
        if row is not None:
            db.expunge(row)
        return row


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

    def test_login_without_active_roles_is_refused_with_403(self, client):
        """Вход без активных ролей — ШТАТНЫЙ отказ 403, не 500 (ADR-018).

        `service.authenticate_user` отвергает такой аккаунт ДО
        update_last_login/create_session: сессия без ролей не должна появляться
        вообще. Прежний 500/`internal_error` был неотличим от настоящей аварии.
        Поведение уже выданной сессии проверяют соседние тесты (me → role null,
        прикладные эндпоинты → 403, logout → 200).
        """
        uid, email = self._make_student(client)
        remove_all_user_roles(uid)
        sessions_before = _session_count(uid)
        last_login_before = _last_login(uid)

        r = client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD},
        )

        assert r.status_code == 403, r.text
        assert "session_token" not in r.json()
        # внутреннее состояние ролей наружу не раскрывается
        body = r.text.lower()
        assert "role" not in body and "user_roles" not in body
        # новая сессия не создана, last_login не обновлён
        assert _session_count(uid) == sessions_before
        assert _last_login(uid) == last_login_before

        entry = _last_auth_event(email, "failed_login")
        assert entry is not None
        assert entry.failure_reason == "no_active_roles"
        assert entry.success is False

    def test_wrong_password_keeps_invalid_credentials_reason(self, client):
        """`no_active_roles` не подменяет обычный отказ по паролю.

        У пользователя роли есть; причина обязана остаться invalid_credentials,
        иначе новый код размывал бы значение и путал расследование.
        """
        _uid, email = self._make_student(client)
        r = client.post(
            "/api/auth/login", json={"email": email, "password": "WrongPass99!"},
        )
        assert r.status_code == 401, r.text

        entry = _last_auth_event(email, "failed_login")
        assert entry is not None
        assert entry.failure_reason == "invalid_credentials"

    def test_logout_works_after_all_roles_removed(self, client):
        """Уже выданная сессия обязана закрываться, даже если ролей не осталось.

        Регрессия: audit-facade требовал роль у user-актора, а `auth_log` её не
        хранит вовсе — logout такого пользователя падал 500, и завершить сессию
        было нечем. Роль обязательна только для AUDIT_LOG.
        """
        uid, email = self._make_student(client)
        token = client.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD},
        ).json()["session_token"]
        remove_all_user_roles(uid)

        r = client.post("/api/auth/logout", headers=_auth(token))
        assert r.status_code == 200, r.text
        # сессия действительно отозвана
        assert client.get(
            "/api/auth/me", headers=_auth(token),
        ).status_code == 401

        with SessionLocal() as db:
            assert db.query(AuthLog).filter(
                AuthLog.user_id == uid, AuthLog.event == "logout",
            ).count() == 1


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
