"""
API/integration tests: legacy `role` PATCH /api/admin/users/{uuid} — legal basis
и staff-only контракт (Stage 31f → ADR-018 multi-role foundation).

Legacy single-`role` — compatibility adapter поверх set-based ядра (без
destructive replace-all). В multi-role модели admin role control управляет ТОЛЬКО
staff-ролями:
  - staff↔staff (напр. psychologist→supervisor) требует документированного
    основания; запись основания и смена роли атомарны;
  - назначение/снятие/конвертация роли `student` через admin PATCH запрещены
    (422) — student появляется только через self-registration / staff-created
    student flow;
  - multi-role пользователь + legacy `role` → 409 (использовать roles[]).

Требования: dev PostgreSQL на alembic head с seed-данными.
"""

import uuid as _uuid

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import Role, User, UserLegalBasisRecord, UserRole

PASSWORD = "SecurePass42!"


def _bcrypt_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _make_user(role: str) -> tuple[str, int]:
    """Создаёт пользователя с ролью напрямую через auth storage. (uuid, id)."""
    u = auth_storage.save_user({
        "name":            f"Integ {role} {_uuid.uuid4().hex[:6]}",
        "email":           f"integ_rolepatch_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _bcrypt_hash(PASSWORD),
        "role":            role,
    })
    return _uuid_for_id(int(u["id"])), int(u["id"])


def _make_admin(client) -> tuple[str, int]:
    """Создаёт админа, логинится. (token, admin_id)."""
    admin = auth_storage.save_user({
        "name":            "Integ Admin",
        "email":           f"integ_rolepatch_admin_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _bcrypt_hash(PASSWORD),
        "role":            "admin",
    })
    r = client.post("/api/auth/login", json={
        "email": admin["email"], "password": PASSWORD,
    })
    assert r.status_code == 200
    return r.json()["session_token"], int(admin["id"])


def _login(client, email: str) -> str:
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200
    return r.json()["session_token"]


def _uuid_for_id(user_id: int) -> str:
    with SessionLocal() as db:
        return str(db.query(User.uuid).filter(User.id == user_id).scalar())


def _patch(client, token: str, uuid: str, body: dict):
    return client.patch(
        f"/api/admin/users/{uuid}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


def _role_of(user_id: int) -> str:
    with SessionLocal() as db:
        row = (
            db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == user_id)
            .first()
        )
        return row[0] if row else "student"


def _basis_records(user_id: int) -> list[UserLegalBasisRecord]:
    with SessionLocal() as db:
        rows = (
            db.query(UserLegalBasisRecord)
            .filter(UserLegalBasisRecord.user_id == user_id)
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


BASIS_OK = {
    "legal_basis_confirmed": True,
    "basis_type": "administrative_order",
    "basis_reference": "Приказ № 7-к",
    "legal_basis_comment": "Назначение через смену роли",
}


# ─── 1. Staff↔staff change requires legal basis ──────────────────────────────

class TestRequiresBasis:
    def test_psychologist_to_supervisor_without_basis_rejected(self, client):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {"role": "supervisor"})
        assert r.status_code == 400
        assert _role_of(uid) == "psychologist"       # роль не изменилась
        assert len(_basis_records(uid)) == 0         # частичных записей нет

    def test_missing_basis_reference_rejected(self, client):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        body = {"role": "supervisor", "legal_basis_confirmed": True,
                "basis_type": "employment"}   # нет basis_reference
        r = _patch(client, token, uuid, body)
        assert r.status_code == 400
        assert _role_of(uid) == "psychologist"
        assert len(_basis_records(uid)) == 0

    def test_invalid_basis_type_rejected_422(self, client):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        body = {"role": "supervisor", "legal_basis_confirmed": True,
                "basis_type": "patient_consent", "basis_reference": "Приказ № 1"}
        r = _patch(client, token, uuid, body)
        assert r.status_code == 422        # pydantic Literal
        assert _role_of(uid) == "psychologist"
        assert len(_basis_records(uid)) == 0


# ─── 2. Staff↔staff change with basis succeeds + records basis (new metadata) ─

