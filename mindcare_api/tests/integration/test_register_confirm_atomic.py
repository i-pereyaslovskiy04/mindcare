"""
Stage 31m-fix-b2 — atomic registration confirm unit-of-work.

Verifies real DB state after success and after injected failures: a failure in
any core step (consent policy missing, role missing, consent-record insert)
rolls back user + user_roles + consent_records AND does NOT consume the OTP.

Requires dev PostgreSQL on alembic head (seeded roles + consents), EMAIL_MODE=dev.
The cleanup_test_records fixture (conftest) removes integ_*@example.com rows.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import otp_service, storage, service
from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, AuthLog, ConsentRecord, OtpVerification, Role, User, UserRole,
)

_PW_HASH = "bcrypt$placeholder-not-verified-at-confirm"


def _seed_otp(email: str) -> str:
    """Create an OTP record for email; return the plaintext code."""
    return otp_service.create_or_update_otp(email, "Тест Тестов", _PW_HASH)


def _get_user(db, email):
    return db.query(User).filter(User.email == email).first()


def _get_otp(db, email):
    return db.query(OtpVerification).filter(OtpVerification.email == email).first()


# ─── success ─────────────────────────────────────────────────────────────────

def test_atomic_success_creates_user_role_consents_and_consumes_otp(test_email):
    code = _seed_otp(test_email)

    user = storage.register_confirm_atomic(
        email=test_email,
        code=code,
        required_consent_types=service.REQUIRED_CONSENTS,
        ip="127.0.0.1",
        user_agent="pytest-agent/1.0",
    )
    assert user["role"] == "student"

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert u is not None
        roles = db.query(UserRole).filter(UserRole.user_id == u.id).all()
        assert len(roles) >= 1
        recs = db.query(ConsentRecord).filter(ConsentRecord.user_id == u.id).all()
        assert len(recs) == len(service.REQUIRED_CONSENTS)
        for r in recs:
            assert r.ip_address is not None
            assert r.user_agent == "pytest-agent/1.0"
        assert _get_otp(db, test_email) is None          # OTP consumed


def test_confirm_twice_fails_because_otp_consumed(test_email):
    code = _seed_otp(test_email)
    storage.register_confirm_atomic(
        email=test_email, code=code,
        required_consent_types=service.REQUIRED_CONSENTS,
    )
    with pytest.raises(ValueError, match="не найден"):
        storage.register_confirm_atomic(
            email=test_email, code=code,
            required_consent_types=service.REQUIRED_CONSENTS,
        )


# ─── failure injection: rollback + OTP preserved ──────────────────────────────

def test_second_consent_failure_rolls_back_all_and_keeps_otp(test_email, monkeypatch):
    code = _seed_otp(test_email)

    real_cr = storage.ConsentRecord
    state = {"n": 0}

    def flaky_consent_record(*args, **kwargs):
        state["n"] += 1
        if state["n"] == 2:                      # fail on the 2nd consent record
            raise RuntimeError("inject: second consent record failed")
        return real_cr(*args, **kwargs)

    monkeypatch.setattr(storage, "ConsentRecord", flaky_consent_record)

    with pytest.raises(RuntimeError, match="inject: second consent"):
        storage.register_confirm_atomic(
            email=test_email, code=code,
            required_consent_types=service.REQUIRED_CONSENTS,
            ip="127.0.0.1", user_agent="ua",
        )

    with SessionLocal() as db:
        assert _get_user(db, test_email) is None          # user rolled back
        otp = _get_otp(db, test_email)
        assert otp is not None                            # OTP NOT consumed
        assert otp.attempts == 0                          # correct code didn't burn attempt


def test_role_assignment_failure_rolls_back_and_keeps_otp(test_email, monkeypatch):
    code = _seed_otp(test_email)

    def boom(db, user_id, role_name="student"):
        raise storage.RegistrationDataError("inject: role missing")

    monkeypatch.setattr(storage, "_assign_role", boom)

    with pytest.raises(storage.RegistrationDataError):
        storage.register_confirm_atomic(
            email=test_email, code=code,
            required_consent_types=service.REQUIRED_CONSENTS,
        )

    with SessionLocal() as db:
        assert _get_user(db, test_email) is None
        assert _get_otp(db, test_email) is not None       # OTP preserved


def test_missing_consent_policy_no_user_and_keeps_otp(test_email):
    code = _seed_otp(test_email)

    with pytest.raises(storage.RegistrationDataError):
        storage.register_confirm_atomic(
            email=test_email, code=code,
            required_consent_types=["privacy_policy", "nonexistent_policy_xyz"],
        )

    with SessionLocal() as db:
        assert _get_user(db, test_email) is None
        assert _get_otp(db, test_email) is not None       # OTP preserved


# ─── OTP error paths ──────────────────────────────────────────────────────────

def test_wrong_code_no_user_and_attempt_incremented(test_email):
    code = _seed_otp(test_email)
    wrong = "654321" if code != "654321" else "123456"

    with pytest.raises(ValueError, match="Неверный код"):
        storage.register_confirm_atomic(
            email=test_email, code=wrong,
            required_consent_types=service.REQUIRED_CONSENTS,
        )

    with SessionLocal() as db:
        assert _get_user(db, test_email) is None
        otp = _get_otp(db, test_email)
        assert otp is not None
        assert otp.attempts == 1                          # wrong attempt counted


def test_expired_otp_no_user(test_email):
    code = _seed_otp(test_email)
    with SessionLocal() as db:
        rec = _get_otp(db, test_email)
        rec.expires_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        )  # naive UTC, как хранит OtpVerification
        db.commit()

    with pytest.raises(ValueError, match="истёк"):
        storage.register_confirm_atomic(
            email=test_email, code=code,
            required_consent_types=service.REQUIRED_CONSENTS,
        )

    with SessionLocal() as db:
        assert _get_user(db, test_email) is None
        assert _get_otp(db, test_email) is None           # expired OTP deleted (policy)


# ─── Stage 5A-1: user_reactivated lifecycle event ─────────────────────────────

def _reactivated_rows(user_id):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "user_reactivated",
                AuditLog.entity_type == "user",
                AuditLog.entity_id == user_id,
            )
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _registration_succeeded_count(user_id):
    with SessionLocal() as db:
        return (
            db.query(AuthLog)
            .filter(
                AuthLog.event == "registration_succeeded",
                AuthLog.user_id == user_id,
            )
            .count()
        )


def _soft_delete(user_id):
    with SessionLocal() as db:
        u = db.query(User).filter(User.id == user_id).first()
        u.deleted_at = datetime.now(timezone.utc)
        u.is_active = False
        db.commit()


def test_new_registration_writes_no_user_reactivated(test_email):
    # Новая (не восстановление) регистрация НЕ пишет user_reactivated.
    code = _seed_otp(test_email)
    user = storage.register_confirm_atomic(
        email=test_email, code=code,
        required_consent_types=service.REQUIRED_CONSENTS,
        ip="127.0.0.1", user_agent="ua",
    )
    assert _reactivated_rows(user["id"]) == []


def test_reactivation_of_soft_deleted_writes_single_user_reactivated(test_email):
    # 1. Первичная регистрация (new) → user_reactivated НЕ пишется.
    code = _seed_otp(test_email)
    user = storage.register_confirm_atomic(
        email=test_email, code=code,
        required_consent_types=service.REQUIRED_CONSENTS,
        ip="127.0.0.1", user_agent="ua",
    )
    uid = user["id"]
    # storage отдаёт id строкой, а audit_log.user_id/entity_id — INTEGER:
    # сравнивать надо с приведённым значением, иначе '1170' != 1170.
    uid_int = int(uid)
    assert _reactivated_rows(uid) == []

    # 2. Soft-delete того же аккаунта.
    _soft_delete(uid)

    # 3. Повторное подтверждение с новым OTP → ветка реактивации.
    code2 = _seed_otp(test_email)
    user2 = storage.register_confirm_atomic(
        email=test_email, code=code2,
        required_consent_types=service.REQUIRED_CONSENTS,
        ip="127.0.0.1", user_agent="ua",
    )
    assert user2["id"] == uid                     # тот же аккаунт восстановлен

    rows = _reactivated_rows(uid)
    assert len(rows) == 1                          # ровно одно событие
    row = rows[0]
    assert row.entity_type == "user" and row.entity_id == uid_int
    assert row.user_id == uid_int                  # actor == восстановленный student
    assert row.user_role == "student"
    assert (row.log_metadata or {}) == {}
    assert row.description is None
    assert row.outcome == "success"
    assert row.failure_reason_code is None


def test_http_reactivation_coexists_with_registration_succeeded(client, test_email):
    # user_reactivated (AUDIT_LOG, storage) сосуществует с registration_succeeded
    # (AUTH_LOG, route). Первичная регистрация — через storage; повторное
    # подтверждение — через HTTP-роут, который пишет registration_succeeded.
    code = _seed_otp(test_email)
    user = storage.register_confirm_atomic(
        email=test_email, code=code,
        required_consent_types=service.REQUIRED_CONSENTS,
        ip="127.0.0.1", user_agent="ua",
    )
    uid = user["id"]
    assert _registration_succeeded_count(uid) == 0   # storage-путь не пишет auth_log

    _soft_delete(uid)

    # Точные before/after для обоих журналов.
    react_before = len(_reactivated_rows(uid))
    regsucc_before = _registration_succeeded_count(uid)

    code2 = _seed_otp(test_email)
    r = client.post(
        "/api/auth/register/confirm",
        json={"email": test_email, "code": code2},
    )
    assert r.status_code == 201, r.text

    assert len(_reactivated_rows(uid)) == react_before + 1      # AUDIT_LOG lifecycle
    assert _registration_succeeded_count(uid) == regsucc_before + 1  # AUTH_LOG


# ─── Stage 5A-1 security: только чистый student реактивируется публично ─────────

def _create_soft_deleted_with_roles(email, role_names):
    """Создаёт soft-deleted User с заданными активными ролями. Возвращает id."""
    with SessionLocal() as db:
        u = User(
            full_name="Staff Тестов", email=normalize_email(email),
            password_hash=_PW_HASH, is_active=False,
            deleted_at=datetime.now(timezone.utc),
        )
        db.add(u)
        db.flush()
        for rn in role_names:
            role = db.query(Role).filter(Role.name == rn).first()
            assert role is not None, f"seed role missing: {rn}"
            db.add(UserRole(user_id=u.id, role_id=role.id))
        db.commit()
        return u.id


def _staff_email(test_email, tag):
    local, _, domain = test_email.partition("@")
    return f"{local}_{tag}@{domain}"


def _registration_failed_rows(email):
    """registration_failed AuthLog-строки для нормализованного email,
    детерминированно упорядоченные (created_at, id)."""
    with SessionLocal() as db:
        rows = (
            db.query(AuthLog)
            .filter(
                AuthLog.event == "registration_failed",
                AuthLog.user_email == normalize_email(email),
            )
            .order_by(AuthLog.created_at.asc(), AuthLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


@pytest.mark.parametrize("role_names", [
    ["admin"], ["psychologist"], ["supervisor"], ["student", "admin"],
])
def test_soft_deleted_staff_not_reactivated_by_public_registration(
    client, test_email, role_names,
):
    email = _staff_email(test_email, "_".join(role_names))
    uid = _create_soft_deleted_with_roles(email, role_names)
    code = _seed_otp(email)

    failed_before = len(_registration_failed_rows(email))

    r = client.post(
        "/api/auth/register/confirm", json={"email": email, "code": code},
    )
    # Generic internal_error — существование аккаунта/ролей не раскрывается.
    assert r.status_code == 500, r.text
    body_text = json.dumps(r.json(), ensure_ascii=False).lower()
    for leak in ("admin", "supervisor", "psychologist", "staff", "role", "роль"):
        assert leak not in body_text

    with SessionLocal() as db:
        u = db.query(User).filter(User.id == uid).first()
        assert u.deleted_at is not None          # НЕ реактивирован
        assert u.is_active is False
        assert _get_otp(db, email) is not None    # OTP НЕ потреблён

    assert _reactivated_rows(uid) == []           # нет user_reactivated

    # registration_failed: ровно одна новая строка — durable audit_code контракт.
    failed_rows = _registration_failed_rows(email)
    assert len(failed_rows) == failed_before + 1
    row = failed_rows[-1]                          # последняя добавленная строка
    assert row.success is False
    assert row.failure_reason == "internal_error"
    assert row.user_id is None                     # actor anonymous (pre-auth)
    assert row.session_id is None
    for rn in role_names:
        assert rn not in (row.failure_reason or "")
    # Никаких raw exception details (класс исключения/сообщение) в текстовых
    # полях AuthLog — только стабильный код internal_error.
    for field in (row.failure_reason, row.user_agent):
        text = (field or "")
        assert "SelfReactivationNotAllowedError" not in text
        assert "Traceback" not in text
        assert "self-reactivation" not in text


# ─── welcome system message soft-fail does not break registration ─────────────

def test_welcome_message_failure_does_not_break_registration(test_email, monkeypatch):
    code = _seed_otp(test_email)

    # Make the system-message storage raise; publisher must swallow it (soft-fail)
    # and service.register_confirm must still return the created user.
    def raise_create(*args, **kwargs):
        raise RuntimeError("inject: system message backend down")

    monkeypatch.setattr("app.chat.storage.create_system_message", raise_create)

    user = service.register_confirm(
        email=test_email, code=code, ip="127.0.0.1", user_agent="ua",
    )
    assert user["role"] == "student"

    with SessionLocal() as db:
        assert _get_user(db, test_email) is not None      # registration committed
        assert _get_otp(db, test_email) is None           # OTP consumed
