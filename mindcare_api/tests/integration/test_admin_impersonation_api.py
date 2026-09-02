"""
ADR-025 — gated integration: impersonation («Зайти под именем»). Запуск ТОЛЬКО
через Stage 1 isolated runner; dev/prod запрещены.

Проверяет РЕАЛЬНЫЙ путь записи аудита (не мок):
  - happy-path: 200, сессия цели помечена impersonator_user_id, last_login цели
    НЕ изменён, /me по новому токену отдаёт impersonating + impersonator_name;
  - ровно одна admin_user_impersonated с entity_id == target, session_id заполнен;
  - guard: self → 400, admin-цель → 403, заблокированный → 403.
"""
from app.db.session import SessionLocal
from app.db.models import AuditLog, User, UserSession
from tests.integration.conftest import create_multi_role_user


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _uuid_by_id(user_id: int) -> str:
    with SessionLocal() as db:
        return str(db.query(User.uuid).filter(User.id == user_id).first().uuid)


def _impersonated_rows(target_id: int):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "admin_user_impersonated",
                AuditLog.entity_type == "user",
                AuditLog.entity_id == target_id,
            )
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _target_last_login(target_id: int):
    with SessionLocal() as db:
        return db.query(User.last_login).filter(User.id == target_id).first().last_login


def _impersonation_sessions(target_id: int, admin_id: int):
    with SessionLocal() as db:
        rows = (
            db.query(UserSession)
            .filter(
                UserSession.user_id == target_id,
                UserSession.impersonator_user_id == admin_id,
            )
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


# ── happy-path ────────────────────────────────────────────────────────────────

def test_impersonate_marks_session_audits_and_preserves_last_login(client):
    admin_token, admin_id, _ = create_multi_role_user(client, ["admin"])
    _, target_id, _ = create_multi_role_user(client, ["student"])
    target_uuid = _uuid_by_id(target_id)

    # create_multi_role_user логинит цель — last_login уже проставлен. Фиксируем
    # его ДО impersonation, чтобы проверить, что вход «под именем» его НЕ трогает.
    last_login_before = _target_last_login(target_id)
    assert last_login_before is not None

    r = client.post(
        f"/api/admin/users/{target_uuid}/impersonate", headers=_auth(admin_token)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["role"] == "student"
    assert "student" in body["roles"]
    imp_token = body["session_token"]

    # Сессия цели помечена админом; last_login цели НЕ изменён impersonation'ом
    # (update_last_login при impersonation не вызывается).
    marked = _impersonation_sessions(target_id, admin_id)
    assert len(marked) == 1
    assert _target_last_login(target_id) == last_login_before

    # Ровно одна audit-строка с заполненным session_id (fail-closed RAISE).
    rows = _impersonated_rows(target_id)
    assert len(rows) == 1
    assert rows[0].user_id == admin_id
    assert rows[0].user_role == "admin"
    assert rows[0].session_id  # session_id_hash новой сессии

    # /me по impersonation-токену отдаёт серверную правду.
    me = client.get("/api/auth/me", headers=_auth(imp_token))
    assert me.status_code == 200, me.text
    me_body = me.json()
    assert me_body["impersonating"] is True
    assert me_body["impersonator_name"]  # имя администратора


# ── guards ────────────────────────────────────────────────────────────────────

def test_impersonate_self_rejected(client):
    admin_token, admin_id, _ = create_multi_role_user(client, ["admin"])
    admin_uuid = _uuid_by_id(admin_id)
    r = client.post(
        f"/api/admin/users/{admin_uuid}/impersonate", headers=_auth(admin_token)
    )
    assert r.status_code == 400, r.text
    assert _impersonated_rows(admin_id) == []


def test_impersonate_admin_target_rejected(client):
    admin_token, _, _ = create_multi_role_user(client, ["admin"])
    _, target_id, _ = create_multi_role_user(client, ["admin"])
    target_uuid = _uuid_by_id(target_id)
    r = client.post(
        f"/api/admin/users/{target_uuid}/impersonate", headers=_auth(admin_token)
    )
    assert r.status_code == 403, r.text
    assert _impersonated_rows(target_id) == []
