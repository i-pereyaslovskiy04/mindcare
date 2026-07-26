"""
Stage 31m-fix-a — SMTP/auth error sanitization.

Covers:
  - mask_email() pure function (safe-for-logging masking);
  - register_init / password_reset_init return a STABLE client message on email
    send failure (no raw SMTP exception / host / secret leaks into AuthError).

Pure unit tests: storage / otp_service / email_service are patched, no DB.
"""

import smtplib
from unittest.mock import patch

import pytest

from app.core.normalization import mask_email
from app.auth import service


# ─── mask_email ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ("ivan@domain.ru", "i***@domain.ru"),
    ("a@x.ru", "a***@x.ru"),
    ("UPPER@Mail.COM", "U***@Mail.COM"),
])
def test_mask_email_keeps_first_char_and_domain(raw, expected):
    assert mask_email(raw) == expected


@pytest.mark.parametrize("raw", ["", None, "no-at-symbol", "@nodomain", "nolocal@"])
def test_mask_email_invalid_inputs_fall_back(raw):
    assert mask_email(raw) == "***"


def test_mask_email_does_not_leak_local_part():
    masked = mask_email("sensitive.person@clinic.ru")
    assert "sensitive" not in masked
    assert masked == "s***@clinic.ru"


# ─── register_init: email-send failure is sanitized ─────────────────────────────

_SECRET = "smtp.internal.example login failed for admin:supersecret"


def test_register_init_sanitizes_smtp_failure():
    # Domain-allowlist проверка мокается: этот unit-тест изолирует поведение при
    # сбое SMTP, а не email-политику (и остаётся без БД).
    with patch("app.auth.storage.find_user_by_email", return_value=None), \
         patch(
             "app.email_domains.service.assert_email_domain_allowed",
             return_value=None,
         ), \
         patch("app.auth.otp_service.create_or_update_otp", return_value="123456"), \
         patch(
             "app.services.email_service.send_registration_otp",
             side_effect=smtplib.SMTPException(_SECRET),
         ):
        with pytest.raises(service.AuthError) as exc_info:
            service.register_init(
                name="Тест Тестов",
                email="ivan@domain.ru",
                password="password123",
            )

    err = exc_info.value
    assert err.status_code == 500
    assert err.message == "Не удалось отправить письмо. Попробуйте позже."
    # raw SMTP exception / secrets must NOT leak to the client message
    assert _SECRET not in err.message
    assert "smtp" not in err.message.lower()
    assert "SMTPException" not in err.message


def test_password_reset_init_sanitizes_smtp_failure():
    fake_user = {"name": "Тест", "hashed_password": "x"}
    with patch("app.auth.storage.find_user_by_email", return_value=fake_user), \
         patch("app.auth.otp_service.create_or_update_otp", return_value="123456"), \
         patch(
             "app.services.email_service.send_password_reset_otp",
             side_effect=smtplib.SMTPException(_SECRET),
         ):
        with pytest.raises(service.AuthError) as exc_info:
            service.password_reset_init(email="ivan@domain.ru")

    err = exc_info.value
    assert err.status_code == 500
    assert err.message == "Не удалось отправить письмо. Попробуйте позже."
    assert _SECRET not in err.message
