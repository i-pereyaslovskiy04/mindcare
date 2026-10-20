"""
ADR-028 — gated integration: единый обратимый lifecycle отключения и
восстановления аккаунта на реальном PostgreSQL (isolated runner).

Покрывает:
  * собственный аккаунт админа: DELETE / PATCH is_active=false / POST
    deactivate → 422 self_admin_protected без изменений БД (в т.ч. multi-role
    admin+student);
  * отключение другого пользователя: обязательная причина (422 без неё),
    шифрованная причина, источник admin, отзыв ВСЕХ сессий, одно
    admin_user_deactivated (metadata={}); повтор → 409;
  * старые сессии непригодны после отключения И после восстановления;
  * восстановление обычного отключённого и исторически soft-deleted
    аккаунта (включая is_active=true + deleted_at): id/uuid, роли, профиль,
    OAuth identity, consent сохранены; restore активного → 409;
  * редактирование отключённого (не удалённого) аккаунта сохраняется;
  * is_active NULL трактуется как активный во фильтрах/DTO/lifecycle;
  * самоотключение: только чистый student; staff (вкл. admin+student) и
    impersonation → 403; чужой id в теле не принимается;
  * impersonation: инициатор потерял admin / отключён → сессия 401;
  * регистрация (пароль и OAuth) отключение не обходит;
  * failure-injection на audit/commit: аккаунт и сессии откатываются вместе;
  * отсутствие причины/email/ФИО/токенов в новых lifecycle/failure-записях.
"""
import json
import uuid as _uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import Session

import app.auth.storage as auth_storage
import app.users.storage as users_storage
from app.audit.contracts import AuditStorageError
from app.core.encryption import decrypt_text
from app.db.models import (
    AuditLog, AuthLog, ConsentRecord, DataChangeLog, OtpVerification, Role,
    User, UserOAuthIdentity, UserRole, UserSession,
)
from app.db.session import SessionLocal
from tests.integration.conftest import (
    add_user_role, create_multi_role_user, create_test_user,
)

