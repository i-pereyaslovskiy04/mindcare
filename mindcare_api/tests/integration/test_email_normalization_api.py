"""
API/integration tests: email normalization in auth flows (Stage 17c).

Tests real HTTP endpoints backed by the dev PostgreSQL database.  Each test
uses a unique integ_*@example.com address that is deleted from the DB after
the test by the autouse cleanup_test_records fixture in conftest.py.

Prerequisites (must be true when this file runs):
  - PostgreSQL dev DB is running
  - alembic upgrade head has been applied
  - Seed data includes privacy_policy + data_processing consents
  - EMAIL_MODE=dev (default) — emails intercepted, not sent

Covered scenarios:
  A. Login with mixed-case email (find_user_by_email normalization)
  B. Register init/confirm cross-case (OTP create + verify normalization)
  C. Password reset init/confirm cross-case (reset OTP normalization)
  D. Duplicate detection for mixed-case email (create_user normalization)

Deferred to Stage 17d:
  - Admin-created user cross-case (requires admin session setup)
  - DB-level functional unique index lower(email)
"""

import pytest

from app.db.session import SessionLocal
from app.db.models import User

from tests.integration.conftest import create_test_user

_PASS     = "SecurePass42!"
_NEW_PASS = "NewSecurePass99!"


# ─── A: Login ─────────────────────────────────────────────────────────────────

class TestLoginEmailNormalization:
    """
    auth.storage.find_user_by_email() normalizes the email before the DB filter.
    A user stored as lowercase must be findable via uppercase / mixed-case login.
    """

    def test_login_uppercase_local_part(self, client, test_email):
        """User stored with lowercase; login with all-uppercase local part succeeds."""
        create_test_user(test_email, _PASS)

        # e.g. "integ_abc@example.com" → "INTEG_ABC@EXAMPLE.COM"
        # pydantic EmailStr lowercases domain → "INTEG_ABC@example.com"
        # find_user_by_email normalizes → "integ_abc@example.com" → found
        resp = client.post("/api/auth/login", json={
            "email":    test_email.upper(),
            "password": _PASS,
        })
        assert resp.status_code == 200, resp.text
        assert "session_token" in resp.json()

    def test_login_mixed_case_local_part(self, client, test_email):
        """User stored with lowercase; login with capitalized first letter succeeds."""
        create_test_user(test_email, _PASS)

        local, domain = test_email.split("@")
        mixed = local.capitalize() + "@" + domain  # "Integ_abc@example.com"

        resp = client.post("/api/auth/login", json={
            "email":    mixed,
            "password": _PASS,
        })
        assert resp.status_code == 200, resp.text
        assert "session_token" in resp.json()

    def test_login_wrong_password_returns_401(self, client, test_email):
        """Sanity check: wrong password returns 401 regardless of email case."""
        create_test_user(test_email, _PASS)
        resp = client.post("/api/auth/login", json={
            "email":    test_email,
            "password": "WrongPassword!",
        })
        assert resp.status_code == 401, resp.text

    def test_user_email_stored_normalized(self, client, test_email):
        """User created via storage helper is stored with normalized (lowercase) email."""
        create_test_user(test_email, _PASS)
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == test_email).first()
            assert user is not None
            assert user.email == test_email  # lowercase


# ─── B: Register init / confirm ───────────────────────────────────────────────

