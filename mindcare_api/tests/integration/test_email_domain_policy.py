"""
Integration-тесты применения email-domain allowlist политики на 4 creation-путях
+ OTP-preservation и soft-deleted реактивация. Требуют dev PostgreSQL на head.

Инварианты:
  - запрещённый домен → РОВНО 422 в каждом из 4 endpoints (в т.ч.
    POST /api/admin/users, где раньше общий ValueError → 409);
  - разрешённый домен проходит; mixed-case нормализуется;
  - login/password reset существующего foreign-email пользователя работают;
  - register/confirm при отключённом домене → 422 и OTP НЕ потреблён;
  - реактивация soft-deleted аккаунта при запрещённом домене → 422.
"""

import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AllowedEmailDomain, OtpVerification, User

PASSWORD = "SecurePass42!"
ADMIN_URL = "/api/admin/users/"
SUPERVISOR_URL = "/api/supervisor/students"

_ADMIN_BODY = {
    "full_name": "Сотрудник Тестовый",
    "role": "psychologist",
    "legal_basis_confirmed": True,
    "basis_type": "employment",
    "basis_reference": "Приказ № 7-к",
}


def _hash() -> str:
    return bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()


def _make_user(client, role: str) -> str:
    u = auth_storage.save_user({
        "name": f"Integ {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_pol_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _hash(),
        "role": role,
    })
    r = client.post(
        "/api/auth/login", json={"email": u["email"], "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _code_for(capture_emails: dict, email: str) -> str:
    """
    Код OTP по email, устойчиво к нормализации домена pydantic EmailStr
    (домен приводится к lower, local сохраняется): матчим ключ без учёта регистра.
    """
    target = email.lower()
    for key, codes in capture_emails.items():
        if key.lower() == target and codes:
            return codes[-1]
    raise KeyError(email)


def _add_domain(domain: str, is_active: bool = True) -> None:
    with SessionLocal() as db:
        db.add(AllowedEmailDomain(domain=domain, is_active=is_active))
        db.commit()


def _set_domain_active(domain: str, active: bool) -> None:
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).filter(
            AllowedEmailDomain.domain == domain,
        ).update({"is_active": active}, synchronize_session=False)
        db.commit()


def _otp_exists(email: str) -> bool:
    with SessionLocal() as db:
        return db.query(OtpVerification).filter(
            OtpVerification.email == email.strip().lower(),
        ).first() is not None


def _user_active(email: str):
    with SessionLocal() as db:
        u = db.query(User).filter(
            User.email == email.strip().lower(),
        ).first()
        return None if u is None else (u.deleted_at is None and u.is_active)


# ─── register/init + confirm ──────────────────────────────────────────────────

class TestRegisterPolicy:
    def test_init_forbidden_domain_422(
        self, client, foreign_test_email, reset_email_domains,
    ):
        r = client.post("/api/auth/register/init", json={
            "name": "Test User", "email": foreign_test_email,
            "password": PASSWORD,
        })
        assert r.status_code == 422

    def test_full_flow_allowed_domain(
        self, client, test_email, capture_emails, reset_email_domains,
    ):
        r = client.post("/api/auth/register/init", json={
            "name": "Test User", "email": test_email, "password": PASSWORD,
        })
        assert r.status_code == 200, r.text
        code = _code_for(capture_emails, test_email)
        r = client.post("/api/auth/register/confirm", json={
            "email": test_email, "code": code,
        })
        assert r.status_code == 201, r.text
        assert _user_active(test_email) is True

    def test_mixed_case_allowed_domain(
        self, client, capture_emails, reset_email_domains,
    ):
        # local mixed-case + domain uppercase → нормализуется, домен разрешён.
        email = f"Integ_Mixed_{_uuid.uuid4().hex[:8]}@DoNNu.RU"
        r = client.post("/api/auth/register/init", json={
            "name": "Test User", "email": email, "password": PASSWORD,
        })
        assert r.status_code == 200, r.text
        code = _code_for(capture_emails, email)
        r = client.post("/api/auth/register/confirm", json={
            "email": email, "code": code,
        })
        assert r.status_code == 201, r.text


# ─── POST /api/admin/users ────────────────────────────────────────────────────

class TestAdminCreatePolicy:
    def test_forbidden_domain_422_not_409(
        self, client, foreign_test_email, reset_email_domains,
    ):
        token = _make_user(client, "admin")
        body = {**_ADMIN_BODY, "email": foreign_test_email}
        r = client.post(ADMIN_URL, headers=_auth(token), json=body)
        # именно 422 (не 409 duplicate) — EmailDomainNotAllowedError не ValueError
        assert r.status_code == 422, r.text

    def test_allowed_domain_201(
        self, client, test_email, reset_email_domains,
    ):
        token = _make_user(client, "admin")
        body = {**_ADMIN_BODY, "email": test_email}
        r = client.post(ADMIN_URL, headers=_auth(token), json=body)
        assert r.status_code == 201, r.text


# ─── POST /api/supervisor/students ────────────────────────────────────────────

class TestSupervisorCreatePolicy:
    def test_forbidden_domain_422(
        self, client, foreign_test_email, reset_email_domains,
    ):
        token = _make_user(client, "supervisor")
        body = {
            "full_name": "Студент Тестовый",
            "email": foreign_test_email,
            "personal_data_consent": True,
        }
        r = client.post(SUPERVISOR_URL, headers=_auth(token), json=body)
        assert r.status_code == 422, r.text

    def test_allowed_domain_201(
        self, client, test_email, reset_email_domains,
    ):
        token = _make_user(client, "supervisor")
        body = {
            "full_name": "Студент Тестовый",
            "email": test_email,
            "personal_data_consent": True,
        }
        r = client.post(SUPERVISOR_URL, headers=_auth(token), json=body)
        assert r.status_code == 201, r.text


# ─── Существующий foreign-email: login и reset работают ───────────────────────

class TestExistingForeignEmailUnaffected:
    def test_login_and_reset_work(
        self, client, foreign_test_email, capture_emails, reset_email_domains,
    ):
        # Пользователь на foreign-домене заводится напрямую (save_user не проходит
        # domain-политику) — имитирует уже существующий аккаунт.
        auth_storage.save_user({
            "name": "Foreign User", "email": foreign_test_email,
            "hashed_password": _hash(), "role": "student",
        })
        # login работает
        r = client.post("/api/auth/login", json={
            "email": foreign_test_email, "password": PASSWORD,
        })
        assert r.status_code == 200, r.text
        # password reset init работает (не раскрывает существование, всегда 200)
        r = client.post("/api/auth/password/reset/init", json={
            "email": foreign_test_email,
        })
        assert r.status_code == 200, r.text


# ─── OTP preservation при отключении домена между init и confirm ──────────────

class TestOtpPreservation:
    def test_confirm_blocked_after_domain_disabled_otp_preserved(
        self, client, capture_emails, reset_email_domains,
    ):
        temp_domain = f"integ-otp-{_uuid.uuid4().hex[:8]}.ru"
        email = f"integ_otp_{_uuid.uuid4().hex[:8]}@{temp_domain}"

        # 1. временный домен активен
        _add_domain(temp_domain, is_active=True)
        # 2. register/init создаёт OTP
        r = client.post("/api/auth/register/init", json={
            "name": "Test User", "email": email, "password": PASSWORD,
        })
        assert r.status_code == 200, r.text
        code = _code_for(capture_emails, email)
        # 3. домен отключается
        _set_domain_active(temp_domain, False)
        # 4. register/confirm → 422, OTP НЕ потреблён
        r = client.post("/api/auth/register/confirm", json={
            "email": email, "code": code,
        })
        assert r.status_code == 422, r.text
        assert _otp_exists(email) is True
        assert _user_active(email) is None            # пользователь не создан
        # 5. домен реактивируется
        _set_domain_active(temp_domain, True)
        # 6. тот же код успешно подтверждает регистрацию
        r = client.post("/api/auth/register/confirm", json={
            "email": email, "code": code,
        })
        assert r.status_code == 201, r.text
        assert _user_active(email) is True


# ─── Soft-deleted реактивация при запрещённом домене ──────────────────────────

class TestSoftDeletedReactivation:
    def test_reactivation_blocked_when_domain_disabled(
        self, client, capture_emails, reset_email_domains,
    ):
        temp_domain = f"integ-sd-{_uuid.uuid4().hex[:8]}.ru"
        email = f"integ_sd_{_uuid.uuid4().hex[:8]}@{temp_domain}"

        # Предварительно создать и soft-delete пользователя на temp-домене.
        user = auth_storage.save_user({
            "name": "Soft Deleted", "email": email,
            "hashed_password": _hash(), "role": "student",
        })
        with SessionLocal() as db:
            from datetime import datetime, timezone
            db.query(User).filter(User.id == int(user["id"])).update({
                "deleted_at": datetime.now(timezone.utc), "is_active": False,
            }, synchronize_session=False)
            db.commit()

        _add_domain(temp_domain, is_active=True)
        # init (домен активен) → OTP
        r = client.post("/api/auth/register/init", json={
            "name": "Soft Deleted", "email": email, "password": PASSWORD,
        })
        assert r.status_code == 200, r.text
        code = _code_for(capture_emails, email)
        # домен отключается → confirm 422, пользователь остаётся удалённым, OTP цел
        _set_domain_active(temp_domain, False)
        r = client.post("/api/auth/register/confirm", json={
            "email": email, "code": code,
        })
        assert r.status_code == 422, r.text
        assert _user_active(email) is False           # всё ещё soft-deleted
        assert _otp_exists(email) is True
        # реактивируем домен → тот же код реактивирует пользователя
        _set_domain_active(temp_domain, True)
        r = client.post("/api/auth/register/confirm", json={
            "email": email, "code": code,
        })
        assert r.status_code == 201, r.text
        assert _user_active(email) is True
