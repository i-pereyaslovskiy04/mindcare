"""
API/integration tests for user_legal_basis_records (Stage 23b).

Доказывает:
  - admin create без подтверждения основания → 422, пользователь не создаётся;
  - создание psychologist/supervisor/admin фиксирует legal basis record
    с актором, IP, user-agent, reference и comment;
  - невалидный basis_type → 422;
  - duplicate email → 409 без новых записей;
  - self-registration студента создаёт consent_records и НЕ создаёт basis;
  - bootstrap-helper пишет legal basis вместо consent-имитации;
  - транзакционность: сбой записи basis откатывает создание пользователя.

Требования: dev PostgreSQL на alembic head (b6e1f4a7c9d3) с seed-данными.
"""

import importlib.util
import uuid as _uuid
from pathlib import Path

import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import ConsentRecord, User, UserLegalBasisRecord
from tests.integration.conftest import create_test_user

PASSWORD = "SecurePass42!"

BODY_OK = {
    "full_name": "Новый Сотрудник Тестович",
    "role":      "psychologist",
    "legal_basis_confirmed": True,
    "basis_type": "employment",
    "basis_reference": "Приказ № 42-к",
    "legal_basis_comment": "Тестовое основание",
}


def _make_admin(client) -> tuple[str, int]:
    """Создаёт админа (роль admin напрямую через auth storage), логинится,
    возвращает (token, admin_id)."""
    admin = auth_storage.save_user({
        "name":            "Integration Admin",
        "email":           f"integ_admin_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _bcrypt_hash(PASSWORD),
        "role":            "admin",
    })
    r = client.post("/api/auth/login", json={
        "email": admin["email"], "password": PASSWORD,
    })
    assert r.status_code == 200
    return r.json()["session_token"], int(admin["id"])


def _bcrypt_hash(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _post_create(client, token: str, body: dict):
    return client.post(
        "/api/admin/users/",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


def _basis_records_for_email(email: str) -> list[UserLegalBasisRecord]:
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            return []
        rows = (
            db.query(UserLegalBasisRecord)
            .filter(UserLegalBasisRecord.user_id == user.id)
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _user_exists(email: str) -> bool:
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).first() is not None


# ─── 1. Валидация подтверждения ───────────────────────────────────────────────

class TestConfirmationRequired:
    def test_missing_confirmation_422(self, client, test_email):
        token, _ = _make_admin(client)
        body = {**BODY_OK, "email": test_email}
        del body["legal_basis_confirmed"]
        r = _post_create(client, token, body)
        assert r.status_code == 422
        assert not _user_exists(test_email)

    def test_false_confirmation_422(self, client, test_email):
        token, _ = _make_admin(client)
        body = {**BODY_OK, "email": test_email, "legal_basis_confirmed": False}
        r = _post_create(client, token, body)
        assert r.status_code == 422
        assert not _user_exists(test_email)

    def test_invalid_basis_type_422(self, client, test_email):
        token, _ = _make_admin(client)
        body = {**BODY_OK, "email": test_email, "basis_type": "patient_consent"}
        r = _post_create(client, token, body)
        assert r.status_code == 422
        assert not _user_exists(test_email)


# ─── 2. Создание staff-ролей фиксирует основание ─────────────────────────────

class TestBasisRecordCreated:
    @pytest.mark.parametrize("role", ["psychologist", "supervisor", "admin"])
    def test_staff_role_gets_basis_record(self, client, test_email, role):
        token, admin_id = _make_admin(client)
        r = _post_create(client, token, {**BODY_OK, "email": test_email, "role": role})
        assert r.status_code == 201

        records = _basis_records_for_email(test_email)
        assert len(records) == 1
        rec = records[0]
        assert rec.basis_type == "employment"
        assert rec.basis_source == "admin_ui"
        assert rec.confirmed_by_user_id == admin_id
        assert rec.confirmed_at is not None

    def test_reference_comment_ip_ua_saved(self, client, test_email):
        token, _ = _make_admin(client)
        r = _post_create(client, token, {**BODY_OK, "email": test_email})
        assert r.status_code == 201

        rec = _basis_records_for_email(test_email)[0]
        assert rec.basis_reference == "Приказ № 42-к"
        assert rec.comment == "Тестовое основание"
        assert rec.ip_address is not None    # 127.0.0.1 от TestClient
        assert rec.user_agent is not None

    def test_duplicate_email_409_no_records(self, client, test_email):
        token, _ = _make_admin(client)
        r1 = _post_create(client, token, {**BODY_OK, "email": test_email})
        assert r1.status_code == 201
        r2 = _post_create(client, token, {**BODY_OK, "email": test_email})
        assert r2.status_code == 409
        # запись основания осталась ровно одна — от первого создания
        assert len(_basis_records_for_email(test_email)) == 1


# ─── 3. Self-registration не создаёт basis records ───────────────────────────

class TestSelfRegistrationUnaffected:
    def test_student_gets_consents_not_basis(self, client, test_email, capture_emails):
        r = client.post("/api/auth/register/init", json={
            "name": "Студент Тестович", "email": test_email, "password": PASSWORD,
        })
        assert r.status_code == 200
        code = capture_emails[test_email][-1]
        r = client.post("/api/auth/register/confirm", json={
            "email": test_email, "code": code,
        })
        assert r.status_code == 201

        with SessionLocal() as db:
            user = db.query(User).filter(User.email == test_email).first()
            assert user is not None
            consents = db.query(ConsentRecord).filter(
                ConsentRecord.user_id == user.id
            ).count()
            basis = db.query(UserLegalBasisRecord).filter(
                UserLegalBasisRecord.user_id == user.id
            ).count()

        assert consents == 2     # privacy_policy + data_processing, как раньше
        assert basis == 0        # студент — субъект согласия, не legal basis


# ─── 4. Bootstrap helper ──────────────────────────────────────────────────────

class TestBootstrapHelper:
    def test_save_legal_basis_for_user(self, client, test_email):
        """create_admin.save_legal_basis_for_user пишет basis, не consent."""
        user = create_test_user(test_email)
        user_id = int(user["id"])

        script_path = (
            Path(__file__).resolve().parents[2] / "scripts" / "create_admin.py"
        )
        spec = importlib.util.spec_from_file_location("create_admin_mod", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        mod.save_legal_basis_for_user(user_id)

        with SessionLocal() as db:
            rec = db.query(UserLegalBasisRecord).filter(
                UserLegalBasisRecord.user_id == user_id
            ).one()
            consents = db.query(ConsentRecord).filter(
                ConsentRecord.user_id == user_id
            ).count()

        assert rec.basis_type == "bootstrap"
        assert rec.basis_source == "bootstrap_script"
        assert rec.confirmed_by_user_id is None
        assert consents == 0     # consent-имитация больше не пишется


# ─── 5. Транзакционность ─────────────────────────────────────────────────────

class TestTransactionRollback:
    def test_basis_failure_rolls_back_user(self, client, test_email, monkeypatch):
        """Если запись основания падает — пользователь не должен остаться в БД."""
        token, _ = _make_admin(client)

        class Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("basis write failed (test)")

        monkeypatch.setattr("app.users.storage.UserLegalBasisRecord", Boom)

        with pytest.raises(RuntimeError, match="basis write failed"):
            _post_create(client, token, {**BODY_OK, "email": test_email})

        assert not _user_exists(test_email)
