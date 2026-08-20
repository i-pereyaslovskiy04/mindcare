"""
Stage 4B-1 — integration: auth-события через record_event пишут корректные auth_log
строки. Запускается ТОЛЬКО через Stage 1 isolated runner (integration conftest
fail-fast'ит без ENV=test + TEST_DATABASE_URL на mindcare_test_<random>). dev/prod
запрещены. Синтетические уникальные данные (integ_ / donnu.ru).
"""
import uuid as _uuid
from datetime import datetime, timedelta

import bcrypt

from app.auth import storage as auth_storage
from app.core.normalization import normalize_email
from app.db.session import SessionLocal
from app.db.models import AllowedEmailDomain, AuthLog, OtpVerification, User, UserSession
from tests.integration.conftest import ALLOWED_TEST_DOMAIN, remove_all_user_roles

PASSWORD = "SecurePass42!"


def _expire_otp(email):
    """Помечает OTP-запись просроченной (сравнение в storage — naive UTC)."""
    with SessionLocal() as db:
        rec = (
            db.query(OtpVerification)
            .filter(OtpVerification.email == normalize_email(email))
            .first()
        )
        assert rec is not None
        rec.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()


def _soft_delete_user(email):
    with SessionLocal() as db:
        u = (
            db.query(User)
            .filter(User.email == normalize_email(email))
            .first()
        )
        assert u is not None
        u.deleted_at = datetime.utcnow()
        db.commit()


def _auth_rows_by_email(email, event=None):
    with SessionLocal() as db:
        q = db.query(AuthLog).filter(AuthLog.user_email == normalize_email(email))
        if event:
            q = q.filter(AuthLog.event == event)
        rows = q.all()
        for r in rows:
            db.expunge(r)
        return rows


def _auth_rows_by_user(user_id, event=None):
    with SessionLocal() as db:
        q = db.query(AuthLog).filter(AuthLog.user_id == user_id)
        if event:
            q = q.filter(AuthLog.event == event)
        rows = q.all()
        for r in rows:
            db.expunge(r)
        return rows


def _register(client, capture_emails, email):
    r = client.post("/api/auth/register/init",
                    json={"name": "Integ User", "email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    code = capture_emails[email][-1]
    r = client.post("/api/auth/register/confirm", json={"email": email, "code": code})
    return r, code


# ── registration ─────────────────────────────────────────────────────────────

def test_registration_succeeded_row(client, capture_emails, test_email):
    r, _ = _register(client, capture_emails, test_email)
    assert r.status_code == 201, r.text
    rows = _auth_rows_by_email(test_email, "registration_succeeded")
    assert len(rows) == 1
    assert rows[0].success is True and rows[0].failure_reason is None
    # старое имя события не создаётся
    assert _auth_rows_by_email(test_email, "register") == []


def test_registration_failed_otp_invalid(client, capture_emails, test_email):
    client.post("/api/auth/register/init",
                json={"name": "Integ User", "email": test_email, "password": PASSWORD})
    r = client.post("/api/auth/register/confirm",
                    json={"email": test_email, "code": "000000"})
    assert r.status_code == 400
    rows = _auth_rows_by_email(test_email, "registration_failed")
    assert len(rows) >= 1
    assert rows[-1].success is False
    assert rows[-1].failure_reason == "otp_invalid"        # стабильный код, не текст


def test_registration_failed_otp_expired(client, capture_emails, test_email):
    client.post("/api/auth/register/init",
                json={"name": "Integ User", "email": test_email, "password": PASSWORD})
    code = capture_emails[test_email][-1]
    _expire_otp(test_email)                                # просрочка до confirm
    r = client.post("/api/auth/register/confirm",
                    json={"email": test_email, "code": code})
    assert r.status_code == 400
    rows = _auth_rows_by_email(test_email, "registration_failed")
    assert rows[-1].success is False
    assert rows[-1].failure_reason == "otp_expired"


def test_registration_failed_domain_not_allowed(
    client, capture_emails, test_email, reset_email_domains
):
    # init проходит на активном домене (donnu.ru); домен деактивируется до confirm,
    # authoritative проверка внутри транзакции даёт domain_not_allowed (422).
    client.post("/api/auth/register/init",
                json={"name": "Integ User", "email": test_email, "password": PASSWORD})
    code = capture_emails[test_email][-1]
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).filter(
            AllowedEmailDomain.domain == ALLOWED_TEST_DOMAIN
        ).update({"is_active": False}, synchronize_session=False)
        db.commit()
    r = client.post("/api/auth/register/confirm",
                    json={"email": test_email, "code": code})
    assert r.status_code == 422
    rows = _auth_rows_by_email(test_email, "registration_failed")
    assert rows[-1].success is False
    assert rows[-1].failure_reason == "domain_not_allowed"


# ── login / failed_login / logout ────────────────────────────────────────────

def _make_user(email, role="student"):
    pw = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    return auth_storage.save_user(
        {"name": "Integ Login", "email": email, "hashed_password": pw, "role": role})


def test_login_and_logout_rows(client):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    user = _make_user(email)
    uid = int(user["id"])

    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    token = r.json()["session_token"]
    login_rows = _auth_rows_by_email(email, "login")
    assert len(login_rows) == 1 and login_rows[0].success is True
    assert login_rows[0].session_id and token not in login_rows[0].session_id  # hash, не raw

    r = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    logout_rows = _auth_rows_by_user(uid, "logout")
    assert len(logout_rows) == 1
    assert logout_rows[0].user_email is None                # logout не пишет email
    assert logout_rows[0].session_id and token not in logout_rows[0].session_id


def test_failed_login_row(client):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    _make_user(email)
    r = client.post("/api/auth/login", json={"email": email, "password": "WrongPass9"})
    assert r.status_code == 401
    rows = _auth_rows_by_email(email, "failed_login")
    assert len(rows) == 1 and rows[0].success is False
    assert rows[0].failure_reason == "invalid_credentials"


def test_login_role_invariant_creates_no_session(client):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    user = _make_user(email)
    uid = int(user["id"])
    remove_all_user_roles(uid)                              # аккаунт без активных ролей
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    # ADR-018: штатный доменный отказ 403 / no_active_roles, не 500/internal_error
    assert r.status_code == 403, r.text
    # сессия не создана
    with SessionLocal() as db:
        sessions = db.query(UserSession).filter(UserSession.user_id == uid).count()
    assert sessions == 0
    rows = _auth_rows_by_email(email, "failed_login")
    assert any(x.failure_reason == "no_active_roles" for x in rows)
    # аварийный код за штатным отказом не закрепляется
    assert not any(x.failure_reason == "internal_error" for x in rows)


# ── password change / reset ──────────────────────────────────────────────────

def test_password_change_row(client):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    user = _make_user(email)
    uid = int(user["id"])
    login = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    token = login.json()["session_token"]
    r = client.post(
        "/api/auth/change-password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": PASSWORD, "new_password": "NewSecurePass9",
              "new_password_confirm": "NewSecurePass9"},
    )
    assert r.status_code == 200, r.text
    rows = _auth_rows_by_user(uid, "password_change")
    assert len(rows) == 1 and rows[0].success is True and rows[0].user_email is None


