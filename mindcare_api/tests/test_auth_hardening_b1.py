"""
Stage 31m-fix-b1 — auth preparatory hardening (unit, no DB).

Covers:
  - OTP logs mask the email (no full local-part, no OTP/hash leak);
  - _assign_role fails explicitly when the role is missing in the reference
    table (no silent skip), and save_user does not commit a roleless user.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from app.auth.otp_service import create_or_update_otp, verify_otp, _hash_code
from app.auth import storage as auth_storage
from app.auth.storage import _assign_role, save_user
from datetime import datetime, timedelta, timezone


def _mock_session(mock_db):
    """SessionLocal stub yielding mock_db as a context manager."""
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=mock_db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


# ─── 1. OTP log masking ─────────────────────────────────────────────────────────

def test_create_otp_log_masks_email(caplog):
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
        with caplog.at_level(logging.INFO, logger="app.auth.otp_service"):
            code = create_or_update_otp("ivan@domain.ru", "Имя", "pwhash")

    assert "ivan@domain.ru" not in caplog.text          # full email not logged
    assert "i***@domain.ru" in caplog.text               # masked context kept
    assert code not in caplog.text                       # OTP code never logged


def test_verify_otp_ok_log_masks_email(caplog):
    code = "654321"
    rec = MagicMock()
    rec.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    rec.attempts = 0
    rec.code = _hash_code(code)
    rec.name = "Alice"
    rec.password_hash = "pw_hash"

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = rec

    with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
        with caplog.at_level(logging.INFO, logger="app.auth.otp_service"):
            verify_otp("ivan@domain.ru", code)

    assert "ivan@domain.ru" not in caplog.text
    assert "i***@domain.ru" in caplog.text


def test_verify_otp_wrong_code_log_masks_email(caplog):
    rec = MagicMock()
    rec.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
    rec.attempts = 0
    rec.code = _hash_code("111111")

    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = rec

    with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
        with caplog.at_level(logging.INFO, logger="app.auth.otp_service"):
            with pytest.raises(ValueError):
                verify_otp("ivan@domain.ru", "999999")

    assert "ivan@domain.ru" not in caplog.text
    assert "i***@domain.ru" in caplog.text


# ─── 2. _assign_role: no silent skip on missing role ─────────────────────────────

def test_assign_role_raises_when_role_missing():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(RuntimeError, match="not found in roles table"):
        _assign_role(mock_db, user_id=1, role_name="student")

    mock_db.add.assert_not_called()


def test_assign_role_adds_user_role_when_present():
    role = MagicMock()
    role.id = 7
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = role

    _assign_role(mock_db, user_id=42, role_name="student")

    assert mock_db.add.call_count == 1


def test_save_user_does_not_commit_roleless_user():
    """If the student role is missing, save_user must not commit the user."""
    mock_db = MagicMock()
    # flush() is a no-op; the Role lookup (.first()) returns None → missing role
    mock_db.query.return_value.filter.return_value.first.return_value = None

    with patch("app.auth.storage.SessionLocal", _mock_session(mock_db)):
        with pytest.raises(RuntimeError, match="not found in roles table"):
            save_user({"name": "T", "email": "user@mail.ru", "hashed_password": "x"})

    mock_db.commit.assert_not_called()
