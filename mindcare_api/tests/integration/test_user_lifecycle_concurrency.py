"""
ADR-028 — детерминированные гонки lifecycle отключения/восстановления на
реальном PostgreSQL.

Инвариант: deactivate/restore/self берут строку users FOR UPDATE; выдача
сессии (password — FOR UPDATE, impersonation — FOR SHARE) и смена membership
(update_user, grant admin) — ту же строку. Поэтому:

  * login ∥ deactivate: вход первым → его сессия отозвана отключением и не
    оживает после restore; отключение первым → вход 403, сессии нет;
  * impersonation ∥ deactivate цели — то же;
  * self-deactivate ∥ выдача admin: проверка «чистого студента» видит
    закоммиченный набор ролей в обоих порядках;
  * PATCH снятия staff-роли ∥ self — self видит закоммиченные роли;
  * deactivate ∥ deactivate — ровно один успех и одна audit-строка;
  * deactivate ∥ restore — согласованный итог, оба события.
"""
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import app.auth.service as auth_service
import app.auth.storage as auth_storage
import app.users.service as users_service
import app.users.storage as users_storage
from app.auth.service import AuthError
from app.db.models import AuditLog, Role, User, UserRole, UserSession
from app.db.session import SessionLocal
from app.users.schemas import AdminUserUpdate
from tests.integration.conftest import (
    add_user_role, create_multi_role_user, create_test_user,
)
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, deadlock_count, run_in_thread,
    wait_for_lock_waiter,
)

PASSWORD = "SecurePass42!"
REASON = "Параллельное отключение"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _student(email):
    uid = int(create_test_user(email, PASSWORD)["id"])
    with SessionLocal() as db:
        return uid, str(db.get(User, uid).uuid)


def _login(email):
    user = auth_service.authenticate_user(email, PASSWORD)
    token, _exp, _u = auth_service.start_password_session(user)
    return token


def _deactivate(uuid, admin_id):
    return users_service.deactivate_user(
        uuid, REASON, actor_id=admin_id, actor_role="admin",
    )


def _restore(uuid, admin_id):
    return users_service.restore_user(uuid, actor_id=admin_id, actor_role="admin")


def _active_sessions(uid):
    with SessionLocal() as db:
        return db.query(UserSession).filter(
            UserSession.user_id == uid, ~UserSession.is_revoked).count()


def _events(event_type, uid):
    with SessionLocal() as db:
        return db.query(AuditLog).filter(
            AuditLog.event_type == event_type, AuditLog.entity_id == uid,
        ).count()


def _user(uid):
    with SessionLocal() as db:
        u = db.get(User, uid)
        db.expunge(u)
        return u


@pytest.fixture
def admin(client):
    _token, admin_id, _ = create_multi_role_user(client, ["admin"])
    return admin_id


@pytest.fixture
def no_deadlocks():
    before = deadlock_count()
    yield
    assert deadlock_count() == before


# ── login ∥ deactivate → restore ─────────────────────────────────────────────

def test_login_first_then_deactivate_revokes_and_restore_does_not_revive(
    client, test_email, admin, monkeypatch, no_deadlocks,
):
    uid, uuid = _student(test_email)
    gate = Gate()
    monkeypatch.setattr(auth_storage, "create_session_in_tx",
                        gate.wrap(auth_storage.create_session_in_tx))

    login = run_in_thread(lambda: _login(test_email))
    gate.wait_reached()                         # вход держит FOR UPDATE users
    deact = run_in_thread(lambda: _deactivate(uuid, admin))
    wait_for_lock_waiter()                      # отключение ждёт вход
    gate.release.set()

    r_login, r_deact = login.join(), deact.join()
    assert_no_deadlock_error(r_login, r_deact)
    assert r_login[0] == "ok" and r_deact[0] == "ok", (r_login, r_deact)
    token = r_login[1]
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401

    _restore(uuid, admin)
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 401
    assert _active_sessions(uid) == 0
    fresh = _login(test_email)
    assert client.get("/api/auth/me", headers=_auth(fresh)).status_code == 200


