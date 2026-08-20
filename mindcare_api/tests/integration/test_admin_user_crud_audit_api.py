"""
Stage 4B-4 — gated integration: admin user CRUD (create/update/delete) через
record_event(). Запуск ТОЛЬКО через Stage 1 isolated runner; dev/prod
запрещены.

Проверяет:
  - create → ровно одна admin_user_created, entity_id == реальный User.id,
    metadata=={}, actor == вызывающий админ;
  - scalar-only update → ровно одна admin_user_updated, metadata=={};
  - role-only update → ровно одна admin_role_*, НЕТ admin_user_updated;
  - scalar+role update → обе строки в одной транзакции;
  - scalar/role no-op → новых audit-строк нет;
  - is_active переход state→same не пишет admin_user_updated;
  - delete → одна admin_user_deleted + отозванные UserSession;
  - повторный delete → 404 без новой success-строки;
  - auth_log не содержит legacy admin_create_user/admin_update_user/
    admin_delete_user/profile_update строк.
"""
import uuid as _uuid

from app.db.session import SessionLocal
from app.db.models import AuditLog, AuthLog, User, UserLegalBasisRecord, UserSession
from tests.integration.conftest import ALLOWED_TEST_DOMAIN, create_multi_role_user

BODY_OK = {
    "full_name": "Новый Сотрудник Тестович",
    "role": "psychologist",
    "legal_basis_confirmed": True,
    "basis_type": "employment",
    "basis_reference": "Приказ № 42-к",
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create(client, token, email, **overrides):
    body = {**BODY_OK, "email": email, **overrides}
    return client.post("/api/admin/users/", headers=_auth(token), json=body)


def _new_email(prefix="admincrud"):
    return f"integ_{prefix}_{_uuid.uuid4().hex[:10]}@{ALLOWED_TEST_DOMAIN}"


def _user_id_by_email(email):
    with SessionLocal() as db:
        row = db.query(User.id).filter(User.email == email).first()
        return row.id if row else None


def _audit_rows(event_type, entity_id, entity_type="user"):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == event_type,
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _legacy_auth_log_rows(prefix):
    with SessionLocal() as db:
        rows = (
            db.query(AuthLog)
            .filter(AuthLog.event.like(f"{prefix}%"))
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


# ── create ──────────────────────────────────────────────────────────────────

def test_create_writes_single_admin_user_created(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    email = _new_email()
    r = _create(client, token, email)
    assert r.status_code == 201, r.text
    # AdminUserCreateResponse не содержит id (только uuid) — резолвим напрямую.
    uid = _user_id_by_email(email)
    assert uid is not None

    rows = _audit_rows("admin_user_created", uid)
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == admin_id
    assert row.user_role == "admin"
    assert (row.log_metadata or {}) == {}
    assert row.description is None
    # Stage 4B-4 corrective pass: точный контракт success-события.
    assert row.outcome == "success"
    assert row.failure_reason_code is None

    # Никакого legacy admin_create_user:{uuid} в auth_log.
    assert _legacy_auth_log_rows("admin_create_user") == []


def test_create_without_legal_basis_confirmation_writes_nothing(client):
    token, _, _ = create_multi_role_user(client, ["admin"])
    email = _new_email()
    r = _create(client, token, email, legal_basis_confirmed=False)
    assert r.status_code == 422, r.text
    assert _user_id_by_email(email) is None


# ── update ──────────────────────────────────────────────────────────────────

def _make_staff_target(client, admin_token):
    email = _new_email("target")
    r = _create(client, admin_token, email)
    assert r.status_code == 201, r.text
    return _user_id_by_email(email)


def test_scalar_only_update_writes_single_admin_user_updated(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)

    r = client.patch(
        f"/api/admin/users/{_uuid_for(target_id)}",
        headers=_auth(token), json={"full_name": "Изменённое Имя"},
    )
    assert r.status_code == 200, r.text

    rows = _audit_rows("admin_user_updated", target_id)
    assert len(rows) == 1
    assert (rows[0].log_metadata or {}) == {}
    assert rows[0].user_id == admin_id
    assert _audit_rows("admin_role_add", target_id) == []
    assert _audit_rows("admin_role_update", target_id) == []


def test_scalar_no_op_writes_nothing(client):
    token, _, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    target_uuid = _uuid_for(target_id)

    client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token), json={"full_name": "Стабильное Имя"},
    )
    before = len(_audit_rows("admin_user_updated", target_id))

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token), json={"full_name": "Стабильное Имя"},
    )
    assert r.status_code == 200, r.text
    after = len(_audit_rows("admin_user_updated", target_id))
    assert after == before   # без изменений — новой строки нет


