"""
Tests for change_password() in app/auth/service.py.

Tests the service layer with mocked storage — no database required.
Consistent with test_encryption.py (pure unit tests, no HTTP layer).

Stage 31m-fix-b3: change_password now делегирует обновление пароля и отзыв
сессий единой атомарной storage-функции change_password_atomic (один commit).
Поэтому юнит-тесты мокают change_password_atomic вместо двух раздельных
функций update_user_password / revoke_all_user_sessions. Реальная атомарность
и поведение БД проверяются в tests/integration/test_password_uow_atomic.py.
"""

import pytest
from unittest.mock import patch

from app.auth import storage
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


# ── Validation (происходит до любого обращения к storage) ──────────────────────

class TestChangePasswordValidation:
    def test_mismatch_confirm_raises_422(self):
        with patch("app.auth.service.storage.change_password_atomic") as mock_atomic:
            with pytest.raises(AuthError) as exc:
                change_password("42", OLD_PASSWORD, NEW_PASSWORD, "Different!")
            assert exc.value.status_code == 422
            mock_atomic.assert_not_called()

    def test_too_short_new_password_raises_422(self):
        with patch("app.auth.service.storage.change_password_atomic") as mock_atomic:
            with pytest.raises(AuthError) as exc:
                change_password("42", OLD_PASSWORD, "short", "short")
            assert exc.value.status_code == 422
            mock_atomic.assert_not_called()

    def test_exactly_8_chars_is_accepted(self, fake_user):
        with patch("app.auth.service.storage.change_password_atomic", return_value=fake_user), \
             patch("app.chat.system_publisher.publish_system_message"):
            change_password("42", OLD_PASSWORD, "Abcd1234", "Abcd1234")

    def test_7_chars_rejected(self):
        with patch("app.auth.service.storage.change_password_atomic") as mock_atomic:
            with pytest.raises(AuthError) as exc:
                change_password("42", OLD_PASSWORD, "Abcd123", "Abcd123")
            assert exc.value.status_code == 422
            mock_atomic.assert_not_called()


# ── Wrong current password (проверяется внутри атомарной транзакции) ───────────

class TestWrongCurrentPassword:
    def test_wrong_current_password_raises_400(self):
        with patch(
            "app.auth.service.storage.change_password_atomic",
            side_effect=storage.InvalidCurrentPasswordError("Неверный текущий пароль"),
        ):
            with pytest.raises(AuthError) as exc:
                change_password("42", "WrongPassword!", NEW_PASSWORD, NEW_PASSWORD)
            assert exc.value.status_code == 400

    def test_wrong_password_does_not_publish_notification(self):
        """Сбой проверки пароля не должен порождать post-commit side effects."""
        with patch(
            "app.auth.service.storage.change_password_atomic",
            side_effect=storage.InvalidCurrentPasswordError("Неверный текущий пароль"),
        ), patch("app.chat.system_publisher.publish_system_message") as mock_pub:
            with pytest.raises(AuthError):
                change_password("42", "WrongPassword!", NEW_PASSWORD, NEW_PASSWORD)
            mock_pub.assert_not_called()

    def test_verify_callback_rejects_wrong_password(self, fake_user):
        """
        Callback verify_current, передаваемый в storage, должен возвращать False
        для неверного и True для верного текущего пароля — это и есть проверка,
        которую storage выполняет внутри транзакции.
        """
        captured = {}

        def capture(user_id, verify_current, new_password_hash):
            captured["verify"] = verify_current
            return fake_user

        with patch("app.auth.service.storage.change_password_atomic", side_effect=capture), \
             patch("app.chat.system_publisher.publish_system_message"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

        verify = captured["verify"]
        assert verify(fake_user["hashed_password"]) is True
        assert verify(_hash("CompletelyDifferent9")) is False


# ── User not found ────────────────────────────────────────────────────────────

class TestUserNotFound:
    def test_user_not_found_raises_404(self):
        with patch(
            "app.auth.service.storage.change_password_atomic",
            side_effect=storage.UserNotFoundError("Пользователь не найден"),
        ):
            with pytest.raises(AuthError) as exc:
                change_password("99", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
            assert exc.value.status_code == 404


# ── Successful change ─────────────────────────────────────────────────────────

class TestChangePasswordSuccess:
    def test_success_calls_atomic_with_user_id(self, fake_user):
        with patch("app.auth.service.storage.change_password_atomic", return_value=fake_user) as mock_atomic, \
             patch("app.chat.system_publisher.publish_system_message"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
            mock_atomic.assert_called_once()
            assert mock_atomic.call_args.kwargs["user_id"] == "42"

    def test_success_publishes_notification(self, fake_user):
        with patch("app.auth.service.storage.change_password_atomic", return_value=fake_user), \
             patch("app.chat.system_publisher.publish_system_message") as mock_pub:
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)
            mock_pub.assert_called_once()
            assert mock_pub.call_args.kwargs["recipient_id"] == 42

    def test_new_hash_verifies_with_new_password(self, fake_user):
        captured = {}

        def capture(user_id, verify_current, new_password_hash):
            captured["hash"] = new_password_hash
            return fake_user

        with patch("app.auth.service.storage.change_password_atomic", side_effect=capture), \
             patch("app.chat.system_publisher.publish_system_message"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

        assert _verify(NEW_PASSWORD, captured["hash"])

    def test_new_hash_rejects_old_password(self, fake_user):
        captured = {}

        def capture(user_id, verify_current, new_password_hash):
            captured["hash"] = new_password_hash
            return fake_user

        with patch("app.auth.service.storage.change_password_atomic", side_effect=capture), \
             patch("app.chat.system_publisher.publish_system_message"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

        assert not _verify(OLD_PASSWORD, captured["hash"])

    def test_no_plaintext_password_in_stdout(self, fake_user, capsys):
        with patch("app.auth.service.storage.change_password_atomic", return_value=fake_user), \
             patch("app.chat.system_publisher.publish_system_message"):
            change_password("42", OLD_PASSWORD, NEW_PASSWORD, NEW_PASSWORD)

        captured = capsys.readouterr()
        assert OLD_PASSWORD not in captured.out
        assert OLD_PASSWORD not in captured.err
        assert NEW_PASSWORD not in captured.out
        assert NEW_PASSWORD not in captured.err
