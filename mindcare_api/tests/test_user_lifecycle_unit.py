"""
ADR-028 — no-DB unit-тесты единого lifecycle отключения/восстановления.

  * схемы: причина отключения (trim/обязательность/длина, лишние поля → 422),
    тело самоотключения (только confirm=true, чужой id не принимается);
  * get_current_user: impersonation-сессия недействительна, если инициатор
    удалён / отключён / потерял admin (сессия отзывается, 401); роль
    инициатора в user dict — подтверждённая membership;
  * route самоотключения: impersonation → 403 и failure от администратора-
    инициатора (НЕ от target); staff → failure от самого пользователя с его
    primary-ролью; non-AuthError не превращается в failure-аудит;
  * route admin deactivate/restore: ровно одна secondary-failure строка.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

import app.auth.deps as deps
import app.auth.routes as auth_routes
import app.users.routes_admin as routes_admin
from app.auth.schemas import SelfDeactivateRequest
from app.auth.service import AuthError
from app.users.schemas import (
    DEACTIVATION_REASON_MAX_LEN, AdminUserDeactivateRequest,
)

ADMIN_ID = 101
TARGET_ID = 202


# ── схемы ────────────────────────────────────────────────────────────────────

def test_reason_is_trimmed():
    assert AdminUserDeactivateRequest(reason="  Причина \n").reason == "Причина"


@pytest.mark.parametrize("bad", ["", "   ", "\n\t ", "x" * (DEACTIVATION_REASON_MAX_LEN + 1)])
def test_reason_empty_or_too_long_rejected(bad):
    with pytest.raises(ValidationError):
        AdminUserDeactivateRequest(reason=bad)


def test_reason_at_max_length_accepted():
    body = AdminUserDeactivateRequest(reason="я" * DEACTIVATION_REASON_MAX_LEN)
    assert len(body.reason) == DEACTIVATION_REASON_MAX_LEN


def test_reason_required_and_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        AdminUserDeactivateRequest()
    with pytest.raises(ValidationError):
        AdminUserDeactivateRequest(reason="ok", source="self")


@pytest.mark.parametrize("payload", [
    {},                                     # нет confirm
    {"confirm": False},                     # не подтверждено
    {"confirm": "true"},                    # строка, не StrictBool
    {"confirm": 1},
    {"confirm": True, "user_id": 5},        # чужой id передать нельзя
    {"confirm": True, "uuid": "x"},
    {"confirm": True, "email": "a@b.c"},
])
def test_self_deactivate_body_strict(payload):
    with pytest.raises(ValidationError):
        SelfDeactivateRequest(**payload)


def test_self_deactivate_body_ok():
    assert SelfDeactivateRequest(confirm=True).confirm is True


# ── get_current_user: impersonation-инициатор ────────────────────────────────

def _deps_storage(monkeypatch, *, admin):
    revoked = []
    target = {"id": str(TARGET_ID), "name": "Студент", "roles": ["student"],
              "role": "student", "is_active": True}
    monkeypatch.setattr(deps.storage, "find_session", lambda tok: {
        "user_id": str(TARGET_ID), "impersonator_user_id": ADMIN_ID,
    })
    monkeypatch.setattr(deps.storage, "touch_session", lambda tok: None)
    monkeypatch.setattr(
        deps.storage, "find_user_by_id",
        lambda uid: target if str(uid) == str(TARGET_ID) else admin,
    )
    monkeypatch.setattr(deps.storage, "revoke_session", revoked.append)
    return revoked


def test_impersonation_with_valid_admin_marks_confirmed_role(monkeypatch):
    revoked = _deps_storage(monkeypatch, admin={
        "id": str(ADMIN_ID), "name": "Админ", "roles": ["admin", "student"],
        "is_active": True,
    })
    user = deps.get_current_user("tok")
    assert user["id"] == str(TARGET_ID)
    assert user["impersonator_user_id"] == ADMIN_ID
    assert user["impersonator_role"] == "admin"
    assert revoked == []


@pytest.mark.parametrize("admin", [
    None,                                                     # удалён
    {"id": str(ADMIN_ID), "name": "A", "roles": ["admin"], "is_active": False},
    {"id": str(ADMIN_ID), "name": "A", "roles": ["student"], "is_active": True},
    {"id": str(ADMIN_ID), "name": "A", "roles": [], "is_active": True},
])
def test_impersonation_with_invalid_initiator_revokes_and_401(monkeypatch, admin):
    revoked = _deps_storage(monkeypatch, admin=admin)
    with pytest.raises(HTTPException) as ei:
        deps.get_current_user("tok")
    assert ei.value.status_code == 401
    assert revoked == ["tok"]


# ── route самоотключения ─────────────────────────────────────────────────────

def _req():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})


@pytest.fixture
def secondary(monkeypatch):
    calls = []
    monkeypatch.setattr(auth_routes, "record_secondary_failure",
                        lambda **kw: calls.append(kw))
    return calls


def test_self_deactivate_in_impersonation_attributed_to_initiator(monkeypatch, secondary):
    def _never(*a, **k):
        raise AssertionError("service must not be called in impersonation")
    monkeypatch.setattr(auth_routes.service, "deactivate_own_account", _never)
    cu = {"id": str(TARGET_ID), "roles": ["student"], "role": "student",
          "impersonator_user_id": ADMIN_ID, "impersonator_role": "admin"}
    with pytest.raises(HTTPException) as ei:
        auth_routes.deactivate_own_account(
            body=SelfDeactivateRequest(confirm=True), request=_req(),
            current_user=cu,
        )
    assert ei.value.status_code == 403
    (kw,) = secondary
    assert kw["event"] == "user_self_deactivate_failed"
    assert kw["failure_reason_code"] == "impersonation_forbidden"
    assert (kw["actor"].user_id, kw["actor"].role) == (ADMIN_ID, "admin")
    assert kw["actor"].user_id != TARGET_ID          # не приписано target


def test_self_deactivate_staff_failure_uses_primary_role(monkeypatch, secondary):
    def _deny(user, **k):
        raise AuthError("x", 403, audit_code="self_deactivation_not_allowed")
    monkeypatch.setattr(auth_routes.service, "deactivate_own_account", _deny)
    cu = {"id": "7", "roles": ["psychologist", "student"], "role": "psychologist"}
    with pytest.raises(HTTPException) as ei:
        auth_routes.deactivate_own_account(
            body=SelfDeactivateRequest(confirm=True), request=_req(),
            current_user=cu,
        )
    assert ei.value.status_code == 403
    (kw,) = secondary
    assert (kw["actor"].user_id, kw["actor"].role) == (7, "psychologist")
    assert kw["failure_reason_code"] == "self_deactivation_not_allowed"


def test_self_deactivate_success_and_target_is_current_user(monkeypatch, secondary):
    seen = {}
    monkeypatch.setattr(auth_routes.service, "deactivate_own_account",
                        lambda user, **k: seen.setdefault("user", user))
    cu = {"id": "9", "roles": ["student"], "role": "student"}
    out = auth_routes.deactivate_own_account(
        body=SelfDeactivateRequest(confirm=True), request=_req(), current_user=cu,
    )
    assert out == {"message": "Аккаунт отключён"}
    assert seen["user"] is cu
    assert secondary == []


def test_self_deactivate_technical_failure_not_audited_as_business(monkeypatch, secondary):
    def _boom(user, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(auth_routes.service, "deactivate_own_account", _boom)
    with pytest.raises(RuntimeError):
        auth_routes.deactivate_own_account(
            body=SelfDeactivateRequest(confirm=True), request=_req(),
            current_user={"id": "9", "roles": ["student"], "role": "student"},
        )
    assert secondary == []


@pytest.mark.parametrize("roles", [["psychologist", "student"], ["admin", "student"],
                                   ["supervisor", "student"], ["student", "admin"]])
def test_service_rejects_non_pure_student_before_storage(monkeypatch, roles):
    import app.auth.service as auth_service

    def _never(*a, **k):
        raise AssertionError("storage must not be called for staff")
    monkeypatch.setattr(auth_service.storage, "self_deactivate_atomic", _never)
    with pytest.raises(AuthError) as ei:
        auth_service.deactivate_own_account({"id": "5", "roles": roles})
    assert (ei.value.status_code, ei.value.audit_code) == (
        403, "self_deactivation_not_allowed",
    )


def test_service_maps_lock_time_staff_detection(monkeypatch):
    """Под блокировкой роль staff появилась конкурентно → тот же 403."""
    import app.auth.service as auth_service

    def _raise(*a, **k):
        raise auth_service.storage.SelfDeactivationNotAllowedError("x")
    monkeypatch.setattr(auth_service.storage, "self_deactivate_atomic", _raise)
    with pytest.raises(AuthError) as ei:
        auth_service.deactivate_own_account({"id": "5", "roles": ["student"]})
    assert ei.value.audit_code == "self_deactivation_not_allowed"


# ── route admin deactivate/restore: одна secondary-failure строка ────────────

@pytest.fixture
def admin_secondary(monkeypatch):
    calls = []
    monkeypatch.setattr(routes_admin, "record_secondary_failure",
                        lambda **kw: calls.append(kw))
    return calls


_ADMIN_CU = {"id": str(ADMIN_ID), "roles": ["admin"], "role": "admin"}


@pytest.mark.parametrize("route,svc,event", [
    ("deactivate_user", "deactivate_user", "admin_user_deactivate_failed"),
    ("restore_user", "restore_user", "admin_user_restore_failed"),
])
def test_admin_lifecycle_route_writes_one_failure(monkeypatch, admin_secondary,
                                                  route, svc, event):
    def _deny(*a, **k):
        raise AuthError("x", 409, audit_code="account_already_disabled"
                        if svc == "deactivate_user" else "account_already_active")
    monkeypatch.setattr(routes_admin.service, svc, _deny)
    kwargs = dict(request=_req(), uuid="u", current_user=_ADMIN_CU)
    if route == "deactivate_user":
        kwargs["body"] = AdminUserDeactivateRequest(reason="r")
    with pytest.raises(HTTPException) as ei:
        getattr(routes_admin, route)(**kwargs)
    assert ei.value.status_code == 409
    (kw,) = admin_secondary
    assert kw["event"] == event
    assert kw["actor"].user_id == ADMIN_ID and kw["actor"].role == "admin"


def test_admin_deactivate_route_passes_trimmed_reason_only(monkeypatch, admin_secondary):
    seen = {}

    def _ok(uuid, reason, **k):
        seen.update(uuid=uuid, reason=reason, **k)
        return {"id": TARGET_ID}
    monkeypatch.setattr(routes_admin.service, "deactivate_user", _ok)
    routes_admin.deactivate_user(
        request=_req(), uuid="u",
        body=AdminUserDeactivateRequest(reason="  Нарушение  "),
        current_user=_ADMIN_CU,
    )
    assert seen["reason"] == "Нарушение"
    assert seen["actor_id"] == ADMIN_ID and seen["actor_role"] == "admin"
    assert admin_secondary == []
