"""
Tests for application-layer email normalization (Stage 17b).

Covers:
  - normalize_email() pure function
  - otp_service: email normalized before DB insert/lookup/delete
  - auth.storage: email normalized in find_user_by_email, save_user, reactivate_user
  - users.storage: email normalized in create_user

Integration tests (OTP create+verify cross-case with a real DB) are
deferred to Stage 17c API/integration tests.
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.normalization import normalize_email
from app.auth.otp_service import (
    create_or_update_otp,
    delete_otp,
    verify_otp,
    _hash_code,
)
from app.auth.storage import find_user_by_email, reactivate_user, save_user
from app.users.storage import create_user


# ─── helpers ──────────────────────────────────────────────────────────────────

def _mock_session(mock_db):
    """Return a mock SessionLocal class that yields mock_db as context manager."""
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=mock_db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


# ──────────────────────────────────────────────────────────────────────────────
# 1.  normalize_email — pure function
# ──────────────────────────────────────────────────────────────────────────────

class TestNormalizeEmail:
    def test_uppercase_lowercased(self):
        assert normalize_email("User@MAIL.RU") == "user@mail.ru"

    def test_leading_and_trailing_whitespace_stripped(self):
        assert normalize_email(" User@MAIL.RU ") == "user@mail.ru"

    def test_trailing_whitespace_only(self):
        assert normalize_email("user@mail.ru ") == "user@mail.ru"

    def test_leading_whitespace_only(self):
        assert normalize_email(" user@mail.ru") == "user@mail.ru"

    def test_already_normalized_unchanged(self):
        assert normalize_email("user@mail.ru") == "user@mail.ru"

    def test_empty_string(self):
        assert normalize_email("") == ""

    def test_mixed_domain_case(self):
        assert normalize_email("John.Doe@Example.COM") == "john.doe@example.com"


# ──────────────────────────────────────────────────────────────────────────────
# 2.  OTP normalization
# ──────────────────────────────────────────────────────────────────────────────

class TestOTPEmailNormalization:
    def test_create_otp_stores_normalized_email(self):
        """Email is normalized before the OTP record is inserted."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
            create_or_update_otp("User@MAIL.RU", "Name", "hash")

        added = mock_db.add.call_args[0][0]
        assert added.email == "user@mail.ru"

    def test_create_otp_strips_whitespace(self):
        """Whitespace around the email is removed before insert."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
            create_or_update_otp("  user@mail.ru  ", "Name", "hash")

        added = mock_db.add.call_args[0][0]
        assert added.email == "user@mail.ru"

    def test_verify_otp_normalizes_email_before_lookup(self):
        """verify_otp normalizes email; a matching record is found and returned."""
        code = "654321"
        fake_record = MagicMock()
        fake_record.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=1)
        fake_record.attempts = 0
        fake_record.code = _hash_code(code)
        fake_record.name = "Alice"
        fake_record.password_hash = "pw_hash"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = fake_record

        with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
            result = verify_otp("User@MAIL.RU", code)

        assert result == {"name": "Alice", "password_hash": "pw_hash"}

    def test_verify_otp_not_found_raises_expected_error(self):
        """verify_otp with unknown (normalized) email raises the expected ValueError."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
            with pytest.raises(ValueError, match="не найден"):
                verify_otp("User@MAIL.RU", "000000")

    def test_delete_otp_normalizes_and_commits(self):
        """delete_otp normalizes email and commits without exception."""
        mock_db = MagicMock()

        with patch("app.auth.otp_service.SessionLocal", _mock_session(mock_db)):
            delete_otp("  USER@EXAMPLE.COM  ")

        mock_db.commit.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# 3.  auth.storage normalization
# ──────────────────────────────────────────────────────────────────────────────

class TestAuthStorageEmailNormalization:
    def test_find_user_by_email_calls_normalize(self):
        """find_user_by_email passes email through normalize_email."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.auth.storage.SessionLocal", _mock_session(mock_db)), \
             patch("app.auth.storage.normalize_email", wraps=normalize_email) as spy:
            find_user_by_email("User@MAIL.RU")

        spy.assert_called_once_with("User@MAIL.RU")

    def test_save_user_stores_normalized_email(self):
        """save_user writes the normalized email to the User ORM object."""
        mock_db = MagicMock()

        with patch("app.auth.storage.SessionLocal", _mock_session(mock_db)), \
             patch("app.auth.storage._assign_role"), \
             patch("app.auth.storage._user_to_dict", return_value={
                 "id": "1", "name": "T", "email": "user@mail.ru",
                 "hashed_password": "x", "role": "student", "is_active": True,
             }):
            save_user({"name": "T", "email": "User@MAIL.RU", "hashed_password": "x"})

        added = mock_db.add.call_args[0][0]
        assert added.email == "user@mail.ru"

    def test_reactivate_user_calls_normalize(self):
        """reactivate_user passes email through normalize_email."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("app.auth.storage.SessionLocal", _mock_session(mock_db)), \
             patch("app.auth.storage.normalize_email", wraps=normalize_email) as spy:
            reactivate_user("User@MAIL.RU", "Name", "hash")

        spy.assert_called_once_with("User@MAIL.RU")


# ──────────────────────────────────────────────────────────────────────────────
# 4.  users.storage normalization
# ──────────────────────────────────────────────────────────────────────────────

class TestUsersStorageEmailNormalization:
    def test_create_user_stores_normalized_email(self):
        """create_user writes the normalized email to the User ORM object."""
        mock_db = MagicMock()
        # Duplicate-check query: User + two .filter() calls → no existing user
        mock_db.query.return_value.filter.return_value.filter.return_value.first.return_value = None
        # Role-lookup query (multi-role create): Role + one .filter() + .all()
        # → все запрошенные роли существуют.
        role_obj = MagicMock(id=99)
        role_obj.name = "psychologist"  # name — reserved Mock kwarg, ставим явно
        mock_db.query.return_value.filter.return_value.all.return_value = [role_obj]

        mock_new_user = MagicMock()
        mock_new_user.id = 1
        mock_new_user.email = "user@mail.ru"
        mock_new_user.full_name = "Test"
        mock_new_user.is_active = True
        mock_new_user.created_at = datetime.now(timezone.utc).replace(tzinfo=None)
        str(mock_new_user.uuid)  # pre-warm the mock attribute

        with patch("app.users.storage.SessionLocal", _mock_session(mock_db)), \
             patch("app.users.storage.User", return_value=mock_new_user) as mock_user_cls:
            create_user(
                "User@MAIL.RU", "Test", "hash", ["psychologist"],
                basis_reference="Приказ № 1",
            )

        mock_user_cls.assert_called_once()
        assert mock_user_cls.call_args.kwargs["email"] == "user@mail.ru"
