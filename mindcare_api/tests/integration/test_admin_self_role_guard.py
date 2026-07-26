"""
Integration-тесты self-admin guard (ADR-018): администратор не может снять у себя
роль admin. Backend — обязательный guard. Требуют dev PostgreSQL на head.

Проверяется:
  - PATCH roles[] без своего admin → 422, роль сохранена;
  - PATCH legacy role, снимающий свой admin → 422;
  - сохранение admin + смена другой своей роли — успех;
  - другой admin может менять роли другого пользователя;
  - rejected combined PATCH не меняет scalar-поля и не пишет audit/legal basis.
"""

import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, Role, User, UserLegalBasisRecord, UserRole

from tests.integration.conftest import add_user_role

PASSWORD = "SecurePass42!"

_LEGAL_BASIS = {
    "legal_basis_confirmed": True,
    "basis_type": "employment",
    "basis_reference": "Приказ № 5-к",
}


def _hash() -> str:
    return bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()


def _make_user(client, role: str, extra_roles=None):
    """Создаёт пользователя (save_user + доп. роли), логинит.
    Returns (token, user_id, uuid)."""
    u = auth_storage.save_user({
        "name": f"Integ {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_selfguard_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _hash(),
        "role": role,
    })
    uid = int(u["id"])
    for r in (extra_roles or []):
        add_user_role(uid, r)
    r = client.post(
        "/api/auth/login", json={"email": u["email"], "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        uuid_str = str(db.query(User.uuid).filter(User.id == uid).scalar())
    return r.json()["session_token"], uid, uuid_str


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _patch(client, token, uuid, body):
    return client.patch(
        f"/api/admin/users/{uuid}", headers=_auth(token), json=body,
    )


def _roles_of(user_id: int) -> set:
    with SessionLocal() as db:
        return {
            name for (name,) in db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id).all()
        }


def _user_row(user_id: int):
    with SessionLocal() as db:
        u = db.query(User).filter(User.id == user_id).first()
        db.expunge(u)
        return u


def _legal_basis_count(user_id: int) -> int:
    with SessionLocal() as db:
        return db.query(UserLegalBasisRecord).filter(
            UserLegalBasisRecord.user_id == user_id,
        ).count()


def _role_audit_count(user_id: int) -> int:
    with SessionLocal() as db:
        return db.query(AuditLog).filter(
            AuditLog.entity_type == "user",
            AuditLog.entity_id == user_id,
            AuditLog.event_type.in_(
                ["admin_role_add", "admin_role_remove", "admin_role_update"],
            ),
        ).count()


# ─── Self-admin removal blocked ───────────────────────────────────────────────

class TestSelfAdminGuard:
    def test_remove_own_admin_via_roles_422(self, client):
        # admin + supervisor: пытаемся снять admin через roles=["supervisor"].
        token, uid, uuid = _make_user(client, "admin", extra_roles=["supervisor"])
        r = _patch(client, token, uuid, {"roles": ["supervisor"]})
        assert r.status_code == 422, r.text
        assert "администратор" in r.json()["detail"].lower()
        assert _roles_of(uid) == {"admin", "supervisor"}  # роли сохранены

    def test_remove_own_admin_via_empty_roles_422(self, client):
        # admin-only: roles=[] сняло бы admin — self-guard 422 (не «без ролей»).
        token, uid, uuid = _make_user(client, "admin")
        r = _patch(client, token, uuid, {"roles": []})
        assert r.status_code == 422, r.text
        assert _roles_of(uid) == {"admin"}

    def test_remove_own_admin_via_legacy_role_422(self, client):
        # admin-only: legacy role="supervisor" → removed={admin} → self-guard 422.
        token, uid, uuid = _make_user(client, "admin")
        r = _patch(client, token, uuid, {"role": "supervisor"})
        assert r.status_code == 422, r.text
        assert _roles_of(uid) == {"admin"}


# ─── Keeping admin: other own-role changes allowed ────────────────────────────

class TestKeepingAdminAllowsOtherChanges:
    def test_keep_admin_remove_other_own_role(self, client):
        # admin + supervisor: снимаем supervisor, admin сохраняется → 200.
        token, uid, uuid = _make_user(client, "admin", extra_roles=["supervisor"])
        r = _patch(client, token, uuid, {"roles": ["admin"]})
        assert r.status_code == 200, r.text
        assert set(r.json()["roles"]) == {"admin"}
        assert _roles_of(uid) == {"admin"}

    def test_keep_admin_change_scalar(self, client):
        token, uid, uuid = _make_user(client, "admin")
        r = _patch(client, token, uuid, {"full_name": "Новое Имя Тест"})
        assert r.status_code == 200, r.text
        assert _user_row(uid).full_name == "Новое Имя Тест"


# ─── Another admin can change another user's roles ────────────────────────────

class TestOtherAdminCanChange:
    def test_other_admin_removes_target_admin(self, client):
        actor_token, _actor_id, _actor_uuid = _make_user(client, "admin")
        # target: admin + supervisor (снятие admin оставит supervisor).
        _t_token, target_id, target_uuid = _make_user(
            client, "admin", extra_roles=["supervisor"],
        )
        r = _patch(client, actor_token, target_uuid, {"roles": ["supervisor"]})
        assert r.status_code == 200, r.text
        assert _roles_of(target_id) == {"supervisor"}


# ─── Rejected combined PATCH: no scalar/audit/legal-basis side effects ─────────

class TestRejectedCombinedPatchNoSideEffects:
    def test_scalar_and_audit_rolled_back(self, client):
        token, uid, uuid = _make_user(client, "admin", extra_roles=["supervisor"])
        before = _user_row(uid)
        lb_before = _legal_basis_count(uid)
        audit_before = _role_audit_count(uid)

        # Комбинированный PATCH: снять свой admin + сменить scalar-поля.
        r = _patch(client, token, uuid, {
            "roles": ["supervisor"],
            "full_name": "Не Должно Сохраниться",
            "is_active": False,
        })
        assert r.status_code == 422, r.text

        after = _user_row(uid)
        # scalar-поля не изменились (единый commit → rollback).
        assert after.full_name == before.full_name
        assert after.is_active == before.is_active
        assert after.is_active is True
        # роли сохранены; audit и legal basis не добавлены.
        assert _roles_of(uid) == {"admin", "supervisor"}
        assert _legal_basis_count(uid) == lb_before
        assert _role_audit_count(uid) == audit_before
