"""
Stage 31m-fix-b3 — atomic password reset confirm & change password unit-of-work.

Verifies REAL DB state after success and after injected failures:
  - password reset confirm and authenticated change password update password_hash
    AND revoke all user sessions in a single transaction (one final commit);
  - a failure in any core step (session revoke, OTP consume) rolls back the
    password change AND (for reset) does NOT consume the OTP — no partial state.

Requires dev PostgreSQL on alembic head (seeded roles + consents), EMAIL_MODE=dev.
The cleanup_test_records fixture (conftest) removes integ_*@example.com rows.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth import otp_service, storage, service
from app.db.session import SessionLocal
from app.db.models import OtpVerification, User, UserSession

OLD_PASSWORD = "OldPassword1!"
NEW_PASSWORD = "BrandNewPass9!"
_OTP_PW_HASH = "bcrypt$placeholder-not-read-on-reset"


# ─── helpers ───────────────────────────────────────────────────────────────────

def _make_user(email: str) -> dict:
    """Create an active student user with a known current password."""
    pw_hash = service._hash(OLD_PASSWORD)
    return storage.save_user({
        "name": "Reset Test User",
        "email": email,
        "hashed_password": pw_hash,
        "role": "student",
    })


def _seed_otp(email: str) -> str:
    """Create a password-reset OTP for email; return the plaintext code."""
    return otp_service.create_or_update_otp(email, "Reset Test User", _OTP_PW_HASH)


def _make_session(user_id: str) -> str:
    """Create one active session for the user; return the raw token."""
    token, _ = storage.create_session(user_id)
    return token


def _get_user(db, email):
    return db.query(User).filter(User.email == email).first()


def _get_otp(db, email):
    return db.query(OtpVerification).filter(OtpVerification.email == email).first()


def _active_session_count(db, user_id: int) -> int:
    return (
        db.query(UserSession)
        .filter(UserSession.user_id == user_id, ~UserSession.is_revoked)
        .count()
    )


# ════════════════════════════════════════════════════════════════════════════
# Password reset confirm
# ════════════════════════════════════════════════════════════════════════════

def test_reset_success_changes_password_revokes_sessions_consumes_otp(test_email):
    user = _make_user(test_email)
    _make_session(user["id"])
    _make_session(user["id"])
    code = _seed_otp(test_email)

    service.password_reset_confirm(test_email, code, NEW_PASSWORD)

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(NEW_PASSWORD, u.password_hash)        # new password
        assert not service._verify(OLD_PASSWORD, u.password_hash)    # old rejected
        assert _active_session_count(db, u.id) == 0                  # all revoked
        assert _get_otp(db, test_email) is None                     # OTP consumed


def test_reset_twice_fails_because_otp_consumed(test_email):
    user = _make_user(test_email)
    code = _seed_otp(test_email)

    service.password_reset_confirm(test_email, code, NEW_PASSWORD)

    with pytest.raises(service.AuthError) as exc:
        service.password_reset_confirm(test_email, code, "AnotherPass1!")
    assert exc.value.status_code == 400  # "Код не найден или уже использован"


def test_reset_wrong_otp_keeps_password_and_sessions_and_increments_attempts(test_email):
    user = _make_user(test_email)
    _make_session(user["id"])
    code = _seed_otp(test_email)
    wrong = "654321" if code != "654321" else "123456"

    with pytest.raises(service.AuthError) as exc:
        service.password_reset_confirm(test_email, wrong, NEW_PASSWORD)
    assert exc.value.status_code == 400

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(OLD_PASSWORD, u.password_hash)        # unchanged
        assert _active_session_count(db, u.id) == 1                  # not revoked
        otp = _get_otp(db, test_email)
        assert otp is not None
        assert otp.attempts == 1                                     # attempt counted


def test_reset_expired_otp_keeps_password(test_email):
    user = _make_user(test_email)
    code = _seed_otp(test_email)
    with SessionLocal() as db:
        rec = _get_otp(db, test_email)
        rec.expires_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        )
        db.commit()

    with pytest.raises(service.AuthError) as exc:
        service.password_reset_confirm(test_email, code, NEW_PASSWORD)
    assert exc.value.status_code == 400

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(OLD_PASSWORD, u.password_hash)        # unchanged
        assert _get_otp(db, test_email) is None                     # expired deleted (policy)


def test_reset_revoke_failure_rolls_back_password_and_keeps_otp(test_email, monkeypatch):
    user = _make_user(test_email)
    _make_session(user["id"])
    code = _seed_otp(test_email)

    def boom(db, user_id):
        raise RuntimeError("inject: session revoke failed")

    monkeypatch.setattr(storage, "_revoke_all_user_sessions_in_session", boom)

    with pytest.raises(RuntimeError, match="inject: session revoke"):
        storage.password_reset_confirm_atomic(
            email=test_email, code=code, new_password_hash=service._hash(NEW_PASSWORD),
        )

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(OLD_PASSWORD, u.password_hash)        # rolled back
        assert _active_session_count(db, u.id) == 1                  # still active
        otp = _get_otp(db, test_email)
        assert otp is not None                                       # OTP preserved
        assert otp.attempts == 0                                     # correct code, no burn


def test_reset_otp_consume_failure_rolls_back_everything(test_email, monkeypatch):
    """Failure AFTER password update but BEFORE OTP consume → rollback all."""
    user = _make_user(test_email)
    _make_session(user["id"])
    code = _seed_otp(test_email)

    def boom(db, record):
        raise RuntimeError("inject: otp consume failed")

    monkeypatch.setattr(storage, "_consume_otp", boom)

    with pytest.raises(RuntimeError, match="inject: otp consume"):
        storage.password_reset_confirm_atomic(
            email=test_email, code=code, new_password_hash=service._hash(NEW_PASSWORD),
        )

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(OLD_PASSWORD, u.password_hash)        # rolled back
        assert _active_session_count(db, u.id) == 1                  # not revoked
        otp = _get_otp(db, test_email)
        assert otp is not None                                       # OTP preserved
        assert otp.attempts == 0


def test_reset_user_not_found_keeps_otp(test_email):
    """OTP valid but no user → 404 and OTP NOT consumed (rollback)."""
    code = _seed_otp(test_email)  # no user created for this email

    with pytest.raises(storage.UserNotFoundError):
        storage.password_reset_confirm_atomic(
            email=test_email, code=code, new_password_hash=service._hash(NEW_PASSWORD),
        )

    with SessionLocal() as db:
        assert _get_otp(db, test_email) is not None                 # OTP preserved


# ════════════════════════════════════════════════════════════════════════════
# Change password (authenticated)
# ════════════════════════════════════════════════════════════════════════════

def test_change_success_changes_password_and_revokes_sessions(test_email):
    user = _make_user(test_email)
    _make_session(user["id"])
    _make_session(user["id"])

    service.change_password(user["id"], OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(NEW_PASSWORD, u.password_hash)        # new password
        assert not service._verify(OLD_PASSWORD, u.password_hash)
        assert _active_session_count(db, u.id) == 0                  # all revoked


def test_change_wrong_old_password_keeps_password_and_sessions(test_email):
    user = _make_user(test_email)
    _make_session(user["id"])

    with pytest.raises(service.AuthError) as exc:
        service.change_password(user["id"], "WrongOldPass1!", NEW_PASSWORD, NEW_PASSWORD)
    assert exc.value.status_code == 400

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(OLD_PASSWORD, u.password_hash)        # unchanged
        assert _active_session_count(db, u.id) == 1                  # not revoked


def test_change_revoke_failure_rolls_back_password(test_email, monkeypatch):
    user = _make_user(test_email)
    _make_session(user["id"])

    def boom(db, user_id):
        raise RuntimeError("inject: session revoke failed")

    monkeypatch.setattr(storage, "_revoke_all_user_sessions_in_session", boom)

    with pytest.raises(RuntimeError, match="inject: session revoke"):
        storage.change_password_atomic(
            user_id=user["id"],
            verify_current=lambda h: service._verify(OLD_PASSWORD, h),
            new_password_hash=service._hash(NEW_PASSWORD),
        )

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(OLD_PASSWORD, u.password_hash)        # rolled back
        assert _active_session_count(db, u.id) == 1                  # still active


def test_change_notification_failure_does_not_break_core(test_email, monkeypatch):
    """System-message soft-fail (post-commit) must not roll back password/sessions."""
    user = _make_user(test_email)
    _make_session(user["id"])

    def raise_create(*args, **kwargs):
        raise RuntimeError("inject: system message backend down")

    monkeypatch.setattr("app.chat.storage.create_system_message", raise_create)

    # Must NOT raise — publisher swallows the failure (soft-fail).
    service.change_password(user["id"], OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

    with SessionLocal() as db:
        u = _get_user(db, test_email)
        assert service._verify(NEW_PASSWORD, u.password_hash)        # committed
        assert _active_session_count(db, u.id) == 0                 # revoked