def test_deactivate_first_then_login_is_refused_without_session(
    client, test_email, admin, monkeypatch, no_deadlocks,
):
    uid, uuid = _student(test_email)
    gate = Gate()
    monkeypatch.setattr(users_storage, "disable_user_in_tx",
                        gate.wrap(users_storage.disable_user_in_tx))

    deact = run_in_thread(lambda: _deactivate(uuid, admin))
    gate.wait_reached()                         # отключение держит FOR UPDATE
    login = run_in_thread(lambda: _login(test_email))
    wait_for_lock_waiter()                      # вход (после bcrypt) ждёт строку
    gate.release.set()

    r_deact, r_login = deact.join(), login.join()
    assert_no_deadlock_error(r_deact, r_login)
    assert r_deact[0] == "ok"
    kind, err = r_login
    assert kind == "error" and isinstance(err, AuthError), r_login
    assert (err.status_code, err.audit_code) == (403, "account_disabled")
    with SessionLocal() as db:
        assert db.query(UserSession).filter(UserSession.user_id == uid).count() == 0

    _restore(uuid, admin)
    assert _active_sessions(uid) == 0


def test_impersonation_vs_deactivate_target(client, test_email, admin,
                                            monkeypatch, no_deadlocks):
    uid, uuid = _student(test_email)
    gate = Gate()
    monkeypatch.setattr(auth_storage, "create_session_in_tx",
                        gate.wrap(auth_storage.create_session_in_tx))

    imp = run_in_thread(
        lambda: users_service.start_impersonation_session(uid, actor_id=admin)
    )
    gate.wait_reached()                         # admin+target FOR SHARE
    deact = run_in_thread(lambda: _deactivate(uuid, admin))
    wait_for_lock_waiter()
    gate.release.set()

    r_imp, r_deact = imp.join(), deact.join()
    assert_no_deadlock_error(r_imp, r_deact)
    assert r_imp[0] == "ok" and r_deact[0] == "ok", (r_imp, r_deact)
    imp_token = r_imp[1][0]
    assert client.get("/api/auth/me", headers=_auth(imp_token)).status_code == 401
    _restore(uuid, admin)
    assert client.get("/api/auth/me", headers=_auth(imp_token)).status_code == 401
    with SessionLocal() as db:
        assert db.get(User, uid).last_login is None   # impersonation last_login не трогает


# ── self-deactivate ∥ смена membership ───────────────────────────────────────

def _self(uid):
    return auth_storage.self_deactivate_atomic(uid)


def test_self_first_then_grant_admin(client, test_email, monkeypatch, no_deadlocks):
    uid, _uuid = _student(test_email)
    gate = Gate()
    monkeypatch.setattr(users_storage, "disable_user_in_tx",
                        gate.wrap(users_storage.disable_user_in_tx))

    def _grant():
        with SessionLocal() as db:
            granted = users_storage.grant_admin_role_to_existing_in_tx(db, uid)
            db.commit()
            return granted

    self_t = run_in_thread(lambda: _self(uid))
    gate.wait_reached()                         # self проверил «чистого» под lock
    grant_t = run_in_thread(_grant)
    wait_for_lock_waiter()                      # выдача admin ждёт строку
    gate.release.set()

    r_self, r_grant = self_t.join(), grant_t.join()
    assert_no_deadlock_error(r_self, r_grant)
    assert r_self[0] == "ok" and r_grant == ("ok", True), (r_self, r_grant)
    u = _user(uid)
    assert u.is_active is False and u.deactivation_source == "self"
    # Выдача admin ждала блокировку (wait_for_lock_waiter) и применилась ПОСЛЕ
    # коммита самоотключения: на момент проверки набор был ровно {student}.
    # (granted_at = now() — время НАЧАЛА транзакции, для порядка непригодно.)
    with SessionLocal() as db:
        admin_role = db.query(Role).filter(Role.name == "admin").one()
        assert db.query(UserRole).filter(
            UserRole.user_id == uid, UserRole.role_id == admin_role.id,
        ).count() == 1
    assert _events("user_self_deactivated", uid) == 1
    assert _active_sessions(uid) == 0