def test_is_active_same_value_writes_nothing(client):
    # Stage 5A-1: state→same не пишет ни generic, ни lifecycle события.
    token, _, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    target_uuid = _uuid_for(target_id)

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token), json={"is_active": True},   # уже True при создании
    )
    assert r.status_code == 200, r.text
    assert _audit_rows("admin_user_updated", target_id) == []
    assert _audit_rows("admin_user_activated", target_id) == []
    assert _audit_rows("admin_user_deactivated", target_id) == []


def _make_staff_target_with_session(client, admin_token):
    """Создаёт staff-пользователя и логинит его, чтобы появилась активная сессия
    (для проверки отзыва при деактивации)."""
    email = _new_email("target")
    r = _create(client, admin_token, email)
    assert r.status_code == 201, r.text
    temp_pw = r.json()["temporary_password"]
    uid = _user_id_by_email(email)
    lr = client.post("/api/auth/login", json={"email": email, "password": temp_pw})
    assert lr.status_code == 200, lr.text
    return uid


def _active_sessions(user_id):
    with SessionLocal() as db:
        return (
            db.query(UserSession)
            .filter(UserSession.user_id == user_id, ~UserSession.is_revoked)
            .count()
        )


def test_deactivate_writes_lifecycle_event_and_revokes_sessions(client):
    # Stage 5A-1: True→False → admin_user_deactivated + отзыв активных сессий.
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target_with_session(client, token)
    target_uuid = _uuid_for(target_id)
    assert _active_sessions(target_id) >= 1

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token), json={"is_active": False},
    )
    assert r.status_code == 200, r.text

    rows = _audit_rows("admin_user_deactivated", target_id)
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == admin_id and row.user_role == "admin"
    assert (row.log_metadata or {}) == {}
    assert row.outcome == "success"
    assert row.failure_reason_code is None
    assert row.description is None
    # is_active НЕ дублируется в admin_user_updated.
    assert _audit_rows("admin_user_updated", target_id) == []
    # Сессии отозваны в той же транзакции.
    assert _active_sessions(target_id) == 0


def test_activate_writes_lifecycle_event_no_extra_revoke(client):
    # Stage 5A-1: False→True → admin_user_activated; активация не отзывает сессии.
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    target_uuid = _uuid_for(target_id)

    client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token), json={"is_active": False},
    )
    before_deact = len(_audit_rows("admin_user_deactivated", target_id))

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token), json={"is_active": True},
    )
    assert r.status_code == 200, r.text

    act_rows = _audit_rows("admin_user_activated", target_id)
    assert len(act_rows) == 1
    assert act_rows[0].user_id == admin_id
    assert (act_rows[0].log_metadata or {}) == {}
    assert act_rows[0].outcome == "success"
    # Активация не пишет generic update и не добавляет deactivated.
    assert _audit_rows("admin_user_updated", target_id) == []
    assert len(_audit_rows("admin_user_deactivated", target_id)) == before_deact


def test_combined_scalar_is_active_role_writes_three_disjoint_events(client):
    # Combined PATCH: full_name + is_active(False) + добавление роли supervisor.
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)   # psychologist, active
    target_uuid = _uuid_for(target_id)

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token),
        json={
            "full_name": "Комбо Лайфцикл",
            "is_active": False,
            "roles": ["psychologist", "supervisor"],
            "legal_basis_confirmed": True,
            "basis_type": "employment",
            "basis_reference": "Приказ № 45-к",
        },
    )
    assert r.status_code == 200, r.text

    assert len(_audit_rows("admin_user_updated", target_id)) == 1
    assert len(_audit_rows("admin_user_deactivated", target_id)) == 1
    assert len(_audit_rows("admin_role_add", target_id)) == 1
    assert _audit_rows("admin_user_activated", target_id) == []


