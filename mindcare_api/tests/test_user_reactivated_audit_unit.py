"""
ADR-028 — no-DB unit-тесты: self-registration больше НЕ реактивирует аккаунт.

app.auth.storage.register_confirm_atomic: если email принадлежит ЛЮБОЙ строке
users (активной, отключённой или исторически soft-deleted), после верного OTP
и ДО любой мутации бросается AccountUnavailableError — без commit (OTP не
потреблён), без консентов/ролей, без события user_reactivated (оно остаётся в
registry только как историческое). Новая регистрация по-прежнему проходит.

Реальная БД не используется: db.query замокан по моделям/колонкам через
side_effect; helpers (_verify_code, domain check, _assign_role, _user_to_dict)
замоканы. Поведение на реальной БД — tests/integration/test_user_lifecycle_api.py.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.auth.service as auth_service
import app.auth.storage as auth_storage
from app.auth.otp_service import _utcnow
from app.db.models import Consent, OtpVerification, User

EMAIL = "restore@donnu.ru"
REQUIRED = ["privacy_policy", "data_processing"]
TARGET_ID = 777


def _session(db):
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


def _rc_db(existing_row):
    """OTP валиден, consent-политики есть; lookup любой строки users по email
    (db.query(User.id)) → existing_row (None — email свободен)."""
    db = MagicMock(name="db")
    otp = SimpleNamespace(
        email=EMAIL, code="hashed", expires_at=_utcnow() + timedelta(hours=1),
        attempts=0, name="Имя Фамилия", password_hash="bcrypt$hash",
    )
    consent = SimpleNamespace(id=1)

    def _query(model):
        q = MagicMock()
        if model is OtpVerification:
            q.filter.return_value.first.return_value = otp
        elif model is Consent:
            q.filter.return_value.order_by.return_value.first.return_value = consent
        elif model is User.id:
            q.filter.return_value.first.return_value = existing_row
        else:  # pragma: no cover — неожиданный запрос обнаружится падением
            raise AssertionError(f"unexpected query: {model!r}")
        return q

    db.query.side_effect = _query
    return db, otp


@pytest.fixture
def calls(monkeypatch):
    seen = []
    monkeypatch.setattr(auth_storage, "record_event", lambda **kw: seen.append(kw))
    monkeypatch.setattr(auth_storage, "_verify_code", lambda code, stored: True)
    monkeypatch.setattr(auth_storage, "_assign_role", lambda db, uid, role: None)
    # ADR-029: намерение приглашения — отдельный шаг UoW, здесь не проверяется
    # (mock-сессия не выдаёт user.id).
    monkeypatch.setattr(auth_storage, "enqueue_registration_invite_in_tx",
                        lambda db, uid: None)
    monkeypatch.setattr(auth_storage, "_user_to_dict",
                        lambda u, db: {"id": u.id, "email": EMAIL})
    monkeypatch.setattr(
        "app.email_domains.storage.assert_email_domain_allowed_in_tx",
        lambda db, email: None,
    )
    return seen


def test_existing_email_any_state_rejected_before_mutation(calls):
    """Отключённый, soft-deleted или активный — один и тот же отказ."""
    db, otp = _rc_db(existing_row=SimpleNamespace(id=TARGET_ID))
    with patch.object(auth_storage, "SessionLocal", _session(db)):
        with pytest.raises(auth_storage.AccountUnavailableError):
            auth_storage.register_confirm_atomic(
                email=EMAIL, code="123456", required_consent_types=REQUIRED,
                ip="203.0.113.7", user_agent="pytest-ua",
            )
    db.commit.assert_not_called()      # OTP не потреблён, ничего не зафиксировано
    db.delete.assert_not_called()
    db.add.assert_not_called()         # ни User, ни ConsentRecord
    assert otp.attempts == 0           # попытки не потрачены
    assert calls == []                 # user_reactivated не пишется никогда


def test_new_registration_still_succeeds_without_user_reactivated(calls):
    db, _otp = _rc_db(existing_row=None)
    with patch.object(auth_storage, "SessionLocal", _session(db)):
        auth_storage.register_confirm_atomic(
            email=EMAIL, code="123456", required_consent_types=REQUIRED,
            ip=None, user_agent=None,
        )
    db.commit.assert_called_once()
    assert [c for c in calls if c["event"] == "user_reactivated"] == []


def test_service_maps_unavailable_account_to_email_already_exists(monkeypatch):
    def _raise(**kw):
        raise auth_storage.AccountUnavailableError("x")
    monkeypatch.setattr(auth_service.storage, "register_confirm_atomic", _raise)
    with pytest.raises(auth_service.AuthError) as ei:
        auth_service.register_confirm(email=EMAIL, code="123456")
    assert ei.value.status_code == 409
    assert ei.value.audit_code == "email_already_exists"
    # Сообщение совпадает с ответом register_init — состояние аккаунта
    # (отключён/удалён) не раскрывается.
    assert ei.value.message == "Email уже зарегистрирован"


def test_register_init_rejects_any_existing_row_before_otp(monkeypatch):
    monkeypatch.setattr(auth_service.storage, "email_exists_any", lambda e: True)
    monkeypatch.setattr(
        "app.email_domains.service.assert_email_domain_allowed", lambda e: None,
    )

    def _no_otp(*a, **kw):
        raise AssertionError("OTP must not be created for an existing account")
    monkeypatch.setattr("app.auth.otp_service.create_or_update_otp", _no_otp)
    with pytest.raises(auth_service.AuthError) as ei:
        auth_service.register_init("Имя Фамилия", EMAIL, "password123")
    assert (ei.value.status_code, ei.value.message) == (409, "Email уже зарегистрирован")


def test_legacy_reactivation_helpers_removed():
    assert not hasattr(auth_storage, "reactivate_user")
    assert not hasattr(auth_storage, "SelfReactivationNotAllowedError")
