"""
Integration regression: actor/target semantics role-change audit (Stage 3).

Проверяет, что AuditLog role-событий пишет ДЕЙСТВУЮЩЕГО администратора в user_id
(actor), а target — в entity_type/entity_id. До Stage 3 в user_id ошибочно попадал
target. Только синтетические уникальные данные (prefix integ_).

Требует ТОЛЬКО disposable PostgreSQL на alembic head, поднятый ТОЛЬКО через Stage 1
isolated runner (scripts/isolated_test_db.py). Dev/prod БД использовать нельзя.
"""
import uuid as _uuid

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import AuditLog, User
from tests.integration.conftest import add_user_role

PASSWORD = "SecurePass42!"
ROLE_EVENTS = ("admin_role_add", "admin_role_remove", "admin_role_update")
ALLOWED_ROLES = {"student", "psychologist", "supervisor", "admin"}

BASIS_OK = {
    "legal_basis_confirmed": True,
    "basis_type": "administrative_order",
    "basis_reference": "integ synthetic order",
    "legal_basis_comment": "stage3 actor/target regression",
}


def _hash() -> str:
    return bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()


def _make_admin(client) -> tuple[str, int]:
    admin = auth_storage.save_user({
        "name": "Integ Actor Admin",
        "email": f"integ_actor_admin_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _hash(),
        "role": "admin",
    })
    r = client.post(
        "/api/auth/login",
        json={"email": admin["email"], "password": PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(admin["id"])


def _make_user(role: str, extra_roles: list[str] | None = None) -> tuple[str, int]:
    u = auth_storage.save_user({
        "name": f"Integ Actor {role} {_uuid.uuid4().hex[:6]}",
        "email": f"integ_actor_{role}_{_uuid.uuid4().hex[:10]}@example.com",
        "hashed_password": _hash(),
        "role": role,
    })
    uid = int(u["id"])
    for r in (extra_roles or []):
        add_user_role(uid, r)
    return _uuid_for_id(uid), uid


def _uuid_for_id(user_id: int) -> str:
    with SessionLocal() as db:
        return str(db.query(User.uuid).filter(User.id == user_id).scalar())


def _patch(client, token: str, uuid: str, body: dict):
    return client.patch(
        f"/api/admin/users/{uuid}",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )


def _role_events(
    target_id: int,
    event_type: str | None = None,
    outcome: str | None = "success",
) -> list:
    """Role-события по target (entity_type/entity_id).

    По умолчанию outcome="success" — иначе будущая Stage 5A failure-запись (у
    отклонённой операции) ошибочно засчиталась бы этим тестом как success-аудит.
    outcome=None снимает фильтр и возвращает события любого исхода.
    """
    with SessionLocal() as db:
        q = db.query(AuditLog).filter(
            AuditLog.entity_type == "user",
            AuditLog.entity_id == target_id,
            AuditLog.event_type.in_(ROLE_EVENTS),
        )
        if event_type is not None:
            q = q.filter(AuditLog.event_type == event_type)
        if outcome is not None:
            q = q.filter(AuditLog.outcome == outcome)
        rows = q.all()
        for r in rows:
            db.expunge(r)
        return rows


def _assert_actor_target(event, *, actor_id: int, target_id: int, same: bool):
    assert event.user_id == actor_id                 # actor
    assert event.entity_type == "user"
    assert event.entity_id == target_id              # target
    if same:
        assert event.user_id == event.entity_id      # actor==target — один юзер
    else:
        assert event.user_id != target_id            # actor != target
    assert event.user_role == "admin"
    assert event.outcome == "success"                # Stage 2 default
    keys = set(event.log_metadata.keys())
    assert keys == {"roles_before", "roles_after", "added", "removed"}
    for k in keys:
        for role in event.log_metadata[k]:
            assert role in ALLOWED_ROLES


# ── A. admin_role_add, actor != target ───────────────────────────────────────

def test_role_add_writes_actor_not_target(client):
    token, admin_id = _make_admin(client)
    uuid, target_id = _make_user("psychologist")
    assert admin_id != target_id

    r = _patch(client, token, uuid, {
        "roles": ["psychologist", "supervisor"], **BASIS_OK,
    })
    assert r.status_code == 200, r.text

    events = _role_events(target_id, "admin_role_add")
    assert len(events) == 1
    _assert_actor_target(
        events[0], actor_id=admin_id, target_id=target_id, same=False,
    )
    assert events[0].log_metadata["added"] == ["supervisor"]


# ── B. admin_role_remove, actor != target ────────────────────────────────────

def test_role_remove_writes_actor_not_target(client):
    token, admin_id = _make_admin(client)
    uuid, target_id = _make_user("psychologist", extra_roles=["supervisor"])
    assert admin_id != target_id

    r = _patch(client, token, uuid, {"roles": ["psychologist"]})
    assert r.status_code == 200, r.text

    events = _role_events(target_id, "admin_role_remove")
    assert len(events) == 1
    _assert_actor_target(
        events[0], actor_id=admin_id, target_id=target_id, same=False,
    )
    assert events[0].log_metadata["removed"] == ["supervisor"]


# ── C. self add-role: actor == target, admin сохранён ────────────────────────

def test_self_add_role_actor_equals_target(client):
    token, admin_id = _make_admin(client)
    admin_uuid = _uuid_for_id(admin_id)

    r = _patch(client, token, admin_uuid, {
        "roles": ["admin", "supervisor"], **BASIS_OK,
    })
    assert r.status_code == 200, r.text

    events = _role_events(admin_id, "admin_role_add")
    assert len(events) == 1
    # actor==target — равенство user_id==entity_id корректно, а не смешение полей.
    _assert_actor_target(
        events[0], actor_id=admin_id, target_id=admin_id, same=True,
    )
    assert events[0].log_metadata["added"] == ["supervisor"]


# ── D. rejected self-admin removal → нет нового success role-события ──────────

def test_rejected_self_admin_removal_writes_no_event(client):
    token, admin_id = _make_admin(client)
    add_user_role(admin_id, "supervisor")   # запасная роль (прямой insert, без audit)
    admin_uuid = _uuid_for_id(admin_id)

    before = len(_role_events(admin_id))     # append-only: не требуем абсолютного 0

    r = _patch(client, token, admin_uuid, {"roles": ["supervisor"]})  # снять admin
    assert r.status_code == 422, r.text

    after = len(_role_events(admin_id))
    assert after == before                   # отклонённая операция не пишет success


# ── E. admin_role_update (add+remove в одном PATCH) ──────────────────────────

def test_role_update_writes_actor_not_target(client):
    token, admin_id = _make_admin(client)
    uuid, target_id = _make_user("psychologist", extra_roles=["supervisor"])
    assert admin_id != target_id

    # снять supervisor, добавить admin (added → нужен legal basis) в одном PATCH
    r = _patch(client, token, uuid, {
        "roles": ["psychologist", "admin"], **BASIS_OK,
    })
    assert r.status_code == 200, r.text

    events = _role_events(target_id, "admin_role_update")
    assert len(events) == 1
    _assert_actor_target(
        events[0], actor_id=admin_id, target_id=target_id, same=False,
    )
    assert events[0].log_metadata["added"] == ["admin"]
    assert events[0].log_metadata["removed"] == ["supervisor"]