class TestSuccessWithBasis:
    @pytest.mark.parametrize("new_role", ["supervisor", "admin"])
    def test_psychologist_to_staff_with_basis(self, client, new_role):
        token, admin_id = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        r = _patch(client, token, uuid, {"role": new_role, **BASIS_OK})
        assert r.status_code == 200
        assert r.json()["role"] == new_role
        assert _role_of(uid) == new_role

        records = _basis_records(uid)
        assert len(records) == 1
        rec = records[0]
        assert rec.basis_type == "administrative_order"
        assert rec.basis_source == "admin_ui"
        assert rec.basis_reference == "Приказ № 7-к"
        assert rec.confirmed_by_user_id == admin_id
        assert rec.ip_address is not None
        assert rec.user_agent is not None
        # новый унифицированный формат metadata (role_add / added_role)
        assert rec.record_metadata["action"] == "role_add"
        assert rec.record_metadata["added_role"] == new_role
        assert rec.record_metadata["roles_before"] == ["psychologist"]
        assert rec.record_metadata["roles_after"] == [new_role]


# ─── 3. Student — read-only через admin PATCH ────────────────────────────────

class TestStudentReadOnly:
    def test_student_to_staff_rejected_422(self, client):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("student")
        r = _patch(client, token, uuid, {"role": "psychologist", **BASIS_OK})
        assert r.status_code == 422
        assert _role_of(uid) == "student"
        assert len(_basis_records(uid)) == 0

    def test_staff_to_student_rejected_422(self, client):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("psychologist")
        # у психолога есть запись основания — она НЕ должна пострадать
        with SessionLocal() as db:
            db.add(UserLegalBasisRecord(
                user_id=uid, basis_type="employment", basis_source="admin_ui",
                basis_reference="Приказ № 0",
            ))
            db.commit()

        r = _patch(client, token, uuid, {"role": "student"})
        assert r.status_code == 422
        assert _role_of(uid) == "psychologist"          # роль не изменилась
        assert len(_basis_records(uid)) == 1            # старые записи целы

    def test_noop_student_on_pure_student_ok(self, client):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("student")
        r = _patch(client, token, uuid, {"role": "student"})
        assert r.status_code == 200
        assert _role_of(uid) == "student"
        assert len(_basis_records(uid)) == 0


# ─── 4. Non-role / no-op не требует основания ────────────────────────────────

class TestNoBasisNeeded:
    def test_no_role_change_does_not_require_basis(self, client):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("student")
        r = _patch(client, token, uuid, {"full_name": "Новое Имя"})
        assert r.status_code == 200
        assert r.json()["full_name"] == "Новое Имя"
        assert _role_of(uid) == "student"
        assert len(_basis_records(uid)) == 0


# ─── 5. Access control ────────────────────────────────────────────────────────

class TestAccessControl:
    def test_non_admin_cannot_patch_role(self, client):
        # психолог пытается дёрнуть admin-эндпоинт
        psy_uuid, psy_id = _make_user("psychologist")
        with SessionLocal() as db:
            email = db.query(User.email).filter(User.id == psy_id).scalar()
        psy_token = _login(client, email)

        target_uuid, target_id = _make_user("psychologist")
        r = _patch(client, psy_token, target_uuid, {"role": "supervisor", **BASIS_OK})
        assert r.status_code == 403
        assert _role_of(target_id) == "psychologist"


# ─── 6. Atomicity ─────────────────────────────────────────────────────────────

class TestAtomicity:
    def test_basis_write_failure_rolls_back_role_change(self, client, monkeypatch):
        token, _ = _make_admin(client)
        uuid, uid = _make_user("psychologist")

        class Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("basis write failed (test)")

        monkeypatch.setattr("app.users.storage.UserLegalBasisRecord", Boom)

        with pytest.raises(RuntimeError, match="basis write failed"):
            _patch(client, token, uuid, {"role": "supervisor", **BASIS_OK})

        # роль не изменилась, запись основания не создана
        assert _role_of(uid) == "psychologist"
        assert len(_basis_records(uid)) == 0
