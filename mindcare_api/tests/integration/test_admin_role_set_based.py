"""
API/integration tests: set-based staff role management на PATCH
/api/admin/users/{uuid} (ADR-018, multi-role foundation).

Правила:
  - управление ролями только staff (psychologist/supervisor/admin), без
    destructive replace-all;
  - `roles[]` — target staff set; student read-only (add/remove → 422);
  - staff role add требует legal basis (атомарно), remove — audit без basis;
  - нельзя оставить пользователя без активных ролей (422);
  - student-only → staff через PATCH запрещён (422);
  - legacy `role` — adapter; multi-role → 409; student — только no-op;
  - role + roles одновременно → 422.

Требования: dev PostgreSQL на alembic head с seed-данными.
"""

import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.auth.roles import primary_role
from app.db.session import SessionLocal
from app.db.models import AuditLog, Role, User, UserLegalBasisRecord, UserRole
from tests.integration.conftest import add_user_role, remove_all_user_roles

PASSWORD = "SecurePass42!"


def _hash() -> str:
    return bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()


def _make_admin(client) -> str:
    admin = auth_storage.save_user({
        "name": "Integ Admin",
        "email": f"integ_setbased_admin_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _hash(),
        "role": "admin",
    })
    r = client.post(
        "/api/auth/login", json={"email": admin["email"], "password": PASSWORD},
    )
    assert r.status_code == 200
    return r.json()["session_token"]


def _make_user(role: str, extra_roles: list[str] | None = None) -> tuple[str, int]:
    u = auth_storage.save_user({
        "name": f"Integ {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_setbased_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _hash(),
        "role": role,
    })
    uid = int(u["id"])
    for r in (extra_roles or []):
        add_user_role(uid, r)
    return _uuid_for_id(uid), uid


def _uuid_for_id(user_id: int) -> str:
    with SessionLocal() as db:
        return str(db.query(User.uuid).filter(User.id == user_id).scalar())


def _patch(client, token: str, uuid: str, body: dict):
    return client.patch(
        f"/api/admin/users/{uuid}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


def _get(client, token: str, uuid: str):
    return client.get(
        f"/api/admin/users/{uuid}",
        headers={"Authorization": f"Bearer {token}"},
    )


def _list(client, token: str, **params):
    return client.get(
        "/api/admin/users/",
        headers={"Authorization": f"Bearer {token}"},
        params=params,
    )


def _user_role_rows(user_id: int) -> list[UserRole]:
    with SessionLocal() as db:
        rows = db.query(UserRole).filter(UserRole.user_id == user_id).all()
        for r in rows:
            db.expunge(r)
        return rows


def _roles_of(user_id: int) -> set:
    with SessionLocal() as db:
        rows = (
            db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id)
            .all()
        )
        return {r[0] for r in rows}


def _basis_records(user_id: int) -> list:
    with SessionLocal() as db:
        rows = (
            db.query(UserLegalBasisRecord)
            .filter(UserLegalBasisRecord.user_id == user_id)
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _role_audit(user_id: int) -> list:
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.entity_type == "user",
                AuditLog.entity_id == user_id,
                AuditLog.event_type.in_(
                    ("admin_role_add", "admin_role_remove", "admin_role_update"),
                ),
            )
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


BASIS_OK = {
    "legal_basis_confirmed": True,
    "basis_type": "administrative_order",
    "basis_reference": "Приказ № 7-к",
    "legal_basis_comment": "set-based role add",
}


# ─── 1. Add staff role via roles[] ───────────────────────────────────────────

