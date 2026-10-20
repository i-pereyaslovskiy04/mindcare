"""
ADR-025 — no-DB unit-тесты impersonation («Зайти под именем»).

Покрывают:
  * guard-набор service.impersonate_target (self / admin-цель / заблокирован /
    без ролей / не найден → AuthError с ожидаемым status);
  * happy-path route: создаётся сессия с impersonator_user_id и пишется
    audit-событие admin_user_impersonated с target=целевой пользователь.

Реальная БД не используется.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

import app.users.service as users_service
import app.users.routes_admin as routes_admin
from app.audit.contracts import AuditError
from app.auth.service import AuthError
from fastapi import HTTPException

ADMIN_ID = 101


def _target(**over):
    base = {
        "id": 202,
        "uuid": "11111111-1111-1111-1111-111111111111",
        "email": "student@donnu.ru",
        "full_name": "Иванов Иван",
        "roles": ["student"],
        "role": "student",
        "is_active": True,
    }
    base.update(over)
    return base


# ── guard-набор impersonate_target ───────────────────────────────────────────

def test_impersonate_target_ok_returns_user(monkeypatch):
    monkeypatch.setattr(users_service, "get_user", lambda uuid: _target())
    out = users_service.impersonate_target("uuid", actor_id=ADMIN_ID)
    assert out["id"] == 202


def test_impersonate_target_self_rejected(monkeypatch):
    monkeypatch.setattr(
        users_service, "get_user", lambda uuid: _target(id=ADMIN_ID)
    )
    with pytest.raises(AuthError) as ei:
        users_service.impersonate_target("uuid", actor_id=ADMIN_ID)
    assert ei.value.status_code == 400


def test_impersonate_target_admin_rejected(monkeypatch):
    monkeypatch.setattr(
        users_service, "get_user",
        lambda uuid: _target(roles=["admin", "student"], role="admin"),
    )
    with pytest.raises(AuthError) as ei:
        users_service.impersonate_target("uuid", actor_id=ADMIN_ID)
    assert ei.value.status_code == 403


def test_impersonate_target_inactive_rejected(monkeypatch):
    monkeypatch.setattr(
        users_service, "get_user", lambda uuid: _target(is_active=False)
    )
    with pytest.raises(AuthError) as ei:
        users_service.impersonate_target("uuid", actor_id=ADMIN_ID)
    assert ei.value.status_code == 403


def test_impersonate_target_no_roles_rejected(monkeypatch):
    monkeypatch.setattr(
        users_service, "get_user", lambda uuid: _target(roles=[], role=None)
    )
    with pytest.raises(AuthError) as ei:
        users_service.impersonate_target("uuid", actor_id=ADMIN_ID)
    assert ei.value.status_code == 403


def test_impersonate_target_not_found_propagates(monkeypatch):
    def _raise(uuid):
        raise AuthError("Пользователь не найден", status_code=404)
    monkeypatch.setattr(users_service, "get_user", _raise)
    with pytest.raises(AuthError) as ei:
        users_service.impersonate_target("uuid", actor_id=ADMIN_ID)
    assert ei.value.status_code == 404


# ── route happy-path: сессия с impersonator_user_id + audit ──────────────────

def test_route_impersonate_creates_marked_session_and_audits(monkeypatch):
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers.get.return_value = "agent"
    current_user = {"id": str(ADMIN_ID), "roles": ["admin"], "role": "admin"}

    monkeypatch.setattr(
        routes_admin.service, "impersonate_target",
        lambda uuid, actor_id: _target(),
    )
    created = {}

    def _start(target_id, *, actor_id, ip, user_agent):
        created["user_id"] = target_id
        created["impersonator_user_id"] = actor_id
        return "raw-token", datetime.now(timezone.utc)

    # ADR-028: сессия выдаётся атомарно под блокировкой (service).
    monkeypatch.setattr(
        routes_admin.service, "start_impersonation_session", _start
    )

    with patch.object(routes_admin, "record_event") as rec:
        resp = routes_admin.impersonate_user(
            request, "uuid", current_user=current_user
        )

    # impersonator_user_id проставлен id администратора; сессия — целевого юзера
    assert created["impersonator_user_id"] == ADMIN_ID
    assert created["user_id"] == 202
    assert resp["session_token"] == "raw-token"
    assert resp["role"] == "student"
    assert resp["name"] == "Иванов Иван"

    # audit: admin_user_impersonated, target — целевой пользователь
    assert rec.call_count == 1
    kw = rec.call_args.kwargs
    assert kw["event"] == "admin_user_impersonated"
    assert kw["target"].entity_type == "user"
    assert kw["target"].entity_id == 202
    assert kw["actor"].user_id == ADMIN_ID


def test_route_impersonate_fail_closed_revokes_session_on_audit_error(monkeypatch):
    """RAISE: сбой аудита → сессия отозвана, 503, токен не отдан."""
    request = MagicMock()
    request.client.host = "10.0.0.1"
    request.headers.get.return_value = "agent"
    current_user = {"id": str(ADMIN_ID), "roles": ["admin"], "role": "admin"}

    monkeypatch.setattr(
        routes_admin.service, "impersonate_target",
        lambda uuid, actor_id: _target(),
    )
    monkeypatch.setattr(
        routes_admin.service, "start_impersonation_session",
        lambda target_id, **kw: ("raw-token", datetime.now(timezone.utc)),
    )
    revoked = {}
    monkeypatch.setattr(
        routes_admin.auth_service, "terminate_session",
        lambda tok: revoked.setdefault("tok", tok),
    )

    def _boom(**kw):
        raise AuditError("audit storage failure")
    monkeypatch.setattr(routes_admin, "record_event", _boom)

    with pytest.raises(HTTPException) as ei:
        routes_admin.impersonate_user(request, "uuid", current_user=current_user)

    assert ei.value.status_code == 503
    assert revoked["tok"] == "raw-token"  # созданная сессия отозвана


# ── ADR-028: авторитетная проверка под блокировкой (start_session_atomic) ────

def _capture_check(monkeypatch):
    """Подменяет storage: сохраняет check, переданный в start_session_atomic."""
    import app.auth.storage as auth_storage
    seen = {}

    def _fake(user_id, *, check, ip, user_agent, impersonator_user_id):
        seen.update(user_id=user_id, impersonator_user_id=impersonator_user_id)
        seen["check"] = check
        return "tok", datetime.now(timezone.utc), {}
    monkeypatch.setattr(auth_storage, "start_session_atomic", _fake)
    return seen


def _admin(**over):
    base = {"id": str(ADMIN_ID), "roles": ["admin", "student"],
            "role": "admin", "is_active": True, "name": "Админ"}
    base.update(over)
    return base


def test_start_impersonation_session_marks_admin_and_locks(monkeypatch):
    seen = _capture_check(monkeypatch)
    tok, _ = users_service.start_impersonation_session(202, actor_id=ADMIN_ID)
    assert tok == "tok"
    assert seen["user_id"] == 202 and seen["impersonator_user_id"] == ADMIN_ID
    seen["check"](_target(), _admin())          # валидная пара — не бросает


@pytest.mark.parametrize("admin", [
    None,                                         # инициатор удалён
    _admin(is_active=False),                      # инициатор отключён
    _admin(roles=["student"], role="student"),    # инициатор потерял admin
])
def test_impersonation_check_rejects_invalid_initiator(monkeypatch, admin):
    seen = _capture_check(monkeypatch)
    users_service.start_impersonation_session(202, actor_id=ADMIN_ID)
    with pytest.raises(AuthError) as ei:
        seen["check"](_target(), admin)
    assert ei.value.status_code == 403


@pytest.mark.parametrize("target,status", [
    (None, 404),                                  # цель удалена под блокировкой
    (_target(is_active=False), 403),              # цель отключена конкурентно
    (_target(roles=["admin"], role="admin"), 403),
])
def test_impersonation_check_rejects_target_changed_under_lock(
    monkeypatch, target, status,
):
    seen = _capture_check(monkeypatch)
    users_service.start_impersonation_session(202, actor_id=ADMIN_ID)
    with pytest.raises(AuthError) as ei:
        seen["check"](target, _admin())
    assert ei.value.status_code == status


def test_impersonation_target_null_is_active_is_active(monkeypatch):
    # Историческое is_active=NULL трактуется как активный (ADR-028).
    seen = _capture_check(monkeypatch)
    users_service.start_impersonation_session(202, actor_id=ADMIN_ID)
    seen["check"](_target(is_active=None), _admin())