class TestRegisterEmailNormalization:
    """
    otp_service.create_or_update_otp() normalizes email before DB insert.
    otp_service.verify_otp() normalizes email before DB lookup.

    Core scenario: init("Integ_abc@example.com") stores OTP for "integ_abc@example.com".
    confirm("integ_abc@example.com") normalizes the same way → OTP is found.
    """

    def test_register_cross_case_init_then_confirm(self, client, test_email, capture_emails):
        """
        Register/init with mixed-case local part; confirm with lowercase → 201 created.
        This is the primary Stage 17b regression test at the API level.
        """
        local, domain = test_email.split("@")
        email_init = local.capitalize() + "@" + domain  # "Integ_abc@example.com"

        # ── Step 1: register/init with mixed-case email
        resp = client.post("/api/auth/register/init", json={
            "name":     "Integration Test",
            "email":    email_init,
            "password": _PASS,
        })
        assert resp.status_code == 200, resp.text

        # send_email was called with the pre-normalization address
        assert email_init in capture_emails, (
            f"Expected email sent to '{email_init}'. "
            f"Captured recipients: {list(capture_emails.keys())}"
        )
        code = capture_emails[email_init][-1]

        # ── Step 2: confirm with lowercase (different case from init)
        resp = client.post("/api/auth/register/confirm", json={
            "email": test_email,   # lowercase  ← differs from init case
            "code":  code,
        })
        assert resp.status_code == 201, resp.text

        # Verify user stored with normalized (lowercase) email
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == test_email).first()
            assert user is not None, f"No user found for '{test_email}'"
            assert user.email == test_email

    def test_register_same_case_baseline(self, client, test_email, capture_emails):
        """Baseline: init and confirm with same lowercase email → always works."""
        resp = client.post("/api/auth/register/init", json={
            "name":     "Baseline Test",
            "email":    test_email,
            "password": _PASS,
        })
        assert resp.status_code == 200, resp.text
        assert test_email in capture_emails
        code = capture_emails[test_email][-1]

        resp = client.post("/api/auth/register/confirm", json={
            "email": test_email,
            "code":  code,
        })
        assert resp.status_code == 201, resp.text

    def test_register_wrong_code_returns_400(self, client, test_email, capture_emails):
        """Sanity check: wrong OTP code returns 400."""
        resp = client.post("/api/auth/register/init", json={
            "name":     "Wrong Code Test",
            "email":    test_email,
            "password": _PASS,
        })
        assert resp.status_code == 200, resp.text

        resp = client.post("/api/auth/register/confirm", json={
            "email": test_email,
            "code":  "000000",
        })
        assert resp.status_code == 400, resp.text


# ─── C: Password reset init / confirm ─────────────────────────────────────────

class TestPasswordResetEmailNormalization:
    """
    Password reset OTP flow normalizes email in create_or_update_otp and verify_otp.
    """

    def test_reset_cross_case_init_then_confirm(self, client, test_email, capture_emails):
        """
        Reset/init with mixed-case; confirm/confirm with lowercase → password changed.
        """
        create_test_user(test_email, _PASS)

        local, domain = test_email.split("@")
        email_init = local.capitalize() + "@" + domain  # "Integ_abc@example.com"

        # ── Step 1: reset/init with mixed-case email
        resp = client.post("/api/auth/password/reset/init", json={"email": email_init})
        assert resp.status_code == 200, resp.text

        assert email_init in capture_emails, (
            f"Expected email sent to '{email_init}'. "
            f"Captured recipients: {list(capture_emails.keys())}"
        )
        code = capture_emails[email_init][-1]

        # ── Step 2: reset/confirm with lowercase email ← differs from init case
        resp = client.post("/api/auth/password/reset/confirm", json={
            "email":        test_email,
            "code":         code,
            "new_password": _NEW_PASS,
        })
        assert resp.status_code == 200, resp.text

        # Verify new password works
        resp = client.post("/api/auth/login", json={
            "email":    test_email,
            "password": _NEW_PASS,
        })
        assert resp.status_code == 200, resp.text
        assert "session_token" in resp.json()

    def test_reset_old_password_rejected_after_reset(self, client, test_email, capture_emails):
        """After a password reset the old password must no longer authenticate."""
        create_test_user(test_email, _PASS)

        local, domain = test_email.split("@")
        email_init = local.capitalize() + "@" + domain

        client.post("/api/auth/password/reset/init", json={"email": email_init})
        code = capture_emails[email_init][-1]
        client.post("/api/auth/password/reset/confirm", json={
            "email":        test_email,
            "code":         code,
            "new_password": _NEW_PASS,
        })

        resp = client.post("/api/auth/login", json={
            "email":    test_email,
            "password": _PASS,   # OLD password
        })
        assert resp.status_code == 401, resp.text

    def test_reset_init_silent_for_unknown_email(self, client, test_email):
        """Reset/init for unknown email returns 200 — no information disclosure."""
        resp = client.post("/api/auth/password/reset/init", json={"email": test_email})
        assert resp.status_code == 200, resp.text


# ─── D: Duplicate detection ───────────────────────────────────────────────────

class TestDuplicateEmailNormalization:
    """
    Registration duplicate check normalizes email before the DB lookup.
    Mixed-case variant of an existing email must be treated as duplicate.
    """

    def test_register_init_rejects_duplicate_different_case(self, client, test_email):
        """
        User exists with lowercase email.
        Register/init with uppercase local part returns 409 Conflict.
        """
        create_test_user(test_email, _PASS)

        local, domain = test_email.split("@")
        email_upper_local = local.upper() + "@" + domain  # "INTEG_ABC@example.com"

        resp = client.post("/api/auth/register/init", json={
            "name":     "Duplicate",
            "email":    email_upper_local,
            "password": _PASS,
        })
        assert resp.status_code == 409, (
            f"Expected 409 Conflict, got {resp.status_code}: {resp.text}"
        )
