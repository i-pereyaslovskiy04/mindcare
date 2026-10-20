"""
Stage Social Auth 3A — auth_log.auth_method для входа по паролю (реальная БД).

/auth/login пишет auth_method='password' и в успехе, и во всех отказах
(неверный пароль, заблокирован, нет активных ролей); logout и смена пароля —
NULL (это не аутентификация). Внешние ответы /auth/login не меняются.
"""
from app.db.models import AuthLog, User
from app.db.session import SessionLocal
from tests.integration.conftest import create_test_user, remove_all_user_roles

PASSWORD = "SecurePass42!"


def _mark() -> int:
    with SessionLocal() as db:
        return db.query(AuthLog.id).order_by(AuthLog.id.desc()).limit(1).scalar() or 0


def _rows(mark):
    with SessionLocal() as db:
        return [
            (r.event, r.failure_reason, r.auth_method)
            for r in db.query(AuthLog).filter(AuthLog.id > mark).order_by(AuthLog.id)
        ]


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_password_login_success_logout_and_change(client, test_email):
    create_test_user(test_email)
    mark = _mark()
    r = _login(client, test_email)
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    assert client.post("/api/auth/change-password", headers=headers, json={
        "current_password": PASSWORD, "new_password": "NewSecure43!",
        "new_password_confirm": "NewSecure43!",
    }).status_code == 200
    r = _login(client, test_email, "NewSecure43!")
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    assert client.post("/api/auth/logout", headers=headers).status_code == 200

    assert _rows(mark) == [
        ("login", None, "password"),
        ("password_change", None, None),
        ("login", None, "password"),
        ("logout", None, None),
    ]


def test_wrong_password_is_password_method(client, test_email):
    create_test_user(test_email)
    mark = _mark()
    assert _login(client, test_email, "WrongPass99!").status_code == 401
    assert _rows(mark) == [("failed_login", "invalid_credentials", "password")]


def test_unknown_email_is_password_method(client, test_email):
    mark = _mark()
    assert _login(client, test_email).status_code == 401
    assert _rows(mark) == [("failed_login", "invalid_credentials", "password")]


def test_disabled_account_is_password_method(client, test_email):
    user_id = int(create_test_user(test_email)["id"])
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update({"is_active": False})
        db.commit()
    mark = _mark()
    assert _login(client, test_email).status_code == 403
    assert _rows(mark) == [("failed_login", "account_disabled", "password")]


def test_no_active_roles_is_password_method(client, test_email):
    user_id = int(create_test_user(test_email)["id"])
    remove_all_user_roles(user_id)
    mark = _mark()
    assert _login(client, test_email).status_code == 403
    assert _rows(mark) == [("failed_login", "no_active_roles", "password")]