def test_role_only_update_writes_role_event_not_user_updated(client):
    token, _, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)   # psychologist
    target_uuid = _uuid_for(target_id)

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token),
        json={
            "roles": ["psychologist", "supervisor"],
            "legal_basis_confirmed": True,
            "basis_type": "employment",
            "basis_reference": "Приказ № 43-к",
        },
    )
    assert r.status_code == 200, r.text

    assert len(_audit_rows("admin_role_add", target_id)) == 1
    assert _audit_rows("admin_user_updated", target_id) == []


def test_scalar_and_role_update_writes_two_rows(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    target_uuid = _uuid_for(target_id)

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token),
        json={
            "full_name": "Комбо Обновление",
            "roles": ["psychologist", "supervisor"],
            "legal_basis_confirmed": True,
            "basis_type": "employment",
            "basis_reference": "Приказ № 44-к",
        },
    )
    assert r.status_code == 200, r.text

    updated_rows = _audit_rows("admin_user_updated", target_id)
    role_rows = _audit_rows("admin_role_add", target_id)
    assert len(updated_rows) == 1
    assert len(role_rows) == 1
    assert updated_rows[0].user_id == admin_id
    assert role_rows[0].user_id == admin_id
    # Stage 4B-4 corrective pass: точный контракт success-события для обеих строк.
    for row, expected_metadata_keys in (
        (updated_rows[0], set()),
        (role_rows[0], {"roles_before", "roles_after", "added", "removed"}),
    ):
        assert row.outcome == "success"
        assert row.failure_reason_code is None
        assert row.description is None
        assert set((row.log_metadata or {}).keys()) == expected_metadata_keys

    assert _legacy_auth_log_rows("admin_update_user") == []


def test_role_no_op_writes_nothing(client):
    # Настоящий role no-op: тот же набор ролей, что уже есть у пользователя.
    token, _, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)   # создан с ролью psychologist
    target_uuid = _uuid_for(target_id)

    r = client.patch(
        f"/api/admin/users/{target_uuid}",
        headers=_auth(token),
        json={"roles": ["psychologist"]},   # совпадает с текущим набором
    )
    assert r.status_code == 200, r.text

    assert _audit_rows("admin_user_updated", target_id) == []
    assert _audit_rows("admin_role_add", target_id) == []
    assert _audit_rows("admin_role_remove", target_id) == []
    assert _audit_rows("admin_role_update", target_id) == []


# Примечание: сценарий "scalar diff + несуществующая added-роль отклоняет весь
# PATCH атомарно" не воспроизводим через публичный API — Pydantic Literal на
# `role`/`roles[]` ограничивает значения реально существующими именами ролей,
# так что HTTP-запрос с несуществующей ролью получит 422 ещё на уровне схемы,
# до вызова storage. Прямая проверка этого пути (Role действительно отсутствует
# в БД под уже провалидированным именем) покрыта на уровне storage-unit:
# tests/test_admin_user_audit_unit.py::
#   test_scalar_real_diff_and_missing_added_role_rejects_before_any_mutation.


# ── delete ──────────────────────────────────────────────────────────────────