PASSWORD = "SecurePass42!"
REASON = "Обращение по служебной записке № 17 — конфиденциальная причина"


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _login(client, email, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _student(client, email):
    """Чистый student с активной сессией. → (user_id, uuid, token)."""
    uid = int(create_test_user(email, PASSWORD)["id"])
    r = _login(client, email)
    assert r.status_code == 200, r.text
    return uid, _uuid_for(uid), r.json()["session_token"]


def _uuid_for(user_id):
    with SessionLocal() as db:
        return str(db.get(User, user_id).uuid)


def _user(user_id):
    with SessionLocal() as db:
        u = db.get(User, user_id)
        db.expunge(u)
        return u


def _active_sessions(user_id):
    with SessionLocal() as db:
        return db.query(UserSession).filter(
            UserSession.user_id == user_id, ~UserSession.is_revoked,
        ).count()


def _audit_rows(event_type, entity_id=None, actor_id=None):
    with SessionLocal() as db:
        q = db.query(AuditLog).filter(AuditLog.event_type == event_type)
        if entity_id is not None:
            q = q.filter(AuditLog.entity_id == entity_id)
        if actor_id is not None:
            q = q.filter(AuditLog.user_id == actor_id)
        rows = q.order_by(AuditLog.id).all()
        for r in rows:
            db.expunge(r)
        return rows


def _max_ids():
    with SessionLocal() as db:
        return tuple(
            db.query(model.id).order_by(model.id.desc()).limit(1).scalar() or 0
            for model in (AuditLog, AuthLog, DataChangeLog)
        )


def _new_rows_since(marks):
    out = []
    with SessionLocal() as db:
        for model, mark in zip((AuditLog, AuthLog, DataChangeLog), marks):
            rows = db.query(model).filter(model.id > mark).all()
            for r in rows:
                db.expunge(r)
            out.append(rows)
    return out


def _blob(row):
    parts = []
    for col in row.__table__.columns:
        val = getattr(row, col.name, None)
        if isinstance(val, (dict, list)):
            val = json.dumps(val, ensure_ascii=False)
        parts.append("" if val is None else str(val))
    return " | ".join(parts)


def _assert_no_leak(rows, *secrets):
    for row in rows:
        blob = _blob(row)
        for s in secrets:
            assert s not in blob, (row.__tablename__, s)


def _deactivate(client, token, target_uuid, reason=REASON):
    return client.post(f"/api/admin/users/{target_uuid}/deactivate",
                       headers=_auth(token), json={"reason": reason})


def _restore(client, token, target_uuid):
    return client.post(f"/api/admin/users/{target_uuid}/restore",
                       headers=_auth(token))


def _soft_delete_historically(user_id, *, is_active=False):
    with SessionLocal() as db:
        u = db.get(User, user_id)
        u.deleted_at = datetime.now(timezone.utc)
        u.is_active = is_active
        db.commit()


@pytest.fixture
def failing_commit():
    """Сбой commit на уровне ORM: транзакция откатывается целиком.

    Срабатывает только на commit, где изменяется строка User (lifecycle),
    а не на служебных commit'ах dependency (touch_session и т.п.)."""
    state = {"armed": True}

    def _boom(session):
        if state["armed"] and any(isinstance(o, User) for o in session.dirty):
            state["armed"] = False
            raise RuntimeError("injected commit failure")
    event.listen(Session, "before_commit", _boom)
    try:
        yield state
    finally:
        event.remove(Session, "before_commit", _boom)


# ══════════════════════════════════════════════════════════════════════════
# 1. Собственный аккаунт администратора
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("roles", [["admin"], ["admin", "student"],
                                   ["admin", "supervisor", "student"]])
def test_admin_cannot_disable_or_delete_self(client, roles):
    token, admin_id, _ = create_multi_role_user(client, roles)
    admin_uuid = _uuid_for(admin_id)
    sessions_before = _active_sessions(admin_id)

    r_del = client.delete(f"/api/admin/users/{admin_uuid}", headers=_auth(token))
    r_patch = client.patch(f"/api/admin/users/{admin_uuid}", headers=_auth(token),
                           json={"is_active": False})
    r_post = _deactivate(client, token, admin_uuid)
    for r in (r_del, r_patch, r_post):
        assert r.status_code == 422, r.text

    u = _user(admin_id)
    assert u.is_active is True and u.deleted_at is None
    assert (u.deactivated_at, u.deactivation_source, u.deactivation_reason_enc) == (
        None, None, None,
    )
    assert _active_sessions(admin_id) == sessions_before
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200
    for ev in ("admin_user_delete_failed", "admin_user_update_failed",
               "admin_user_deactivate_failed"):
        rows = _audit_rows(ev, actor_id=admin_id)
        assert rows and rows[-1].failure_reason_code == "self_admin_protected"
    assert _audit_rows("admin_user_deactivated", entity_id=admin_id) == []


def test_admin_cannot_remove_own_admin_role_still_holds(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin", "psychologist"])
    r = client.patch(f"/api/admin/users/{_uuid_for(admin_id)}", headers=_auth(token),
                     json={"roles": ["psychologist"]})
    assert r.status_code == 422, r.text
    assert "admin" in client.get("/api/auth/me", headers=_auth(token)).json()["roles"]


# ══════════════════════════════════════════════════════════════════════════
# 2. Отключение другого пользователя
# ══════════════════════════════════════════════════════════════════════════

def test_deactivate_with_reason_revokes_all_sessions_and_audits(client, test_email):
    token, admin_id, admin_email = create_multi_role_user(client, ["admin"])
    uid, target_uuid, student_token = _student(client, test_email)
    second = _login(client, test_email).json()["session_token"]
    assert _active_sessions(uid) == 2
    marks = _max_ids()

    r = _deactivate(client, token, target_uuid, reason=f"  {REASON}  ")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_active"] is False and body["deactivation_source"] == "admin"
    assert REASON not in r.text

    u = _user(uid)
    assert u.is_active is False and u.deleted_at is None
    assert u.email == test_email                        # email сохранён
    assert u.deactivation_reason_enc.startswith("enc:v1:")
    assert decrypt_text(u.deactivation_reason_enc) == REASON   # trim
    assert _active_sessions(uid) == 0
    for tok in (student_token, second):
        assert client.get("/api/auth/me", headers=_auth(tok)).status_code == 401

    (row,) = _audit_rows("admin_user_deactivated", entity_id=uid)
    assert (row.user_id, row.user_role, row.entity_type) == (admin_id, "admin", "user")
    assert row.outcome == "success" and (row.log_metadata or {}) == {}
    assert row.description is None

    audit_new, auth_new, dcl_new = _new_rows_since(marks)
    assert [r.event_type for r in audit_new] == ["admin_user_deactivated"]
    assert dcl_new == []                     # lifecycle не пишет DCL
    _assert_no_leak(audit_new, REASON, "конфиденциальная", test_email,
                    admin_email, "Integration Test User", student_token)

    # Вход отключённого — 403 account_disabled (после верного пароля).
    r = _login(client, test_email)
    assert r.status_code == 403
    assert auth_new == []                    # сама операция auth_log не пишет


@pytest.mark.parametrize("body", [
    {}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501},
    {"reason": "ok", "source": "self"},
])
def test_deactivate_without_valid_reason_is_422_without_changes(
    client, test_email, body,
):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, student_token = _student(client, test_email)
    r = client.post(f"/api/admin/users/{target_uuid}/deactivate",
                    headers=_auth(token), json=body)
    assert r.status_code == 422, r.text
    u = _user(uid)
    assert u.is_active is True and u.deactivation_source is None
    assert client.get("/api/auth/me", headers=_auth(student_token)).status_code == 200
    assert _audit_rows("admin_user_deactivated", entity_id=uid) == []


def test_repeat_deactivate_is_409(client, test_email):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    assert _deactivate(client, token, target_uuid).status_code == 200
    r = _deactivate(client, token, target_uuid, reason="Ещё раз")
    assert r.status_code == 409, r.text
    assert decrypt_text(_user(uid).deactivation_reason_enc) == REASON  # не перезаписана
    assert len(_audit_rows("admin_user_deactivated", entity_id=uid)) == 1
    rows = _audit_rows("admin_user_deactivate_failed", actor_id=admin_id)
    assert rows[-1].failure_reason_code == "account_already_disabled"


def test_deactivate_unknown_user_is_404(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    for target in (str(_uuid.uuid4()), "not-a-uuid"):
        r = _deactivate(client, token, target)
        assert r.status_code == 404, r.text
    rows = _audit_rows("admin_user_deactivate_failed", actor_id=admin_id)
    assert [r.failure_reason_code for r in rows[-2:]] == ["user_not_found"] * 2


def test_admin_can_deactivate_another_admin_and_its_impersonation_dies(
    client, test_email,
):
    token_a, _a_id, _ = create_multi_role_user(client, ["admin"])
    token_b, b_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    imp = client.post(f"/api/admin/users/{target_uuid}/impersonate",
                      headers=_auth(token_b))
    assert imp.status_code == 200, imp.text
    imp_token = imp.json()["session_token"]

    r = _deactivate(client, token_a, _uuid_for(b_id))
    assert r.status_code == 200, r.text
    assert client.get("/api/auth/me", headers=_auth(token_b)).status_code == 401
    # impersonation-сессия, созданная отключённым админом, тоже недействительна
    assert client.get("/api/auth/me", headers=_auth(imp_token)).status_code == 401
    assert _user(uid).is_active is True       # цель не затронута


# ══════════════════════════════════════════════════════════════════════════
# 3. Восстановление
# ══════════════════════════════════════════════════════════════════════════

def test_restore_disabled_keeps_identity_and_old_sessions_stay_dead(
    client, test_email,
):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, old_token = _student(client, test_email)
    before = _user(uid)
    assert _deactivate(client, token, target_uuid).status_code == 200

    r = _restore(client, token, target_uuid)
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True and r.json()["deactivation_source"] is None

    u = _user(uid)
    assert (u.id, str(u.uuid), u.email) == (before.id, str(before.uuid), before.email)
    assert (u.deactivated_at, u.deactivation_source, u.deactivation_reason_enc) == (
        None, None, None,
    )
    # Старый токен не оживает; новый вход работает.
    assert client.get("/api/auth/me", headers=_auth(old_token)).status_code == 401
    r = _login(client, test_email)
    assert r.status_code == 200, r.text
    me = client.get("/api/auth/me", headers=_auth(r.json()["session_token"]))
    assert me.status_code == 200 and me.json()["roles"] == ["student"]
    (row,) = _audit_rows("admin_user_activated", entity_id=uid)
    assert row.user_id == admin_id and (row.log_metadata or {}) == {}


@pytest.mark.parametrize("historical_is_active", [False, True])
def test_restore_historically_soft_deleted_account(
    client, test_email, historical_is_active,
):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, old_token = _student(client, test_email)
    add_user_role(uid, "psychologist")                  # роли сохраняются как есть
    with SessionLocal() as db:
        consent_id = db.execute(
            text("SELECT id FROM consents ORDER BY id LIMIT 1")
        ).scalar()
        db.add(ConsentRecord(user_id=uid, consent_id=consent_id, accepted=True))
        db.add(UserOAuthIdentity(user_id=uid, provider="yandex",
                                 provider_subject=f"integ_{_uuid.uuid4().hex}"))
        db.commit()
        consents = db.query(ConsentRecord).filter(ConsentRecord.user_id == uid).count()
    _soft_delete_historically(uid, is_active=historical_is_active)
    # Исторически удалённый виден в фильтре «Отключён» без include_deleted.
    listing = client.get("/api/admin/users/?is_active=false&size=100",
                         headers=_auth(token)).json()
    assert target_uuid in {i["uuid"] for i in listing["items"]}

    r = _restore(client, token, target_uuid)
    assert r.status_code == 200, r.text
    assert sorted(r.json()["roles"]) == ["psychologist", "student"]

    u = _user(uid)
    assert u.deleted_at is None and u.is_active is True and str(u.uuid) == target_uuid
    with SessionLocal() as db:
        assert db.query(ConsentRecord).filter(
            ConsentRecord.user_id == uid).count() == consents
        assert db.query(UserOAuthIdentity).filter(
            UserOAuthIdentity.user_id == uid).count() == 1
        roles_rows = db.query(UserRole).filter(UserRole.user_id == uid).count()
        assert roles_rows == 2                           # новых ролей нет
        assert db.query(User).filter(User.email == test_email).count() == 1
    assert client.get("/api/auth/me", headers=_auth(old_token)).status_code == 401
    assert len(_audit_rows("admin_user_activated", entity_id=uid)) == 1


@pytest.mark.parametrize("is_active", [True, None])
def test_restore_active_account_is_409(client, test_email, is_active):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    with SessionLocal() as db:
        db.get(User, uid).is_active = is_active
        db.commit()
    r = _restore(client, token, target_uuid)
    assert r.status_code == 409, r.text
    assert _audit_rows("admin_user_activated", entity_id=uid) == []
    rows = _audit_rows("admin_user_restore_failed", actor_id=admin_id)
    assert rows[-1].failure_reason_code == "account_already_active"


def test_restore_revokes_session_that_survived_deactivation(client, test_email):
    """Строка сессии, «пережившая» отключение (гонка до ADR-028), после
    restore недействительна: restore отзывает все оставшиеся сессии."""
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    assert _deactivate(client, token, target_uuid).status_code == 200
    raw, _exp = auth_storage.create_session(str(uid))   # прямая вставка в обход входа
    assert _active_sessions(uid) == 1

    assert _restore(client, token, target_uuid).status_code == 200
    assert _active_sessions(uid) == 0
    assert client.get("/api/auth/me", headers=_auth(raw)).status_code == 401


# ══════════════════════════════════════════════════════════════════════════
# 4. Редактирование отключённого и is_active NULL
# ══════════════════════════════════════════════════════════════════════════

def test_disabled_not_deleted_account_remains_editable(client, test_email):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    assert _deactivate(client, token, target_uuid).status_code == 200
    before = _user(uid)

    r = client.get(f"/api/admin/users/{target_uuid}", headers=_auth(token))
    assert r.status_code == 200 and r.json()["is_active"] is False
    r = client.patch(f"/api/admin/users/{target_uuid}", headers=_auth(token),
                     json={"full_name": "Новое Имя Отключённого", "is_active": False})
    assert r.status_code == 200, r.text
    u = _user(uid)
    assert u.full_name == "Новое Имя Отключённого"
    assert u.is_active is False
    assert (u.deactivation_source, u.deactivation_reason_enc) == (
        before.deactivation_source, before.deactivation_reason_enc,
    )


def test_null_is_active_is_treated_as_active_everywhere(client, test_email):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    with SessionLocal() as db:
        db.get(User, uid).is_active = None
        db.commit()

    active = client.get(f"/api/admin/users/?is_active=true&search={test_email}",
                        headers=_auth(token)).json()
    disabled = client.get(f"/api/admin/users/?is_active=false&search={test_email}",
                          headers=_auth(token)).json()
    assert [i["uuid"] for i in active["items"]] == [target_uuid]
    assert active["items"][0]["is_active"] is True
    assert disabled["items"] == []
    detail = client.get(f"/api/admin/users/{target_uuid}", headers=_auth(token))
    assert detail.json()["is_active"] is True
    # PATCH is_active=true — no-op, не «переход»
    r = client.patch(f"/api/admin/users/{target_uuid}", headers=_auth(token),
                     json={"is_active": True})
    assert r.status_code == 200, r.text
    assert _restore(client, token, target_uuid).status_code == 409
    assert _deactivate(client, token, target_uuid).status_code == 200
    assert _user(uid).is_active is False


# ══════════════════════════════════════════════════════════════════════════
# 5. Самоотключение
# ══════════════════════════════════════════════════════════════════════════

def _self_deactivate(client, token, body=None):
    return client.post("/api/auth/account/deactivate", headers=_auth(token),
                       json=body if body is not None else {"confirm": True})


def test_pure_student_can_deactivate_self(client, test_email):
    uid, _target_uuid, token = _student(client, test_email)
    second = _login(client, test_email).json()["session_token"]
    marks = _max_ids()

    r = _self_deactivate(client, token)
    assert r.status_code == 200, r.text

    u = _user(uid)
    assert u.is_active is False and u.deleted_at is None and u.email == test_email
    assert u.deactivation_source == "self"
    assert decrypt_text(u.deactivation_reason_enc) == "По запросу пользователя"
    assert _active_sessions(uid) == 0
    for tok in (token, second):
        assert client.get("/api/auth/me", headers=_auth(tok)).status_code == 401
    (row,) = _audit_rows("user_self_deactivated", entity_id=uid)
    assert (row.user_id, row.user_role) == (uid, "student")
    assert (row.log_metadata or {}) == {} and row.outcome == "success"

    audit_new, auth_new, dcl_new = _new_rows_since(marks)
    assert [r.event_type for r in audit_new] == ["user_self_deactivated"]
    assert auth_new == [] and dcl_new == []
    _assert_no_leak(audit_new, "По запросу", test_email, token)
    assert _login(client, test_email).status_code == 403


@pytest.mark.parametrize("roles,acting", [
    (["psychologist", "student"], "psychologist"),
    (["supervisor", "student"], "supervisor"),
    (["admin", "student"], "admin"),
    (["admin"], "admin"),
])
def test_staff_cannot_self_deactivate(client, roles, acting):
    token, uid, _ = create_multi_role_user(client, roles)
    r = _self_deactivate(client, token)
    assert r.status_code == 403, r.text
    assert _user(uid).is_active is True
    assert client.get("/api/auth/me", headers=_auth(token)).status_code == 200
    rows = _audit_rows("user_self_deactivate_failed", actor_id=uid)
    assert rows[-1].failure_reason_code == "self_deactivation_not_allowed"
    assert rows[-1].user_role == acting
    assert _audit_rows("user_self_deactivated", entity_id=uid) == []


@pytest.mark.parametrize("body", [
    {}, {"confirm": False}, {"confirm": "true"},
    {"confirm": True, "user_id": 1}, {"confirm": True, "uuid": "x"},
])
def test_self_deactivate_rejects_foreign_target_and_bad_body(client, test_email, body):
    uid, _u, token = _student(client, test_email)
    other_id, _ou, other_token = _student(client, f"integ_other_{test_email}")
    if "user_id" in body:
        body = {**body, "user_id": other_id}
    r = _self_deactivate(client, token, body)
    assert r.status_code == 422, r.text
    assert _user(uid).is_active is True and _user(other_id).is_active is True
    assert client.get("/api/auth/me", headers=_auth(other_token)).status_code == 200


def test_self_deactivate_in_impersonation_is_forbidden_and_attributed_to_admin(
    client, test_email,
):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    imp = client.post(f"/api/admin/users/{target_uuid}/impersonate",
                      headers=_auth(token)).json()["session_token"]

    r = _self_deactivate(client, imp)
    assert r.status_code == 403, r.text
    assert _user(uid).is_active is True
    rows = _audit_rows("user_self_deactivate_failed", actor_id=admin_id)
    assert rows[-1].failure_reason_code == "impersonation_forbidden"
    assert rows[-1].user_role == "admin"
    assert _audit_rows("user_self_deactivate_failed", actor_id=uid) == []


@pytest.mark.parametrize("change", ["role_removed", "admin_disabled"])
def test_impersonation_session_dies_when_initiator_loses_authority(
    client, test_email, change,
):
    token, admin_id, _ = create_multi_role_user(client, ["admin", "student"])
    uid, target_uuid, _ = _student(client, test_email)
    imp = client.post(f"/api/admin/users/{target_uuid}/impersonate",
                      headers=_auth(token)).json()["session_token"]
    assert client.get("/api/auth/me", headers=_auth(imp)).status_code == 200

    with SessionLocal() as db:
        if change == "role_removed":
            admin_role = db.query(Role).filter(Role.name == "admin").one()
            db.query(UserRole).filter(
                UserRole.user_id == admin_id, UserRole.role_id == admin_role.id,
            ).delete(synchronize_session=False)
        else:
            db.get(User, admin_id).is_active = False
        db.commit()

    failed_before = len(_audit_rows("user_self_deactivate_failed"))
    r = _self_deactivate(client, imp)
    assert r.status_code == 401, r.text
    assert client.get("/api/auth/me", headers=_auth(imp)).status_code == 401
    with SessionLocal() as db:
        s = db.query(UserSession).filter(
            UserSession.impersonator_user_id == admin_id).one()
        assert s.is_revoked is True
    # Действие не выполнено и никому не приписано: ни target, ни инициатору.
    assert len(_audit_rows("user_self_deactivate_failed")) == failed_before
    assert _user(uid).is_active is True


# ══════════════════════════════════════════════════════════════════════════
# 6. Регистрация и OAuth не обходят отключение
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("state", ["disabled", "soft_deleted"])
def test_register_init_rejects_disabled_and_deleted(client, test_email,
                                                    capture_emails, state):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    if state == "disabled":
        assert _deactivate(client, token, target_uuid).status_code == 200
    else:
        _soft_delete_historically(uid)

    r = client.post("/api/auth/register/init", json={
        "name": "Повтор Регистрации", "email": test_email, "password": PASSWORD,
    })
    assert r.status_code == 409, r.text
    with SessionLocal() as db:
        assert db.query(OtpVerification).filter(
            OtpVerification.email == test_email).count() == 0
        assert db.query(User).filter(User.email == test_email).count() == 1
    assert _user(uid).is_active is False


@pytest.mark.parametrize("state", ["disabled", "soft_deleted"])
def test_oauth_login_and_registration_do_not_bypass(client, test_email, state):
    from app.oauth import service as oauth_service
    from app.oauth.errors import OAuthRegistrationError
    from tests.oauth_fakes import FakeProvider, registered

    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    if state == "disabled":
        assert _deactivate(client, token, target_uuid).status_code == 200
    else:
        _soft_delete_historically(uid)

    # login по уже привязанной identity
    with registered(FakeProvider("yandex")) as fake:
        with SessionLocal() as db:
            db.add(UserOAuthIdentity(user_id=uid, provider="yandex",
                                     provider_subject=fake.subject))
            db.commit()
        start = oauth_service.start_login("yandex")
        outcome = oauth_service.handle_callback(
            "yandex", {"state": start.state, "code": fake.issue_code(start.state)},
            start.state,
        )
        assert "ticket" not in outcome.fragment
        assert outcome.audit_code == "account_disabled"

    # регистрация новой identity на тот же email
    with registered(FakeProvider("yandex", email=test_email)) as fake2:
        start = oauth_service.start_login("yandex")
        outcome = oauth_service.handle_callback(
            "yandex", {"state": start.state, "code": fake2.issue_code(start.state)},
            start.state,
        )
        assert outcome.fragment.get("result") == "registration"
        with pytest.raises(OAuthRegistrationError) as ei:
            oauth_service.registration_init(outcome.fragment["ticket"])
        assert ei.value.code == "email_already_exists"
    u = _user(uid)
    assert u.is_active is False
    with SessionLocal() as db:
        assert db.query(UserOAuthIdentity).filter(
            UserOAuthIdentity.user_id == uid).count() == 1   # без auto-link


# ══════════════════════════════════════════════════════════════════════════
# 7. Failure-injection: аккаунт и сессии откатываются вместе
# ══════════════════════════════════════════════════════════════════════════

def _boom_on(event_name):
    original = users_storage.record_event

    def _rec(**kw):
        if kw.get("event") == event_name:
            raise AuditStorageError("injected audit failure")
        return original(**kw)
    return _rec


@pytest.mark.parametrize("mode", ["audit", "commit"])
def test_deactivate_failure_rolls_back_account_and_sessions(
    client, test_email, monkeypatch, request, mode,
):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, student_token = _student(client, test_email)
    if mode == "audit":
        monkeypatch.setattr(users_storage, "record_event",
                            _boom_on("admin_user_deactivated"))
        expected = AuditStorageError
    else:
        request.getfixturevalue("failing_commit")
        expected = RuntimeError
    with pytest.raises(expected):
        _deactivate(client, token, target_uuid)
    u = _user(uid)
    assert u.is_active is True and u.deactivation_reason_enc is None
    assert _active_sessions(uid) == 1
    assert client.get("/api/auth/me", headers=_auth(student_token)).status_code == 200
    assert _audit_rows("admin_user_deactivated", entity_id=uid) == []


@pytest.mark.parametrize("mode", ["audit", "commit"])
def test_restore_failure_rolls_back(client, test_email, monkeypatch, request, mode):
    token, _admin_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, _ = _student(client, test_email)
    _soft_delete_historically(uid)
    if mode == "audit":
        monkeypatch.setattr(users_storage, "record_event",
                            _boom_on("admin_user_activated"))
        expected = AuditStorageError
    else:
        request.getfixturevalue("failing_commit")
        expected = RuntimeError
    with pytest.raises(expected):
        _restore(client, token, target_uuid)
    u = _user(uid)
    assert u.deleted_at is not None and u.is_active is False


@pytest.mark.parametrize("mode", ["audit", "commit"])
def test_self_deactivate_failure_rolls_back(client, test_email, monkeypatch,
                                            request, mode):
    uid, _u, token = _student(client, test_email)
    if mode == "audit":
        original = auth_storage.record_event

        def _rec(**kw):
            if kw.get("event") == "user_self_deactivated":
                raise AuditStorageError("injected")
            return original(**kw)
        monkeypatch.setattr(auth_storage, "record_event", _rec)
        expected = AuditStorageError
    else:
        expected = RuntimeError
    if mode == "commit":
        request.getfixturevalue("failing_commit")
    with pytest.raises(expected):
        _self_deactivate(client, token)
    u = _user(uid)
    assert u.is_active is True and u.deactivation_source is None
    assert _active_sessions(uid) == 1


# ══════════════════════════════════════════════════════════════════════════
# 8. Restore исторического администратора: impersonation-сессии не оживают
# ══════════════════════════════════════════════════════════════════════════

def _revoked_flags(user_id=None, impersonator_id=None):
    with SessionLocal() as db:
        q = db.query(UserSession)
        if user_id is not None:
            q = q.filter(UserSession.user_id == user_id)
        if impersonator_id is not None:
            q = q.filter(UserSession.impersonator_user_id == impersonator_id)
        return [s.is_revoked for s in q.all()]


def _admin_with_impersonation(client, test_email):
    """Админ A с impersonation-сессией под студентом + обычная сессия студента.

    Токены ЗДЕСЬ не используются для запросов: dependency сама отзывает
    сессию отключённого/утратившего права, что скрыло бы дефект."""
    token_a, a_id, _ = create_multi_role_user(client, ["admin"])
    uid, target_uuid, student_token = _student(client, test_email)
    imp = client.post(f"/api/admin/users/{target_uuid}/impersonate",
                      headers=_auth(token_a))
    assert imp.status_code == 200, imp.text
    return token_a, a_id, imp.json()["session_token"], uid, student_token


def _historically_disable(user_id, kind):
    """Историческое отключение БЕЗ отзыва сессий (как до ADR-028)."""
    with SessionLocal() as db:
        u = db.get(User, user_id)
        u.is_active = False
        if kind == "soft_deleted":
            u.deleted_at = datetime.now(timezone.utc)
        elif kind == "soft_deleted_active_flag":
            u.is_active = True
            u.deleted_at = datetime.now(timezone.utc)
        db.commit()


@pytest.mark.parametrize("kind", ["disabled", "soft_deleted",
                                  "soft_deleted_active_flag"])
def test_restore_historical_admin_revokes_own_and_impersonation_sessions(
    client, test_email, kind,
):
    token_a, a_id, imp_token, uid, student_token = _admin_with_impersonation(
        client, test_email)
    token_b, b_id, _ = create_multi_role_user(client, ["admin"])
    _historically_disable(a_id, kind)
    # Сессии не отозваны (модель исторического состояния).
    assert _revoked_flags(user_id=a_id) == [False]
    assert _revoked_flags(impersonator_id=a_id) == [False]
    target_flags_before = _revoked_flags(user_id=uid)

    r = _restore(client, token_b, _uuid_for(a_id))
    assert r.status_code == 200, r.text

    assert all(_revoked_flags(user_id=a_id))             # собственные
    assert _revoked_flags(impersonator_id=a_id) == [True]  # impersonation
    for tok in (token_a, imp_token):
        assert client.get("/api/auth/me", headers=_auth(tok)).status_code == 401
    # Цель и её обычная сессия не затронуты: отозвана ровно одна строка цели —
    # impersonation-сессия администратора (её user_id == цель).
    assert _revoked_flags(user_id=uid).count(False) == (
        target_flags_before.count(False) - 1)
    assert client.get("/api/auth/me",
                      headers=_auth(student_token)).status_code == 200
    assert _user(uid).is_active is True
    (row,) = _audit_rows("admin_user_activated", entity_id=a_id)
    assert (row.user_id, row.user_role) == (b_id, "admin")
    assert (row.log_metadata or {}) == {}


def test_restore_audit_failure_rolls_back_both_revocations(
    client, test_email, monkeypatch,
):
    token_a, a_id, imp_token, uid, student_token = _admin_with_impersonation(
        client, test_email)
    token_b, _b_id, _ = create_multi_role_user(client, ["admin"])
    _historically_disable(a_id, "soft_deleted")
    monkeypatch.setattr(users_storage, "record_event",
                        _boom_on("admin_user_activated"))

    with pytest.raises(AuditStorageError):
        _restore(client, token_b, _uuid_for(a_id))

    u = _user(a_id)
    assert u.deleted_at is not None and u.is_active is False
    assert _revoked_flags(user_id=a_id) == [False]         # собственные целы
    assert _revoked_flags(impersonator_id=a_id) == [False]  # impersonation цела
    assert _audit_rows("admin_user_activated", entity_id=a_id) == []
