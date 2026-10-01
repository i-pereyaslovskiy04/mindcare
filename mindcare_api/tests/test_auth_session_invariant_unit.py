"""
Stage Social Auth 2A — unit-тесты auth-инвариантов без БД (storage замокан).

  * ensure_user_can_start_session — единая проверка «можно ли выдать сессию»
    (is_active / роли), общая для password и будущего social login;
  * password_hash=None (social-only) → тот же 401, что неверный пароль, без
    исключений bcrypt и с выравниванием времени (bcrypt выполняется всегда);
  * change_password без пароля → 409, а не 500;
  * password_reset_init не копирует текущий хеш пароля в OTP.

Поведение на реальной БД — tests/integration/test_auth_passwordless_and_disabled.py.
"""
from unittest.mock import patch

import pytest

from app.auth import service, storage
from app.auth.service import AuthError

_ACTIVE_STUDENT = {
    "id": "5", "email": "u@e.com", "name": "U", "hashed_password": "h",
    "roles": ["student"], "role": "student", "is_active": True,
}


def _user(**overrides) -> dict:
    return {**_ACTIVE_STUDENT, **overrides}


@pytest.fixture
def last_login_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(storage, "update_last_login", calls.append)
    return calls


# ── ensure_user_can_start_session ─────────────────────────────────────────────

def test_active_user_with_role_may_start_session():
    service.ensure_user_can_start_session(_user())  # не бросает


def test_missing_user_is_invalid_credentials():
    with pytest.raises(AuthError) as ei:
        service.ensure_user_can_start_session(None)
    assert (ei.value.status_code, ei.value.audit_code) == (401, "invalid_credentials")


def test_disabled_user_is_account_disabled():
    with pytest.raises(AuthError) as ei:
        service.ensure_user_can_start_session(_user(is_active=False))
    assert (ei.value.status_code, ei.value.audit_code) == (403, "account_disabled")


@pytest.mark.parametrize("value", [None, "missing"])
def test_null_or_absent_is_active_is_not_disabled(value):
    user = _user()
    if value == "missing":
        user.pop("is_active")
    else:
        user["is_active"] = value
    service.ensure_user_can_start_session(user)  # legacy NULL ≠ заблокирован


def test_disabled_and_no_roles_reports_account_disabled_first():
    with pytest.raises(AuthError) as ei:
        service.ensure_user_can_start_session(
            _user(is_active=False, roles=[], role=None)
        )
    assert ei.value.audit_code == "account_disabled"


def test_disabled_message_is_generic_and_same_as_no_active_roles():
    with pytest.raises(AuthError) as disabled:
        service.ensure_user_can_start_session(_user(is_active=False))
    with pytest.raises(AuthError) as no_roles:
        service.ensure_user_can_start_session(_user(roles=[], role=None))
    # Наружу причина не различается — только audit-код.
    assert disabled.value.message == no_roles.value.message
    assert "заблок" not in disabled.value.message.lower()


# ── authenticate_user: is_active ──────────────────────────────────────────────

def test_login_disabled_user_with_correct_password_rejected(monkeypatch, last_login_calls):
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: _user(is_active=False))
    monkeypatch.setattr(service, "_verify", lambda p, h: True)
    with pytest.raises(AuthError) as ei:
        service.authenticate_user("u@e.com", "pw")
    assert (ei.value.status_code, ei.value.audit_code) == (403, "account_disabled")
    assert last_login_calls == []


def test_login_disabled_user_with_wrong_password_reveals_nothing(monkeypatch, last_login_calls):
    """Без верного пароля статус блокировки не раскрывается."""
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: _user(is_active=False))
    monkeypatch.setattr(service, "_verify", lambda p, h: False)
    with pytest.raises(AuthError) as ei:
        service.authenticate_user("u@e.com", "pw")
    assert (ei.value.status_code, ei.value.audit_code) == (401, "invalid_credentials")
    assert last_login_calls == []


# ── authenticate_user: password_hash=None ─────────────────────────────────────

