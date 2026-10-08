"""
ADR-028 — детерминированные гонки выдачи сессии на реальном PostgreSQL.

start_session_atomic (password) берёт строку users FOR UPDATE и сверяет
password_hash с проверенным bcrypt'ом; смена/сброс пароля берут ту же строку
FOR UPDATE до смены и отзыва сессий; OAuth complete — identity → user, оба
FOR UPDATE. Проверяется, что:

  * два независимых password-входа одного пользователя сериализуются без
    deadlock, оба токена рабочие;
  * то же для двух OAuth-входов (два ticket);
  * вход, проверивший СТАРЫЙ пароль, после завершившегося reset/change →
    401 invalid_credentials (failed_login), строки сессии нет;
  * вход, завершившийся первым, затем change/reset → его токен отозван,
    вход новым паролем работает.

Пауза — Gate после взятия блокировки (или до неё — для «проверил старый
пароль»); второй участник ждёт блокировку (pg_stat_activity), не sleep.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.auth.routes as auth_routes
import app.auth.service as auth_service
import app.auth.storage as auth_storage
import app.oauth.storage as oauth_storage
from app.auth import otp_service
from app.auth.schemas import LoginRequest
from app.db.models import AuthLog, UserOAuthIdentity, UserSession
from app.db.session import SessionLocal
from app.oauth import service as oauth_service
from tests.integration.conftest import create_test_user
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, deadlock_count, run_in_thread,
    wait_for_lock_waiter,
)
from tests.oauth_fakes import FakeProvider, registered

PASSWORD = "SecurePass42!"
NEW_PASSWORD = "BrandNewPass77!"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _fake_request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})


def _route_login(email, password=PASSWORD):
    out = auth_routes.login(
        body=LoginRequest(email=email, password=password), request=_fake_request(),
    )
    return out["session_token"]


def _service_login(email, password=PASSWORD):
    user = auth_service.authenticate_user(email, password)
    token, _exp, _u = auth_service.start_password_session(user)
    return token


def _sessions(user_id):
    with SessionLocal() as db:
        return db.query(UserSession).filter(UserSession.user_id == user_id).count()


def _failed_login_codes(email):
    with SessionLocal() as db:
        return [
            (r.failure_reason, r.auth_method)
            for r in db.query(AuthLog).filter(
                AuthLog.event == "failed_login", AuthLog.user_email == email,
            ).order_by(AuthLog.id)
        ]


@pytest.fixture
def no_deadlocks():
    before = deadlock_count()
    yield
    assert deadlock_count() == before


# ── вход ∥ вход ──────────────────────────────────────────────────────────────

def test_two_password_logins_of_one_user_serialize(client, test_email,
                                                   monkeypatch, no_deadlocks):
    uid = int(create_test_user(test_email, PASSWORD)["id"])
    gate = Gate()
    monkeypatch.setattr(auth_storage, "create_session_in_tx",
                        gate.wrap(auth_storage.create_session_in_tx))

    first = run_in_thread(lambda: _service_login(test_email))
    gate.wait_reached()                         # первый держит FOR UPDATE
    second = run_in_thread(lambda: _service_login(test_email))
    wait_for_lock_waiter()                      # второй ждёт ту же строку
    gate.release.set()

    r1, r2 = first.join(), second.join()
    assert_no_deadlock_error(r1, r2)
    assert r1[0] == "ok" and r2[0] == "ok", (r1, r2)
    for token in (r1[1], r2[1]):
        assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200
    assert _sessions(uid) == 2


def test_two_oauth_logins_of_one_user_serialize(client, test_email, monkeypatch,
                                                no_deadlocks):
    with registered(FakeProvider("yandex")) as fake:
        uid = int(create_test_user(test_email, PASSWORD)["id"])
        with SessionLocal() as db:
            db.add(UserOAuthIdentity(user_id=uid, provider="yandex",
                                     provider_subject=fake.subject))
            db.commit()

        def _ticket():
            start = oauth_service.start_login("yandex")
            outcome = oauth_service.handle_callback(
                "yandex", {"state": start.state, "code": fake.issue_code(start.state)},
                start.state,
            )
            return outcome.fragment["ticket"]
        t1, t2 = _ticket(), _ticket()

        gate = Gate()
        monkeypatch.setattr(oauth_storage, "create_session_in_tx",
                            gate.wrap(oauth_storage.create_session_in_tx))
        first = run_in_thread(lambda: oauth_service.complete_login(t1))
        gate.wait_reached()                     # identity + user FOR UPDATE
        second = run_in_thread(lambda: oauth_service.complete_login(t2))
        wait_for_lock_waiter()
        gate.release.set()

        r1, r2 = first.join(), second.join()
    assert_no_deadlock_error(r1, r2)
    assert r1[0] == "ok" and r2[0] == "ok", (r1, r2)
    for res in (r1[1], r2[1]):
        assert client.get("/api/auth/me",
                          headers=_auth(res.session_token)).status_code == 200
    assert _sessions(uid) == 2


# ── вход проверил старый пароль ∥ reset/change завершились ───────────────────

def _reset_password(email):
    code = otp_service.create_or_update_otp(email=email, name="X", password_hash=None)
    auth_service.password_reset_confirm(email, code, NEW_PASSWORD)


def _change_password(uid):
    auth_service.change_password(str(uid), PASSWORD, NEW_PASSWORD, NEW_PASSWORD)


@pytest.mark.parametrize("change", ["reset", "change"])
def test_login_with_verified_old_password_after_password_change_is_401(
    client, test_email, monkeypatch, no_deadlocks, change,
):
    uid = int(create_test_user(test_email, PASSWORD)["id"])
    gate = Gate()
    # Пауза ПОСЛЕ bcrypt-проверки, но ДО блокировки/выдачи сессии.
    monkeypatch.setattr(auth_storage, "start_session_atomic",
                        gate.wrap(auth_storage.start_session_atomic))

    login = run_in_thread(lambda: _route_login(test_email))
    gate.wait_reached()
    if change == "reset":
        _reset_password(test_email)
    else:
        _change_password(uid)
    gate.release.set()

    kind, value = login.join()
    assert kind == "error" and isinstance(value, HTTPException), (kind, value)
    assert value.status_code == 401
    assert _sessions(uid) == 0                       # строка сессии не создана
    assert _failed_login_codes(test_email)[-1] == ("invalid_credentials", "password")
    # Новый пароль работает.
    r = client.post("/api/auth/login",
                    json={"email": test_email, "password": NEW_PASSWORD})
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("change", ["reset", "change"])
def test_password_change_revokes_session_of_login_that_finished_first(
    client, test_email, monkeypatch, no_deadlocks, change,
):
    uid = int(create_test_user(test_email, PASSWORD)["id"])
    gate = Gate()
    # Пауза ВНУТРИ транзакции входа, после FOR UPDATE строки users.
    monkeypatch.setattr(auth_storage, "create_session_in_tx",
                        gate.wrap(auth_storage.create_session_in_tx))

    login = run_in_thread(lambda: _service_login(test_email))
    gate.wait_reached()
    changer = run_in_thread(
        (lambda: _reset_password(test_email)) if change == "reset"
        else (lambda: _change_password(uid))
    )
    wait_for_lock_waiter()                           # смена ждёт строку users
    gate.release.set()

    r_login, r_change = login.join(), changer.join()
    assert_no_deadlock_error(r_login, r_change)
    assert r_login[0] == "ok" and r_change[0] == "ok", (r_login, r_change)
    assert client.get("/api/auth/me",
                      headers=_auth(r_login[1])).status_code == 401
    r = client.post("/api/auth/login",
                    json={"email": test_email, "password": NEW_PASSWORD})
    assert r.status_code == 200, r.text