def test_grant_admin_first_then_self_is_refused(client, test_email, no_deadlocks):
    uid, _uuid = _student(test_email)
    granted_locked = threading.Event()
    commit_now = threading.Event()

    def _grant():
        with SessionLocal() as db:
            users_storage.grant_admin_role_to_existing_in_tx(db, uid)  # FOR UPDATE
            granted_locked.set()
            assert commit_now.wait(20)
            db.commit()

    grant_t = run_in_thread(_grant)
    assert granted_locked.wait(20)
    self_t = run_in_thread(lambda: _self(uid))
    wait_for_lock_waiter()                      # self ждёт ту же строку
    commit_now.set()

    r_grant, r_self = grant_t.join(), self_t.join()
    assert_no_deadlock_error(r_grant, r_self)
    assert r_grant[0] == "ok"
    kind, err = r_self
    assert kind == "error" and isinstance(err, auth_storage.SelfDeactivationNotAllowedError)
    assert _user(uid).is_active is True
    assert _events("user_self_deactivated", uid) == 0


def test_patch_removing_staff_role_then_self_sees_committed_roles(
    client, test_email, admin, monkeypatch, no_deadlocks,
):
    uid, uuid = _student(test_email)
    add_user_role(uid, "psychologist")          # psychologist + student
    gate = Gate()
    monkeypatch.setattr(users_storage, "_apply_role_and_scalar_changes",
                        gate.wrap(users_storage._apply_role_and_scalar_changes))

    patch_t = run_in_thread(lambda: users_service.update_user(
        uuid, AdminUserUpdate(roles=[]), actor_id=admin, actor_role="admin",
    ))
    gate.wait_reached()                         # PATCH держит FOR UPDATE
    self_t = run_in_thread(lambda: _self(uid))
    wait_for_lock_waiter()
    gate.release.set()

    r_patch, r_self = patch_t.join(), self_t.join()
    assert_no_deadlock_error(r_patch, r_self)
    assert r_patch[0] == "ok" and r_self[0] == "ok", (r_patch, r_self)
    assert _user(uid).deactivation_source == "self"


# ── lifecycle ∥ lifecycle ────────────────────────────────────────────────────

def test_parallel_deactivate_has_exactly_one_success(client, test_email, admin,
                                                     no_deadlocks):
    uid, uuid = _student(test_email)
    n = 4
    barrier = threading.Barrier(n)

    def _task(_):
        barrier.wait()
        try:
            return ("ok", _deactivate(uuid, admin))
        except Exception as exc:   # noqa: BLE001
            return ("error", exc)

    with ThreadPoolExecutor(max_workers=n) as pool:
        results = list(pool.map(_task, range(n)))
    assert_no_deadlock_error(*results)
    assert [k for k, _ in results].count("ok") == 1
    errors = [e for k, e in results if k == "error"]
    assert all(isinstance(e, AuthError) and e.audit_code == "account_already_disabled"
               for e in errors)
    assert _events("admin_user_deactivated", uid) == 1


def test_deactivate_then_restore_in_parallel_is_consistent(
    client, test_email, admin, monkeypatch, no_deadlocks,
):
    uid, uuid = _student(test_email)
    gate = Gate()
    monkeypatch.setattr(users_storage, "disable_user_in_tx",
                        gate.wrap(users_storage.disable_user_in_tx))

    deact = run_in_thread(lambda: _deactivate(uuid, admin))
    gate.wait_reached()
    rest = run_in_thread(lambda: _restore(uuid, admin))
    wait_for_lock_waiter()                      # restore ждёт; увидит отключённого
    gate.release.set()

    r_deact, r_rest = deact.join(), rest.join()
    assert_no_deadlock_error(r_deact, r_rest)
    assert r_deact[0] == "ok" and r_rest[0] == "ok", (r_deact, r_rest)
    u = _user(uid)
    assert u.is_active is True and u.deactivation_source is None
    assert _events("admin_user_deactivated", uid) == 1
    assert _events("admin_user_activated", uid) == 1