def test_login_without_password_hash_is_plain_401(monkeypatch, last_login_calls):
    """Даже если bcrypt «совпал» с dummy-хешем, без пароля входа нет."""
    seen = []
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: _user(hashed_password=None))
    monkeypatch.setattr(service, "_verify", lambda p, h: seen.append(h) or True)
    with pytest.raises(AuthError) as ei:
        service.authenticate_user("u@e.com", "pw")
    assert (ei.value.status_code, ei.value.audit_code) == (401, "invalid_credentials")
    assert ei.value.message == "Неверный email или пароль"
    assert last_login_calls == []
    # bcrypt выполнен с реальным dummy-хешем, а не с None.
    assert len(seen) == 1 and isinstance(seen[0], str) and seen[0].startswith("$2")


def test_login_without_password_hash_uses_real_bcrypt_without_exception(monkeypatch):
    """Без моков _verify: никакого AttributeError/ValueError от bcrypt."""
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: _user(hashed_password=None))
    with pytest.raises(AuthError) as ei:
        service.authenticate_user("u@e.com", "any-password")
    assert ei.value.status_code == 401


def test_unknown_email_still_runs_bcrypt(monkeypatch):
    """Выравнивание времени: нет аккаунта → bcrypt всё равно вызывается."""
    seen = []
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: None)
    monkeypatch.setattr(service, "_verify", lambda p, h: seen.append(h) or False)
    with pytest.raises(AuthError) as ei:
        service.authenticate_user("nobody@e.com", "pw")
    assert ei.value.audit_code == "invalid_credentials"
    assert len(seen) == 1


def test_wrong_password_and_no_password_give_identical_error(monkeypatch):
    monkeypatch.setattr(service, "_verify", lambda p, h: False)
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: _user())
    with pytest.raises(AuthError) as wrong:
        service.authenticate_user("u@e.com", "pw")
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: _user(hashed_password=None))
    with pytest.raises(AuthError) as none:
        service.authenticate_user("u@e.com", "pw")
    assert (wrong.value.status_code, wrong.value.message, wrong.value.audit_code) == (
        none.value.status_code, none.value.message, none.value.audit_code
    )


def test_normal_user_login_still_succeeds(monkeypatch, last_login_calls):
    monkeypatch.setattr(storage, "find_user_by_email", lambda e: _user())
    monkeypatch.setattr(service, "_verify", lambda p, h: True)
    assert service.authenticate_user("u@e.com", "pw")["id"] == "5"
    assert last_login_calls == ["5"]


# ── change_password без пароля ────────────────────────────────────────────────

def test_change_password_without_password_is_409_not_500():
    with patch.object(
        storage, "change_password_atomic",
        side_effect=storage.PasswordNotSetError("x"),
    ), patch("app.chat.system_publisher.publish_system_message") as publish:
        with pytest.raises(AuthError) as ei:
            service.change_password("5", "whatever", "NewPassword1!", "NewPassword1!")
    assert ei.value.status_code == 409
    assert "восстановлением" in ei.value.message
    # Провайдер/способ регистрации не называется.
    for word in ("Яндекс", "VK", "ВКонтакте", "social"):
        assert word not in ei.value.message
    publish.assert_not_called()


# ── password_reset_init не копирует хеш ───────────────────────────────────────

@pytest.mark.parametrize("hashed", ["$2b$12$existinghash", None])
def test_reset_init_never_copies_password_hash_into_otp(monkeypatch, hashed):
    captured = {}
    monkeypatch.setattr(
        storage, "find_user_by_email", lambda e: _user(hashed_password=hashed)
    )

    def _fake_otp(email, name, password_hash):
        captured["password_hash"] = password_hash
        return "123456"

    with patch("app.auth.otp_service.create_or_update_otp", side_effect=_fake_otp), \
         patch("app.services.email_service.send_password_reset_otp"):
        service.password_reset_init("u@e.com")
    assert captured == {"password_hash": None}