def test_password_reset_success_and_failure(client, capture_emails):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    _make_user(email)
    # failure: wrong code
    client.post("/api/auth/password/reset/init", json={"email": email})
    r = client.post("/api/auth/password/reset/confirm",
                    json={"email": email, "code": "000000", "new_password": "NewSecure9"})
    assert r.status_code == 400
    fail = _auth_rows_by_email(email, "password_reset")
    assert any(x.success is False and x.failure_reason == "otp_invalid" for x in fail)
    # success: real code
    client.post("/api/auth/password/reset/init", json={"email": email})
    code = capture_emails[email][-1]
    r = client.post("/api/auth/password/reset/confirm",
                    json={"email": email, "code": code, "new_password": "NewSecure9"})
    assert r.status_code == 200, r.text
    ok = [x for x in _auth_rows_by_email(email, "password_reset") if x.success]
    assert len(ok) >= 1 and ok[-1].failure_reason is None


def test_password_reset_failure_otp_expired(client):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    _make_user(email)
    client.post("/api/auth/password/reset/init", json={"email": email})
    _expire_otp(email)
    r = client.post("/api/auth/password/reset/confirm",
                    json={"email": email, "code": "000000", "new_password": "NewSecure9"})
    assert r.status_code == 400
    rows = _auth_rows_by_email(email, "password_reset")
    assert any(x.success is False and x.failure_reason == "otp_expired" for x in rows)


def test_password_reset_failure_password_policy(client):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    _make_user(email)
    client.post("/api/auth/password/reset/init", json={"email": email})
    # Слишком короткий пароль — политика проверяется ДО OTP (422).
    r = client.post("/api/auth/password/reset/confirm",
                    json={"email": email, "code": "000000", "new_password": "short"})
    assert r.status_code == 422
    rows = _auth_rows_by_email(email, "password_reset")
    assert any(x.success is False and x.failure_reason == "password_policy" for x in rows)


def test_password_reset_failure_user_not_found(client, capture_emails):
    email = f"integ_authaudit_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"
    _make_user(email)
    client.post("/api/auth/password/reset/init", json={"email": email})
    code = capture_emails[email][-1]
    _soft_delete_user(email)                      # OTP валиден, но пользователя нет
    r = client.post("/api/auth/password/reset/confirm",
                    json={"email": email, "code": code, "new_password": "NewSecure9"})
    assert r.status_code == 404
    rows = _auth_rows_by_email(email, "password_reset")
    assert any(x.success is False and x.failure_reason == "user_not_found" for x in rows)