def test_delete_writes_single_admin_user_deleted_and_revokes_sessions(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    target_uuid = _uuid_for(target_id)

    r = client.delete(f"/api/admin/users/{target_uuid}", headers=_auth(token))
    assert r.status_code == 204, r.text

    rows = _audit_rows("admin_user_deleted", target_id)
    assert len(rows) == 1
    assert rows[0].user_id == admin_id
    assert (rows[0].log_metadata or {}) == {}
    # Stage 4B-4 corrective pass: точный контракт success-события.
    assert rows[0].outcome == "success"
    assert rows[0].failure_reason_code is None
    assert rows[0].description is None

    with SessionLocal() as db:
        active = (
            db.query(UserSession)
            .filter(UserSession.user_id == target_id, ~UserSession.is_revoked)
            .count()
        )
        assert active == 0

    assert _legacy_auth_log_rows("admin_delete_user") == []


def test_repeat_delete_returns_404_without_new_audit_row(client):
    token, _, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    target_uuid = _uuid_for(target_id)

    r1 = client.delete(f"/api/admin/users/{target_uuid}", headers=_auth(token))
    assert r1.status_code == 204, r1.text
    r2 = client.delete(f"/api/admin/users/{target_uuid}", headers=_auth(token))
    assert r2.status_code == 404, r2.text

    rows = _audit_rows("admin_user_deleted", target_id)
    assert len(rows) == 1   # повторный вызов не добавляет вторую строку


# ── malformed IP/UA sanitization (through the public API) ─────────────────────

def test_malformed_ip_and_user_agent_sanitized_to_null_everywhere(client):
    """
    request.client.host для стандартного `client`-фикстуры фиксирован как
    валидный "127.0.0.1" (см. conftest.py) — через него malformed IP
    невоспроизводим. Для этого одного сценария используем отдельный
    TestClient с недействительным client=("not-an-ip", ...), НЕ как context
    manager (без `with`) — это не запускает lifespan (init_db/seed/
    engine.dispose() на shutdown), поэтому не задевает session-scoped
    engine/`client`-фикстуру, используемую остальными тестами модуля.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    email = _new_email("badctx")
    huge_ua = "x" * 600   # превышает _UA_MAX_LEN=512 → санитизируется в None

    bad_client = TestClient(app, client=("not-an-ip", 12345))
    r = bad_client.post(
        "/api/admin/users/",
        headers={"Authorization": f"Bearer {token}", "User-Agent": huge_ua},
        json={**BODY_OK, "email": email},
    )
    assert r.status_code == 201, r.text   # не 500

    uid = _user_id_by_email(email)
    assert uid is not None

    audit_rows = _audit_rows("admin_user_created", uid)
    assert len(audit_rows) == 1
    audit_row = audit_rows[0]
    assert audit_row.user_id == admin_id   # actor mapping не сломан malformed context
    assert audit_row.ip_address is None
    assert audit_row.user_agent is None
    assert audit_row.outcome == "success"
    assert audit_row.failure_reason_code is None

    with SessionLocal() as db:
        basis_rows = (
            db.query(UserLegalBasisRecord)
            .filter(UserLegalBasisRecord.user_id == uid)
            .all()
        )
        assert len(basis_rows) == 1
        basis = basis_rows[0]
        # Единый sanitized context (Stage 4B-4): legal-basis запись получает
        # то же None, что и audit-строка — не raw "not-an-ip"/огромный UA.
        assert basis.ip_address is None
        assert basis.user_agent is None

        # Исходные malformed значения нигде не сохранены (ни в audit, ни в
        # legal basis, ни где-либо ещё в затронутых строках).
        blob = f"{audit_row.log_metadata} {basis.comment} {basis.basis_reference}"
        assert "not-an-ip" not in blob
        assert huge_ua not in blob


def _uuid_for(user_id):
    with SessionLocal() as db:
        row = db.query(User.uuid).filter(User.id == user_id).first()
        return str(row.uuid)


# ─── Stage 5A-2: durable best-effort failure events ───────────────────────────

def _failure_rows(event_type, actor_id):
    """*_failed AuditLog-строки для actor, детерминированно упорядоченные."""
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == event_type,
                AuditLog.user_id == actor_id,
                AuditLog.outcome == "failure",
            )
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _assert_failure_contract(row, actor_id, code):
    assert row.outcome == "failure"
    assert row.failure_reason_code == code
    assert row.user_id == actor_id and row.user_role == "admin"
    assert row.entity_type is None and row.entity_id is None   # target FORBIDDEN
    assert (row.log_metadata or {}) == {}
    assert row.description is None


def test_create_duplicate_active_email_writes_create_failed(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    email = _new_email("dupactive")
    assert _create(client, token, email).status_code == 201

    before = len(_failure_rows("admin_user_create_failed", admin_id))
    r = _create(client, token, email)
    assert r.status_code == 409, r.text
    # email не раскрывается в теле как «существует у X» — только generic 409
    rows = _failure_rows("admin_user_create_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "email_already_exists")


def test_create_duplicate_soft_deleted_email_writes_create_failed(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    email = _new_email("dupsoft")
    assert _create(client, token, email).status_code == 201
    uid = _user_id_by_email(email)
    # soft-delete → email всё ещё в users (deleted_at IS NOT NULL)
    assert client.delete(
        f"/api/admin/users/{_uuid_for(uid)}", headers=_auth(token),
    ).status_code == 204

    before = len(_failure_rows("admin_user_create_failed", admin_id))
    r = _create(client, token, email)   # повторное создание того же email
    assert r.status_code == 409, r.text
    rows = _failure_rows("admin_user_create_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "email_already_exists")
    # второй User НЕ создан: та же строка (soft-deleted) остаётся
    with SessionLocal() as db:
        cnt = db.query(User).filter(
            User.email == email.strip().lower(),
        ).count()
        assert cnt == 1


def test_update_not_found_writes_update_failed(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    before = len(_failure_rows("admin_user_update_failed", admin_id))
    r = client.patch(
        f"/api/admin/users/{_uuid.uuid4()}",   # валидный uuid, нет User
        headers=_auth(token), json={"full_name": "Никого Нет"},
    )
    assert r.status_code == 404, r.text
    rows = _failure_rows("admin_user_update_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "user_not_found")


def test_update_malformed_uuid_writes_invalid_request(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    before = len(_failure_rows("admin_user_update_failed", admin_id))
    r = client.patch(
        "/api/admin/users/not-a-uuid",
        headers=_auth(token), json={"full_name": "Кривой UUID"},
    )
    assert r.status_code == 400, r.text
    rows = _failure_rows("admin_user_update_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "invalid_request")


def test_update_empty_patch_writes_invalid_request(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)
    before = len(_failure_rows("admin_user_update_failed", admin_id))
    r = client.patch(
        f"/api/admin/users/{_uuid_for(target_id)}",
        headers=_auth(token), json={},
    )
    assert r.status_code == 400, r.text
    rows = _failure_rows("admin_user_update_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "invalid_request")


def test_update_self_admin_writes_self_admin_protected(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    before = len(_failure_rows("admin_user_update_failed", admin_id))
    r = client.patch(
        f"/api/admin/users/{_uuid_for(admin_id)}",
        headers=_auth(token), json={"roles": []},   # снять свою admin-роль
    )
    assert r.status_code == 422, r.text
    rows = _failure_rows("admin_user_update_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "self_admin_protected")


def test_update_role_policy_writes_role_policy_violation(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)   # psychologist-only
    before = len(_failure_rows("admin_user_update_failed", admin_id))
    r = client.patch(
        f"/api/admin/users/{_uuid_for(target_id)}",
        headers=_auth(token), json={"roles": []},   # без активных ролей
    )
    assert r.status_code == 422, r.text
    rows = _failure_rows("admin_user_update_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "role_policy_violation")


def test_update_missing_legal_basis_writes_legal_basis_required(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    target_id = _make_staff_target(client, token)   # psychologist
    before = len(_failure_rows("admin_user_update_failed", admin_id))
    r = client.patch(
        f"/api/admin/users/{_uuid_for(target_id)}",
        headers=_auth(token),
        json={"roles": ["psychologist", "supervisor"]},   # без legal basis
    )
    assert r.status_code == 400, r.text
    rows = _failure_rows("admin_user_update_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "legal_basis_required")


def test_delete_not_found_writes_delete_failed(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    before = len(_failure_rows("admin_user_delete_failed", admin_id))
    r = client.delete(
        f"/api/admin/users/{_uuid.uuid4()}", headers=_auth(token),
    )
    assert r.status_code == 404, r.text
    rows = _failure_rows("admin_user_delete_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "user_not_found")


def test_delete_malformed_uuid_writes_user_not_found(client):
    # DELETE malformed UUID → сохранённый контракт 404 / user_not_found.
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    before = len(_failure_rows("admin_user_delete_failed", admin_id))
    r = client.delete("/api/admin/users/not-a-uuid", headers=_auth(token))
    assert r.status_code == 404, r.text
    rows = _failure_rows("admin_user_delete_failed", admin_id)
    assert len(rows) == before + 1
    _assert_failure_contract(rows[-1], admin_id, "user_not_found")


def test_failure_rows_contain_no_pii(client):
    token, admin_id, _ = create_multi_role_user(client, ["admin"])
    email = _new_email("nopii")
    assert _create(client, token, email).status_code == 201
    _create(client, token, email)   # duplicate → create_failed

    import json as _json
    for row in _failure_rows("admin_user_create_failed", admin_id):
        blob = (row.description or "") + _json.dumps(
            row.log_metadata or {}, ensure_ascii=False,
        ) + (row.request_url or "")
        assert email not in blob
        assert "email_already_exists" == row.failure_reason_code  # только код
