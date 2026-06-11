"""
Tests for change_password() in app/auth/service.py.

Tests the service layer with mocked storage — no database required.
Consistent with test_encryption.py (pure unit tests, no HTTP layer).
"""

import pytest
from unittest.mock import patch, call

from app.auth.service import change_password, AuthError, _hash, _verify


# ── Fixtures ──────────────────────────────────────────────────────────────────

OLD_PASSWORD = "OldPassword1"
NEW_PASSWORD = "NewPassword1!"


@pytest.fixture()
def fake_user():
    return {
        "id": "42",
        "email": "test@example.com",
        "name": "Test User",
        "hashed_password": _hash(OLD_PASSWORD),
        "role": "student",
        "is_active": True,
    }


# ── Validation ────────────────────────────────────────────────────────────────

class TestChangePasswordValidation:
    def test_mismatch_confirm_raises_422(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user):
            with pytest.raises(AuthError) as exc:
                change_password("42", OLD_PASSWORD, NEW_PASSWORD, "Different!")
            assert exc.value.status_code == 422

    def test_too_short_new_password_raises_422(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user):
            with pytest.raises(AuthError) as exc:
                change_password("42", OLD_PASSWORD, "short", "short")
            assert exc.value.status_code == 422

    def test_exactly_8_chars_is_accepted(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.update_user_password"), \
             patch("app.auth.service.storage.revoke_all_user_sessions"):
            change_password("42", OLD_PASSWORD, "Abcd1234", "Abcd1234")

    def test_7_chars_rejected(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user):
            with pytest.raises(AuthError) as exc:
                change_password("42", OLD_PASSWORD, "Abcd123", "Abcd123")
            assert exc.value.status_code == 422


# ── Wrong current password ────────────────────────────────────────────────────

class TestWrongCurrentPassword:
    def test_wrong_current_password_raises_400(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user):
            with pytest.raises(AuthError) as exc:
                change_password("42", "WrongPassword!", NEW_PASSWORD, NEW_PASSWORD)
            assert exc.value.status_code == 400

    def test_wrong_password_does_not_update(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.update_user_password") as mock_update:
            with pytest.raises(AuthError):
                change_password("42", "WrongPassword!", NEW_PASSWORD, NEW_PASSWORD)
            mock_update.assert_not_called()

    def test_wrong_password_does_not_revoke_sessions(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.revoke_all_user_sessions") as mock_revoke:
            with pytest.raises(AuthError):
                change_password("42", "WrongPassword!", NEW_PASSWORD, NEW_PASSWORD)
            mock_revoke.assert_not_called()


# ── User not found ────────────────────────────────────────────────────────────

class TestUserNotFound:
    def test_user_not_found_raises_404(self):
        with patch("app.auth.service.storage.find_user_by_id", return_value=None):
            with pytest.raises(AuthError) as exc:
                change_password("99", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
            assert exc.value.status_code == 404


# ── Successful change ─────────────────────────────────────────────────────────

class TestChangePasswordSuccess:
    def test_success_calls_update_password(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.update_user_password") as mock_update, \
             patch("app.auth.service.storage.revoke_all_user_sessions"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
            mock_update.assert_called_once()
            call_user_id = mock_update.call_args[0][0]
            assert call_user_id == "42"

    def test_success_calls_revoke_all_sessions(self, fake_user):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.update_user_password"), \
             patch("app.auth.service.storage.revoke_all_user_sessions") as mock_revoke:
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
            mock_revoke.assert_called_once_with("42")

    def test_new_hash_verifies_with_new_password(self, fake_user):
        captured = {}

        def capture_update(user_id, password_hash):
            captured["hash"] = password_hash

        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.update_user_password", side_effect=capture_update), \
             patch("app.auth.service.storage.revoke_all_user_sessions"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

        assert _verify(NEW_PASSWORD, captured["hash"])

    def test_new_hash_rejects_old_password(self, fake_user):
        captured = {}

        def capture_update(user_id, password_hash):
            captured["hash"] = password_hash

        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.update_user_password", side_effect=capture_update), \
             patch("app.auth.service.storage.revoke_all_user_sessions"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

        assert not _verify(OLD_PASSWORD, captured["hash"])

    def test_no_plaintext_password_in_stdout(self, fake_user, capsys):
        with patch("app.auth.service.storage.find_user_by_id", return_value=fake_user), \
             patch("app.auth.service.storage.update_user_password"), \
             patch("app.auth.service.storage.revoke_all_user_sessions"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

        captured = capsys.readouterr()
        assert OLD_PASSWORD not in captured.out
        assert OLD_PASSWORD not in captured.err
        assert NEW_PASSWORD not in captured.out
        assert NEW_PASSWORD not in captured.err
