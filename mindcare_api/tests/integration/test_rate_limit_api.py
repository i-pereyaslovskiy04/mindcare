"""
API tests for auth rate limiting (Stage 21).

Требования те же, что у остальных integration-тестов: запущенный dev
PostgreSQL на alembic head с seed-данными. Email-транспорт всегда
перехватывается, реальные письма не отправляются.

Лимиты в тестах уменьшаются через monkeypatch RULES, чтобы не делать
десятки bcrypt-запросов; полный матричный контроль значений — в unit-тестах
tests/test_rate_limit.py.
"""

import pytest

from app.core import rate_limit
from tests.integration.conftest import create_test_user

RATE_MESSAGE = "Слишком много попыток. Попробуйте позже."


# ─── 1. Login ─────────────────────────────────────────────────────────────────

class TestLoginRateLimit:
    def test_login_email_limit_returns_429(self, client, test_email):
        """После limit неудачных логинов по email — 429 с единым сообщением."""
        create_test_user(test_email, password="CorrectPass42!")
        limit, _ = rate_limit.RULES["login:email"]

        for _ in range(limit):
            r = client.post("/api/auth/login", json={
                "email": test_email, "password": "WrongPass!!",
            })
            assert r.status_code == 401  # до лимита поведение прежнее

        r = client.post("/api/auth/login", json={
            "email": test_email, "password": "WrongPass!!",
        })
        assert r.status_code == 429
        assert r.json()["detail"] == RATE_MESSAGE

    def test_login_email_limit_blocks_correct_password_too(self, client, test_email):
        """429 действует и для верного пароля — окно должно остыть."""
        create_test_user(test_email, password="CorrectPass42!")
        limit, _ = rate_limit.RULES["login:email"]

        for _ in range(limit):
            client.post("/api/auth/login", json={
                "email": test_email, "password": "WrongPass!!",
            })

        r = client.post("/api/auth/login", json={
            "email": test_email, "password": "CorrectPass42!",
        })
        assert r.status_code == 429

    def test_login_email_limit_case_insensitive(self, client, test_email):
        """Лимит не обходится сменой регистра email."""
        create_test_user(test_email, password="CorrectPass42!")
        limit, _ = rate_limit.RULES["login:email"]

        for _ in range(limit):
            client.post("/api/auth/login", json={
                "email": test_email.upper(), "password": "WrongPass!!",
            })

        r = client.post("/api/auth/login", json={
            "email": test_email, "password": "WrongPass!!",
        })
        assert r.status_code == 429

    def test_login_ip_limit_returns_429(self, client, test_email, monkeypatch):
        """IP-лимит: разные email с одного IP суммируются."""
        monkeypatch.setitem(rate_limit.RULES, "login:ip", (4, 300))
        create_test_user(test_email, password="CorrectPass42!")

        for i in range(4):
            r = client.post("/api/auth/login", json={
                "email": f"integ_noone{i}@example.com", "password": "WrongPass!!",
            })
            assert r.status_code == 401

        r = client.post("/api/auth/login", json={
            "email": test_email, "password": "CorrectPass42!",
        })
        assert r.status_code == 429

    def test_login_under_limit_unchanged(self, client, test_email):
        """До лимита успешный login работает как раньше."""
        create_test_user(test_email, password="CorrectPass42!")
        r = client.post("/api/auth/login", json={
            "email": test_email, "password": "CorrectPass42!",
        })
        assert r.status_code == 200
        assert "session_token" in r.json()


# ─── 2. Password reset init ──────────────────────────────────────────────────

class TestResetInitRateLimit:
    def test_limit_applies_to_nonexistent_email(self, client, capture_emails):
        """
        Anti-enumeration: незарегистрированный email получает те же 200,
        а затем тот же 429, что и существующий — по ответам нельзя понять,
        есть ли аккаунт.
        """
        ghost = "integ_ghost_reset@example.com"
        limit, _ = rate_limit.RULES["reset_init:email"]

        for _ in range(limit):
            r = client.post("/api/auth/password/reset/init", json={"email": ghost})
            assert r.status_code == 200

        r = client.post("/api/auth/password/reset/init", json={"email": ghost})
        assert r.status_code == 429
        assert r.json()["detail"] == RATE_MESSAGE

    def test_limit_applies_to_existing_email_same_shape(
        self, client, test_email, capture_emails, monkeypatch,
    ):
        """Существующий email после лимита получает идентичный 429."""
        # Обходим OTP RESEND_COOLDOWN, чтобы дойти именно до rate limit
        monkeypatch.setattr("app.auth.otp_service.RESEND_COOLDOWN", 0)
        create_test_user(test_email)
        limit, _ = rate_limit.RULES["reset_init:email"]

        for _ in range(limit):
            r = client.post("/api/auth/password/reset/init", json={"email": test_email})
            assert r.status_code == 200

        r = client.post("/api/auth/password/reset/init", json={"email": test_email})
        assert r.status_code == 429
        assert r.json()["detail"] == RATE_MESSAGE


# ─── 3. Register init ─────────────────────────────────────────────────────────

class TestRegisterInitRateLimit:
    def test_register_init_ip_limit(self, client, capture_emails, monkeypatch):
        """IP-лимит на register/init: спам разными email блокируется."""
        monkeypatch.setitem(rate_limit.RULES, "register_init:ip", (3, 900))

        for i in range(3):
            r = client.post("/api/auth/register/init", json={
                "name":     "Test User",
                "email":    f"integ_reg{i}@example.com",
                "password": "SecurePass42!",
            })
            assert r.status_code == 200

        r = client.post("/api/auth/register/init", json={
            "name":     "Test User",
            "email":    "integ_reg_blocked@example.com",
            "password": "SecurePass42!",
        })
        assert r.status_code == 429
        assert r.json()["detail"] == RATE_MESSAGE


# ─── 4. Confirm endpoints ─────────────────────────────────────────────────────

class TestConfirmRateLimit:
    def test_register_confirm_email_limit(self, client, monkeypatch):
        """
        confirm-лимит срабатывает даже без существующей OTP-записи:
        перебор кодов по email блокируется на уровне HTTP.
        """
        monkeypatch.setitem(rate_limit.RULES, "confirm:email", (3, 600))
        ghost = "integ_confirm_ghost@example.com"

        for _ in range(3):
            r = client.post("/api/auth/register/confirm", json={
                "email": ghost, "code": "000000",
            })
            assert r.status_code == 400  # «код не найден» — прежнее поведение

        r = client.post("/api/auth/register/confirm", json={
            "email": ghost, "code": "000000",
        })
        assert r.status_code == 429

    def test_reset_confirm_email_limit(self, client, monkeypatch):
        monkeypatch.setitem(rate_limit.RULES, "confirm:email", (3, 600))
        ghost = "integ_confirm_ghost2@example.com"

        for _ in range(3):
            r = client.post("/api/auth/password/reset/confirm", json={
                "email": ghost, "code": "000000", "new_password": "NewPass4242!",
            })
            assert r.status_code == 400

        r = client.post("/api/auth/password/reset/confirm", json={
            "email": ghost, "code": "000000", "new_password": "NewPass4242!",
        })
        assert r.status_code == 429
