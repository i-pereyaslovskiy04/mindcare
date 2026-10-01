"""
Stage Social Auth 2A — auth-инварианты на реальной БД (route → service → storage).

  A. is_active=false: верный пароль → 403 account_disabled, сессия не создаётся,
     last_login не меняется, failed_login в auth_log; после активации вход работает.
  B. password_hash=NULL (social-only): обычный вход → тот же 401, что неверный пароль.
  C. reset по OTP устанавливает первый пароль; reset-OTP не хранит копию хеша;
     неверный/истёкший код ничего не меняет; сессии отзываются.
  D. change-password без пароля → 409, без 500 и без изменений.
  E. has_password в /me и /profile; хеш наружу не попадает.

Email — integ_* (cleanup_test_records удаляет пользователей и их сессии/OTP).
"""
from datetime import datetime, timedelta, timezone

from app.auth import storage as auth_storage
from app.db.models import AuthLog, OtpVerification, User, UserSession
from app.db.session import SessionLocal

from tests.integration.conftest import add_user_role, create_test_user

PASSWORD = "SecurePass42!"
NEW_PASSWORD = "BrandNewPass42!"
_GENERIC_403 = "Доступ к системе не активирован. Обратитесь к администратору."


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_passwordless_student(email: str) -> int:
    """Social-only аккаунт: password_hash IS NULL, роль student."""
    with SessionLocal() as db:
        user = User(full_name="Integ Social Only", email=email, password_hash=None)
        db.add(user)
        db.commit()
        user_id = user.id
    add_user_role(user_id, "student")
    return user_id


def _user_row(email: str) -> dict:
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == email).one()
        return {
            "id": u.id, "password_hash": u.password_hash,
            "last_login": u.last_login, "is_active": u.is_active,
        }


def _set_active(email: str, value: bool) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.email == email).update({"is_active": value})
        db.commit()


def _session_count(user_id: int) -> int:
    with SessionLocal() as db:
        return db.query(UserSession).filter(UserSession.user_id == user_id).count()


def _failed_login_reasons(email: str) -> list:
    with SessionLocal() as db:
        rows = (
            db.query(AuthLog)
            .filter(AuthLog.user_email == email, AuthLog.event == "failed_login")
            .order_by(AuthLog.id)
            .all()
        )
        return [r.failure_reason for r in rows]


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── A. is_active=false ───────────────────────────────────────────────────────

def test_disabled_user_with_correct_password_gets_no_session(client, test_email):
    user = create_test_user(test_email, PASSWORD)
    _set_active(test_email, False)
    before = _user_row(test_email)

    r = _login(client, test_email)

    assert r.status_code == 403
    assert r.json()["detail"] == _GENERIC_403
    assert _session_count(int(user["id"])) == 0
    assert _user_row(test_email)["last_login"] == before["last_login"]
    assert _failed_login_reasons(test_email)[-1] == "account_disabled"


def test_disabled_user_with_wrong_password_gets_plain_401(client, test_email):
    create_test_user(test_email, PASSWORD)
    _set_active(test_email, False)

    r = _login(client, test_email, "WrongPass42!")

    assert r.status_code == 401
    assert r.json()["detail"] == "Неверный email или пароль"
    assert _failed_login_reasons(test_email)[-1] == "invalid_credentials"


def test_reactivated_user_can_login_again(client, test_email):
    user = create_test_user(test_email, PASSWORD)
    _set_active(test_email, False)
    assert _login(client, test_email).status_code == 403

    _set_active(test_email, True)
    r = _login(client, test_email)

    assert r.status_code == 200, r.text
    assert _session_count(int(user["id"])) == 1
    assert _user_row(test_email)["last_login"] is not None


# ── B. password_hash=NULL ────────────────────────────────────────────────────

def test_passwordless_user_password_login_is_same_401(client, test_email, foreign_test_email):
    user_id = _make_passwordless_student(test_email)
    create_test_user(foreign_test_email, PASSWORD)

    no_password = _login(client, test_email, "AnyPassword42!")
    wrong_password = _login(client, foreign_test_email, "WrongPass42!")

    assert no_password.status_code == wrong_password.status_code == 401
    assert no_password.json() == wrong_password.json()
    assert _session_count(user_id) == 0
    assert _failed_login_reasons(test_email)[-1] == "invalid_credentials"


def test_regular_password_user_still_logs_in(client, test_email):
    create_test_user(test_email, PASSWORD)
    r = _login(client, test_email)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "student"


# ── C. reset устанавливает первый пароль ─────────────────────────────────────

def _reset_init(client, email, capture_emails) -> str:
    r = client.post("/api/auth/password/reset/init", json={"email": email})
    assert r.status_code == 200, r.text
    return capture_emails[email][-1]


def _otp_row(email: str):
    with SessionLocal() as db:
        return db.query(OtpVerification).filter(OtpVerification.email == email).one()


