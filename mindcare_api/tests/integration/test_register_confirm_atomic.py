"""
Stage 31m-fix-b2 — atomic registration confirm unit-of-work.

Verifies real DB state after success and after injected failures: a failure in
any core step (consent policy missing, role missing, consent-record insert)
rolls back user + user_roles + consent_records AND does NOT consume the OTP.

Requires dev PostgreSQL on alembic head (seeded roles + consents), EMAIL_MODE=dev.
The cleanup_test_records fixture (conftest) removes integ_*@example.com rows.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import otp_service, storage, service
from app.db.session import SessionLocal
from app.db.models import ConsentRecord, OtpVerification, User, UserRole

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