class TestAddStaffRole:
    def test_add_supervisor_to_psychologist(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {
            "roles": ["psychologist", "supervisor"], **BASIS_OK,
        })
        assert r.status_code == 200, r.text
        assert _roles_of(uid) == {"psychologist", "supervisor"}
        assert set(r.json()["roles"]) == {"psychologist", "supervisor"}

        records = _basis_records(uid)
        assert len(records) == 1
        rec = records[0]
        assert rec.basis_type == "administrative_order"
        assert rec.basis_source == "admin_ui"
        assert rec.record_metadata["action"] == "role_add"
        assert rec.record_metadata["added_role"] == "supervisor"
        assert "psychologist" in rec.record_metadata["roles_before"]
        assert set(rec.record_metadata["roles_after"]) == {
            "psychologist", "supervisor",
        }
        assert rec.ip_address is not None

    def test_add_without_basis_rejected(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {"roles": ["psychologist", "supervisor"]})
        assert r.status_code == 400
        assert _roles_of(uid) == {"psychologist"}
        assert len(_basis_records(uid)) == 0

    def test_add_creates_role_add_audit(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        _patch(client, token, uuid, {
            "roles": ["psychologist", "supervisor"], **BASIS_OK,
        })
        events = [e for e in _role_audit(uid) if e.event_type == "admin_role_add"]
        assert len(events) == 1
        assert events[0].user_role == "admin"
        assert set(events[0].log_metadata["added"]) == {"supervisor"}


# ─── 2. Remove staff role ────────────────────────────────────────────────────

class TestRemoveStaffRole:
    def test_remove_supervisor_keeps_psychologist(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist", extra_roles=["supervisor"])
        assert _roles_of(uid) == {"psychologist", "supervisor"}

        r = _patch(client, token, uuid, {"roles": ["psychologist"]})
        assert r.status_code == 200, r.text
        assert _roles_of(uid) == {"psychologist"}
        # удаление staff-роли — без нового legal basis
        assert len(_basis_records(uid)) == 0
        events = [
            e for e in _role_audit(uid) if e.event_type == "admin_role_remove"
        ]
        assert len(events) == 1
        assert set(events[0].log_metadata["removed"]) == {"supervisor"}

    def test_remove_keeps_old_basis_records(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist", extra_roles=["supervisor"])
        with SessionLocal() as db:
            db.add(UserLegalBasisRecord(
                user_id=uid, basis_type="employment", basis_source="admin_ui",
                basis_reference="Приказ № 0",
            ))
            db.commit()
        assert len(_basis_records(uid)) == 1

        r = _patch(client, token, uuid, {"roles": ["psychologist"]})
        assert r.status_code == 200
        assert len(_basis_records(uid)) == 1  # старые не тронуты


# ─── 3. Student — read-only ──────────────────────────────────────────────────

class TestStudentReadOnly:
    def test_student_in_roles_rejected_422(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {
            "roles": ["psychologist", "student"], **BASIS_OK,
        })
        assert r.status_code == 422  # pydantic Literal
        assert _roles_of(uid) == {"psychologist"}

    def test_existing_student_preserved_on_staff_add(self, client):
        token = _make_admin(client)
        # student + psychologist
        uuid, uid = _make_user("student", extra_roles=["psychologist"])
        r = _patch(client, token, uuid, {
            "roles": ["psychologist", "supervisor"], **BASIS_OK,
        })
        assert r.status_code == 200, r.text
        roles = _roles_of(uid)
        assert "student" in roles           # student сохранён
        assert roles == {"student", "psychologist", "supervisor"}
        assert "student" in r.json()["roles"]

    def test_student_only_to_staff_rejected_422(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("student")
        r = _patch(client, token, uuid, {"roles": ["psychologist"], **BASIS_OK})
        assert r.status_code == 422
        assert _roles_of(uid) == {"student"}
        assert len(_basis_records(uid)) == 0


# ─── 4. Guards: пустой набор / без ролей ─────────────────────────────────────

class TestEmptyResult:
    def test_empty_roles_leaving_no_active_rejected(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {"roles": []})
        assert r.status_code == 422
        assert _roles_of(uid) == {"psychologist"}


# ─── 5. Legacy `role` adapter ────────────────────────────────────────────────

class TestLegacyRoleAdapter:
    def test_legacy_student_on_staff_rejected_422(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {"role": "student"})
        assert r.status_code == 422
        assert _roles_of(uid) == {"psychologist"}

    def test_legacy_staff_on_student_only_rejected_422(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("student")
        r = _patch(client, token, uuid, {"role": "psychologist", **BASIS_OK})
        assert r.status_code == 422
        assert _roles_of(uid) == {"student"}

    def test_legacy_student_noop_on_pure_student_ok(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("student")
        r = _patch(client, token, uuid, {"role": "student"})
        assert r.status_code == 200, r.text
        assert _roles_of(uid) == {"student"}
        assert len(_basis_records(uid)) == 0

    def test_legacy_role_on_multi_role_user_409(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist", extra_roles=["supervisor"])
        r = _patch(client, token, uuid, {"role": "admin", **BASIS_OK})
        assert r.status_code == 409
        assert _roles_of(uid) == {"psychologist", "supervisor"}

    def test_legacy_staff_to_staff_single_role_ok(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {"role": "supervisor", **BASIS_OK})
        assert r.status_code == 200, r.text
        assert _roles_of(uid) == {"supervisor"}


# ─── 6. role + roles взаимоисключимы ─────────────────────────────────────────

class TestMutualExclusion:
    def test_role_and_roles_together_422(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {
            "role": "psychologist", "roles": ["supervisor"], **BASIS_OK,
        })
        assert r.status_code == 422
        assert _roles_of(uid) == {"psychologist"}


# ─── 7. Атомарность (failure-injection) ──────────────────────────────────────

class TestAtomicity:
    def test_basis_write_failure_rolls_back(self, client, monkeypatch):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")

        class Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("basis write failed (test)")

        monkeypatch.setattr("app.users.storage.UserLegalBasisRecord", Boom)

        with pytest.raises(RuntimeError, match="basis write failed"):
            _patch(client, token, uuid, {
                "roles": ["psychologist", "supervisor"], **BASIS_OK,
            })

        assert _roles_of(uid) == {"psychologist"}
        assert len(_basis_records(uid)) == 0


# ─── 8. No active roles ≠ student в admin read/list/update ──────────────────

class TestNoActiveRolesNotMaskedAsStudent:
    def test_admin_get_no_roles_role_is_none(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("student")
        remove_all_user_roles(uid)

        r = _get(client, token, uuid)
        assert r.status_code == 200
        body = r.json()
        assert body["roles"] == []
        assert body["role"] is None

    def test_admin_patch_scalar_only_no_roles_role_is_none(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("student")
        remove_all_user_roles(uid)

        r = _patch(client, token, uuid, {"full_name": "Новое Имя"})
        assert r.status_code == 200
        body = r.json()
        assert body["role"] is None
        assert body["roles"] == []

    def test_admin_list_no_roles_role_is_none(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("student")
        remove_all_user_roles(uid)

        r = _list(client, token, size=100)
        assert r.status_code == 200
        items = [it for it in r.json()["items"] if it["uuid"] == uuid]
        assert len(items) == 1
        assert items[0]["role"] is None


# ─── 9. Expired role не влияет на admin list/read primary role и фильтр ─────

class TestExpiredRoleIgnoredInAdminViews:
    def test_expired_higher_priority_role_not_shown_as_primary(self, client):
        token = _make_admin(client)
        # psychologist активен; supervisor (выше приоритетом) — просрочен.
        uuid, uid = _make_user("psychologist")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "supervisor", expires_at=past)

        r = _get(client, token, uuid)
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "psychologist"      # НЕ "supervisor"
        assert body["roles"] == ["psychologist"]

    def test_expired_role_not_shown_as_primary_in_list(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "supervisor", expires_at=past)

        items = _list(client, token, size=100).json()["items"]
        item = next(it for it in items if it["uuid"] == uuid)
        assert item["role"] == "psychologist"

    def test_expired_role_excluded_from_role_filter(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "supervisor", expires_at=past)

        # Фильтр role=supervisor не должен находить пользователя (роль просрочена).
        sup_items = _list(client, token, role="supervisor", size=100).json()["items"]
        assert uuid not in {it["uuid"] for it in sup_items}

        # Фильтр role=psychologist находит (роль активна).
        psy_items = _list(client, token, role="psychologist", size=100).json()["items"]
        assert uuid in {it["uuid"] for it in psy_items}


# ─── 10. Реактивация просроченной staff-роли (без UniqueConstraint) ─────────

class TestExpiredRoleReactivation:
    def test_reactivate_expired_staff_role_via_roles(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "supervisor", expires_at=past)  # просроченная строка

        r = _patch(client, token, uuid, {
            "roles": ["psychologist", "supervisor"], **BASIS_OK,
        })
        assert r.status_code == 200, r.text
        assert _roles_of(uid) == {"psychologist", "supervisor"}

        # Ровно одна строка user_roles на (user, supervisor) — реактивирована,
        # не задублирована (иначе UniqueConstraint(user_id, role_id) упал бы).
        rows = _user_role_rows(uid)
        with SessionLocal() as db:
            supervisor_role_id = (
                db.query(Role.id).filter(Role.name == "supervisor").scalar()
            )
        sup_rows = [r for r in rows if r.role_id == supervisor_role_id]
        assert len(sup_rows) == 1
        assert sup_rows[0].expires_at is None

        # legal basis всё равно создан для реактивации (это добавление роли).
        records = _basis_records(uid)
        assert len(records) == 1
        assert records[0].record_metadata["added_role"] == "supervisor"

    def test_reactivate_expired_role_no_integrity_error(self, client):
        """Смок: реактивация не должна поднимать IntegrityError на UniqueConstraint."""
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "admin", expires_at=past)

        r = _patch(client, token, uuid, {
            "roles": ["psychologist", "admin"], **BASIS_OK,
        })
        assert r.status_code == 200, r.text


# ─── 11. Admin LIST возвращает roles[] ───────────────────────────────────────

class TestAdminListRoles:
    def _find_item(self, client, token, uuid):
        r = _list(client, token, size=100)
        assert r.status_code == 200
        items = [it for it in r.json()["items"] if it["uuid"] == uuid]
        assert len(items) == 1
        return items[0]

    def test_list_returns_full_roles_and_primary(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist", extra_roles=["supervisor"])

        item = self._find_item(client, token, uuid)
        # детерминированный порядок по приоритету
        assert item["roles"] == ["supervisor", "psychologist"]
        assert item["role"] == "supervisor"
        assert item["role"] == primary_role(item["roles"])

    def test_list_excludes_expired_role(self, client):
        token = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        past = datetime.now(timezone.utc) - timedelta(days=1)
        add_user_role(uid, "supervisor", expires_at=past)

        item = self._find_item(client, token, uuid)
        assert item["roles"] == ["psychologist"]      # supervisor просрочен
        assert item["role"] == "psychologist"