def test_passwordless_user_sets_first_password_via_reset(client, test_email, capture_emails):
    user_id = _make_passwordless_student(test_email)
    token, _ = auth_storage.create_session(str(user_id))

    code = _reset_init(client, test_email, capture_emails)
    assert _otp_row(test_email).password_hash is None

    r = client.post("/api/auth/password/reset/confirm", json={
        "email": test_email, "code": code, "new_password": NEW_PASSWORD,
    })

    assert r.status_code == 200, r.text
    assert _user_row(test_email)["password_hash"] is not None
    # Сессии отозваны, как в обычном reset.
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 401
    # Теперь обычный вход работает.
    assert _login(client, test_email, NEW_PASSWORD).status_code == 200


def test_reset_otp_does_not_copy_existing_password_hash(client, test_email, capture_emails):
    create_test_user(test_email, PASSWORD)
    _reset_init(client, test_email, capture_emails)
    assert _otp_row(test_email).password_hash is None


def test_invalid_reset_code_leaves_passwordless_user_unchanged(client, test_email, capture_emails):
    _make_passwordless_student(test_email)
    code = _reset_init(client, test_email, capture_emails)
    wrong = "000000" if code != "000000" else "111111"

    r = client.post("/api/auth/password/reset/confirm", json={
        "email": test_email, "code": wrong, "new_password": NEW_PASSWORD,
    })

    assert r.status_code == 400
    assert _user_row(test_email)["password_hash"] is None


def test_expired_reset_code_leaves_passwordless_user_unchanged(client, test_email, capture_emails):
    _make_passwordless_student(test_email)
    code = _reset_init(client, test_email, capture_emails)
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == test_email).update({
            "expires_at": datetime.now(timezone.utc).replace(tzinfo=None)
            - timedelta(minutes=1),
        })
        db.commit()

    r = client.post("/api/auth/password/reset/confirm", json={
        "email": test_email, "code": code, "new_password": NEW_PASSWORD,
    })

    assert r.status_code == 400
    assert _user_row(test_email)["password_hash"] is None


def test_reset_otp_is_not_accepted_as_registration(client, test_email, capture_emails):
    """Reset-OTP (без хеша) не может создать/реактивировать аккаунт без пароля."""
    user_id = _make_passwordless_student(test_email)
    code = _reset_init(client, test_email, capture_emails)

    r = client.post("/api/auth/register/confirm", json={"email": test_email, "code": code})

    assert r.status_code == 400
    assert _user_row(test_email)["id"] == user_id
    assert _otp_row(test_email) is not None   # OTP не потреблён


# ── D. change-password без пароля ────────────────────────────────────────────

def test_change_password_without_password_is_409(client, test_email):
    user_id = _make_passwordless_student(test_email)
    token, _ = auth_storage.create_session(str(user_id))

    r = client.post("/api/auth/change-password", headers=_bearer(token), json={
        "current_password": "Whatever42!",
        "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD,
    })

    assert r.status_code == 409
    assert "восстановлением" in r.json()["detail"]
    assert _user_row(test_email)["password_hash"] is None
    # Ничего не отозвано: сессия жива.
    assert client.get("/api/auth/me", headers=_bearer(token)).status_code == 200


def test_change_password_for_regular_user_still_works(client, test_email):
    create_test_user(test_email, PASSWORD)
    token = _login(client, test_email).json()["session_token"]

    r = client.post("/api/auth/change-password", headers=_bearer(token), json={
        "current_password": PASSWORD,
        "new_password": NEW_PASSWORD, "new_password_confirm": NEW_PASSWORD,
    })

    assert r.status_code == 200, r.text
    assert _login(client, test_email, NEW_PASSWORD).status_code == 200


# ── E. has_password ──────────────────────────────────────────────────────────

def _assert_no_hash_leak(body: dict, raw_hash) -> None:
    keys = {k.lower() for k in body}
    assert not any("hash" in k for k in keys)
    assert "password_hash" not in keys and "hashed_password" not in keys
    if raw_hash:
        assert raw_hash not in str(body)


def test_has_password_true_for_regular_account(client, test_email):
    create_test_user(test_email, PASSWORD)
    token = _login(client, test_email).json()["session_token"]
    raw_hash = _user_row(test_email)["password_hash"]

    me = client.get("/api/auth/me", headers=_bearer(token)).json()
    profile = client.get("/api/auth/profile", headers=_bearer(token)).json()

    assert me["has_password"] is True and profile["has_password"] is True
    _assert_no_hash_leak(me, raw_hash)
    _assert_no_hash_leak(profile, raw_hash)


def test_has_password_false_for_passwordless_account(client, test_email):
    user_id = _make_passwordless_student(test_email)
    token, _ = auth_storage.create_session(str(user_id))

    me = client.get("/api/auth/me", headers=_bearer(token)).json()
    profile = client.get("/api/auth/profile", headers=_bearer(token)).json()
    patched = client.patch(
        "/api/auth/profile", headers=_bearer(token), json={"phone": "+70000000000"},
    ).json()

    assert me["has_password"] is False
    assert profile["has_password"] is False
    assert patched["has_password"] is False
    _assert_no_hash_leak(me, None)
    _assert_no_hash_leak(profile, None)
