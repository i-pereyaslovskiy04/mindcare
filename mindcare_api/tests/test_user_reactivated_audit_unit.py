"""
Stage 5A-1 — no-DB unit-тесты события user_reactivated в
app.auth.storage.register_confirm_atomic.

Проверяет, что запись пишется ТОЛЬКО в ветке восстановления soft-deleted User
(actor = сам восстановленный student, target = этот же аккаунт, metadata пуст,
без ПДн), а новая регистрация его не пишет. Реальная БД не используется:
db.query замокан по моделям через side_effect; helpers (_verify_code, domain
check, _assign_role, _user_to_dict) замоканы.
"""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.auth.storage as auth_storage
from app.audit.contracts import AuditStorageError
from app.auth.otp_service import _utcnow
from app.db.models import OtpVerification, Consent, User

EMAIL = "restore@donnu.ru"
REQUIRED = ["privacy_policy", "data_processing"]
TARGET_ID = 777


def _session(db):
    m = MagicMock()
    m.return_value.__enter__ = MagicMock(return_value=db)
    m.return_value.__exit__ = MagicMock(return_value=False)
    return m


def _rc_db(existing_user):
    """MagicMock db: OTP валиден, consent-политики есть, User-lookup →
    existing_user (soft-deleted для реактивации, None для новой регистрации)."""
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
        elif model is User:
            q.filter.return_value.first.return_value = existing_user
        return q

    db.query.side_effect = _query
    return db, otp


def _patches(monkeypatch, calls, active_roles=("student",)):
    monkeypatch.setattr(auth_storage, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(auth_storage, "_verify_code", lambda code, stored: True)
    monkeypatch.setattr(auth_storage, "_assign_role", lambda db, uid, role: None)
    monkeypatch.setattr(auth_storage, "_user_to_dict",
                        lambda u, db: {"id": u.id, "email": EMAIL})
    monkeypatch.setattr(
        "app.email_domains.storage.assert_email_domain_allowed_in_tx",
        lambda db, email: None,
    )
    # Stage 5A-1 security: реактивация проверяет реальные активные роли.
    monkeypatch.setattr(
        auth_storage, "get_active_role_names",
        lambda db, uid: list(active_roles),
    )


def test_reactivation_writes_exactly_one_user_reactivated(monkeypatch):
    calls = []
    _patches(monkeypatch, calls)
    soft_deleted = SimpleNamespace(
        id=TARGET_ID, email=EMAIL, deleted_at=object(), is_active=False,
        full_name="", password_hash="",
    )
    db, _otp = _rc_db(soft_deleted)

    with patch.object(auth_storage, "SessionLocal", _session(db)):
        auth_storage.register_confirm_atomic(
            email=EMAIL, code="123456", required_consent_types=REQUIRED,
            ip="203.0.113.7", user_agent="pytest-ua",
        )

    reactivated = [c for c in calls if c["event"] == "user_reactivated"]
    assert len(reactivated) == 1
    kw = reactivated[0]
    # actor == target == восстановленный аккаунт (по id).
    assert kw["actor"].kind == "user"
    assert kw["actor"].user_id == TARGET_ID
    assert kw["actor"].role == "student"
    assert kw["target"].entity_type == "user"
    assert kw["target"].entity_id == TARGET_ID
    assert kw["metadata"] == {}
    assert kw.get("description") is None
    assert kw["db"] is db
    # ПДн не попадают в audit payload.
    blob = repr(kw)
    for pii in (EMAIL, "Имя Фамилия", "bcrypt$hash", "123456",
                "privacy_policy", "data_processing"):
        assert pii not in blob


def test_new_registration_does_not_write_user_reactivated(monkeypatch):
    calls = []
    _patches(monkeypatch, calls)
    db, _otp = _rc_db(existing_user=None)   # нет soft-deleted → новая регистрация

    # User НЕ патчим: иначе db.query(User) получит пропатченный класс и `model is
    # User` в side_effect не сработает. Реальный User() конструируется без БД.
    with patch.object(auth_storage, "SessionLocal", _session(db)):
        auth_storage.register_confirm_atomic(
            email=EMAIL, code="123456", required_consent_types=REQUIRED,
            ip=None, user_agent=None,
        )

    assert [c for c in calls if c["event"] == "user_reactivated"] == []


# ── Stage 5A-1 security: self-reactivation разрешена ТОЛЬКО для чистого student ──

@pytest.mark.parametrize("roles", [
    [],                          # без активных ролей
    ["admin"],                   # staff-only
    ["psychologist"],
    ["supervisor"],
    ["student", "psychologist"],  # student + staff
    ["student", "admin"],
])
def test_non_pure_student_soft_deleted_is_not_reactivated(monkeypatch, roles):
    calls = []
    _patches(monkeypatch, calls, active_roles=roles)
    soft = SimpleNamespace(
        id=TARGET_ID, email=EMAIL, deleted_at=object(), is_active=False,
        full_name="OLD NAME", password_hash="OLD$HASH",
    )
    db, _otp = _rc_db(soft)

    with patch.object(auth_storage, "SessionLocal", _session(db)):
        with pytest.raises(auth_storage.SelfReactivationNotAllowedError) as ei:
            auth_storage.register_confirm_atomic(
                email=EMAIL, code="123456", required_consent_types=REQUIRED,
                ip="127.0.0.1", user_agent="ua",
            )

    # typed internal precommit error → service мапит через существующий
    # except RegistrationDataError в generic internal_error.
    assert isinstance(ei.value, auth_storage.RegistrationDataError)
    # User НЕ реактивирован и НЕ мутирован.
    assert soft.deleted_at is not None
    assert soft.is_active is False
    assert soft.full_name == "OLD NAME"
    assert soft.password_hash == "OLD$HASH"
    # Ни audit, ни flush, ни consume OTP, ни commit.
    assert calls == []
    db.flush.assert_not_called()
    db.delete.assert_not_called()
    db.commit.assert_not_called()
    # Диагностика не раскрывает email/id/UUID/названия ролей.
    msg = str(ei.value)
    for leak in (EMAIL, str(TARGET_ID),
                 "admin", "supervisor", "psychologist", "student"):
        assert leak not in msg


def test_valid_student_reactivation_audit_failure_propagates_no_commit(monkeypatch):
    # Валидный student-аккаунт; record_event падает AuditStorageError.
    # Реальный SessionLocal-контекст откатил бы уже применённые ORM-изменения
    # (deleted_at/is_active/ФИО/hash) при выходе с исключением; здесь проверяем,
    # что исключение всплывает, commit не достигнут и OTP не потреблён.
    calls = []
    _patches(monkeypatch, calls, active_roles=["student"])

    def _boom(**kw):
        raise AuditStorageError("audit storage failure for user_reactivated")
    monkeypatch.setattr(auth_storage, "record_event", _boom)

    soft = SimpleNamespace(
        id=TARGET_ID, email=EMAIL, deleted_at=object(), is_active=False,
        full_name="OLD NAME", password_hash="OLD$HASH",
    )
    db, _otp = _rc_db(soft)

    with patch.object(auth_storage, "SessionLocal", _session(db)):
        with pytest.raises(AuditStorageError):
            auth_storage.register_confirm_atomic(
                email=EMAIL, code="123456", required_consent_types=REQUIRED,
                ip=None, user_agent=None,
            )
    db.commit.assert_not_called()
    db.delete.assert_not_called()   # OTP не потреблён
