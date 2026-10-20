"""
Stage 5C-2 — gated integration: audit trail групповых занятий и регистраций.

Запуск ТОЛЬКО через Stage 1 isolated runner (scripts/isolated_test_db.py) при
безопасном TEST_DATABASE_URL; dev/prod запрещены.

Проверяет 7 success-событий: group_session created/updated/booking_opened/
booking_closed/cancelled (supervisor+admin) и group_session_registered/
registration_cancelled (student). Полный success-контракт каждой строки,
target регистрации = внутренний integer id (не UUID), реактивация
cancelled→registered переиспользует тот же id, no-op/идемпотентность,
transition-контракт status (manual completed и cancelled→scheduled отвергаются
без записи событий), отсутствие названий/описаний в audit. Append-only журналы
НЕ очищаются — уникальные entity id и before/after counts.
"""
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, GroupSession, GroupSessionRegistration, MeetingType, Role,
    UserRole,
)

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))
GS_URL = "/api/supervisor/group-sessions"
STUDENT_GS_URL = "/api/group-sessions"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_grp_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"GrpTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login",
                    json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


def _group_meeting_type():
    with SessionLocal() as db:
        mt = MeetingType(
            name=f"integ_grp_type_{_uuid.uuid4().hex[:6]}", duration_minutes=60,
            buffer_minutes=0, allow_in_person=False, allow_online=True,
            is_group=True, is_active=True, is_bookable=True, display_order=0,
        )
        db.add(mt)
        db.commit()
        return mt.id


def _rows(event_type, entity_id):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type,
                    AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _assert_success(row, entity_type, entity_id, actor_id, actor_role):
    assert row.entity_type == entity_type
    assert row.entity_id == entity_id
    assert row.outcome == "success"
    assert row.failure_reason_code is None
    assert row.description is None
    assert (row.log_metadata or {}) == {}
    assert row.user_id == actor_id
    assert row.user_role == actor_role


def _gs_id(gs_uuid: str) -> int:
    with SessionLocal() as db:
        return db.query(GroupSession.id).filter(
            GroupSession.uuid == gs_uuid).scalar()


def _registration_id(gs_uuid: str, student_id: int) -> int:
    with SessionLocal() as db:
        gs_id = db.query(GroupSession.id).filter(
            GroupSession.uuid == gs_uuid).scalar()
        return db.query(GroupSessionRegistration.id).filter(
            GroupSessionRegistration.group_session_id == gs_id,
            GroupSessionRegistration.student_id == student_id).scalar()


def _future(hours=72):
    return (datetime.now(MOSCOW_TZ) + timedelta(hours=hours)).replace(
        minute=0, second=0, microsecond=0)


def _create_gs(client, tok, mt_id, psych_id, **over):
    payload = {
        "meeting_type_id": mt_id,
        "psychologist_id": psych_id,
        "title": f"grp_{_uuid.uuid4().hex[:8]}",
        "starts_at": _future().isoformat(),
        "format": "online",
        "capacity": 10,
        "booking_enabled": True,
    }
    payload.update(over)
    return client.post(GS_URL, json=payload, headers=_auth(tok))


# ─── GroupSession lifecycle (supervisor / admin) ──────────────────────────────

def test_group_session_created_and_updated(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()

    secret = f"SECRETTITLE_{_uuid.uuid4().hex}"
    r = _create_gs(client, tok, mt_id, psych, title=secret)
    assert r.status_code == 201, r.text
    gs_uuid = r.json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    rows = _rows("group_session_created", gs_id)
    assert len(rows) == 1
    _assert_success(rows[0], "group_session", gs_id, sup_id, "supervisor")
    import json as _json
    blob = (rows[0].description or "") + _json.dumps(
        rows[0].log_metadata or {}, ensure_ascii=False)
    assert secret not in blob            # название не в audit

    # реальный diff обычного поля → ровно один generic updated
    assert client.patch(f"{GS_URL}/{gs_uuid}", json={"capacity": 20},
                        headers=_auth(tok)).status_code == 200
    urows = _rows("group_session_updated", gs_id)
    assert len(urows) == 1
    _assert_success(urows[0], "group_session", gs_id, sup_id, "supervisor")


def test_group_session_identical_patch_is_noop(client):
    tok, _ = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych,
                         capacity=10).json()["uuid"]
    gs_id = _gs_id(gs_uuid)
    before = len(_rows("group_session_updated", gs_id))

    assert client.patch(f"{GS_URL}/{gs_uuid}", json={"capacity": 10},
                        headers=_auth(tok)).status_code == 200
    assert client.patch(f"{GS_URL}/{gs_uuid}", json={},
                        headers=_auth(tok)).status_code == 200
    assert len(_rows("group_session_updated", gs_id)) == before


def test_booking_transitions_without_generic_updated(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych,
                         booking_enabled=True).json()["uuid"]
    gs_id = _gs_id(gs_uuid)
    upd_before = len(_rows("group_session_updated", gs_id))

    # dedicated booking endpoint: закрыть
    assert client.patch(f"{GS_URL}/{gs_uuid}/booking?enabled=false",
                        headers=_auth(tok)).status_code == 200
    crows = _rows("group_session_booking_closed", gs_id)
    assert len(crows) == 1
    _assert_success(crows[0], "group_session", gs_id, sup_id, "supervisor")
    # generic updated НЕ появился
    assert len(_rows("group_session_updated", gs_id)) == upd_before

    # повторное закрытие — no-op
    assert client.patch(f"{GS_URL}/{gs_uuid}/booking?enabled=false",
                        headers=_auth(tok)).status_code == 200
    assert len(_rows("group_session_booking_closed", gs_id)) == 1

    # открыть обратно
    assert client.patch(f"{GS_URL}/{gs_uuid}/booking?enabled=true",
                        headers=_auth(tok)).status_code == 200
    orows = _rows("group_session_booking_opened", gs_id)
    assert len(orows) == 1
    _assert_success(orows[0], "group_session", gs_id, sup_id, "supervisor")


def test_group_session_cancelled_transition(client):
    tok, sup_id = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych).json()["uuid"]
    gs_id = _gs_id(gs_uuid)
    upd_before = len(_rows("group_session_updated", gs_id))

    assert client.patch(f"{GS_URL}/{gs_uuid}", json={"status": "cancelled"},
                        headers=_auth(tok)).status_code == 200
    rows = _rows("group_session_cancelled", gs_id)
    assert len(rows) == 1
    _assert_success(rows[0], "group_session", gs_id, sup_id, "supervisor")
    # status не тонет в generic updated
    assert len(_rows("group_session_updated", gs_id)) == upd_before


def test_manual_completed_rejected_without_audit(client):
    """`completed` принадлежит system maintenance — 422 и 0 событий."""
    tok, _ = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych).json()["uuid"]
    gs_id = _gs_id(gs_uuid)

    with SessionLocal() as db:
        before = db.query(AuditLog).filter(
            AuditLog.entity_id == gs_id,
            AuditLog.entity_type == "group_session").count()

    r = client.patch(f"{GS_URL}/{gs_uuid}", json={"status": "completed"},
                     headers=_auth(tok))
    assert r.status_code == 422, r.text     # отвергается схемой (enum)

    with SessionLocal() as db:
        assert db.query(AuditLog).filter(
            AuditLog.entity_id == gs_id,
            AuditLog.entity_type == "group_session").count() == before
        # статус не изменён
        assert db.query(GroupSession.status).filter(
            GroupSession.id == gs_id).scalar() == "scheduled"


def test_cancelled_to_scheduled_rejected_without_audit(client):
    """Восстановление требует отдельного события — 422 и 0 новых строк."""
    tok, _ = _make_user(client, "supervisor")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok, mt_id, psych).json()["uuid"]
    gs_id = _gs_id(gs_uuid)
    assert client.patch(f"{GS_URL}/{gs_uuid}", json={"status": "cancelled"},
                        headers=_auth(tok)).status_code == 200

    with SessionLocal() as db:
        before = db.query(AuditLog).filter(
            AuditLog.entity_id == gs_id,
            AuditLog.entity_type == "group_session").count()

    r = client.patch(f"{GS_URL}/{gs_uuid}", json={"status": "scheduled"},
                     headers=_auth(tok))
    assert r.status_code == 422, r.text

    with SessionLocal() as db:
        assert db.query(AuditLog).filter(
            AuditLog.entity_id == gs_id,
            AuditLog.entity_type == "group_session").count() == before
        assert db.query(GroupSession.status).filter(
            GroupSession.id == gs_id).scalar() == "cancelled"


def test_admin_actor_role_is_admin(client):
    tok, admin_id = _make_user(client, "admin")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    r = _create_gs(client, tok, mt_id, psych)
    assert r.status_code == 201, r.text
    gs_id = _gs_id(r.json()["uuid"])
    rows = _rows("group_session_created", gs_id)
    assert len(rows) == 1
    _assert_success(rows[0], "group_session", gs_id, admin_id, "admin")


def test_admin_and_supervisor_resolves_to_supervisor(client):
    tok, uid = _make_user(client, "supervisor")
    with SessionLocal() as db:
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        db.add(UserRole(user_id=uid, role_id=admin_role.id))
        db.commit()
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_id = _gs_id(_create_gs(client, tok, mt_id, psych).json()["uuid"])
    rows = _rows("group_session_created", gs_id)
    assert len(rows) == 1
    _assert_success(rows[0], "group_session", gs_id, uid, "supervisor")


# ─── Student registrations ────────────────────────────────────────────────────

def test_student_register_and_cancel_use_integer_registration_id(client):
    tok_sup, _ = _make_user(client, "supervisor")
    tok_stu, student_id = _make_user(client, "student")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok_sup, mt_id, psych).json()["uuid"]

    r = client.post(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                    headers=_auth(tok_stu))
    assert r.status_code == 201, r.text
    reg_id = _registration_id(gs_uuid, student_id)

    rows = _rows("group_session_registered", reg_id)
    assert len(rows) == 1
    _assert_success(rows[0], "group_session_registration", reg_id,
                    student_id, "student")
    assert isinstance(rows[0].entity_id, int)
    # публичный DTO не отдаёт внутренний id
    assert "id" not in r.json()

    # отмена
    assert client.delete(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                         headers=_auth(tok_stu)).status_code == 204
    crows = _rows("group_session_registration_cancelled", reg_id)
    assert len(crows) == 1
    _assert_success(crows[0], "group_session_registration", reg_id,
                    student_id, "student")


def test_reactivation_reuses_same_registration_id(client):
    """register → cancel → register переиспользует ТУ ЖЕ строку и target."""
    tok_sup, _ = _make_user(client, "supervisor")
    tok_stu, student_id = _make_user(client, "student")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok_sup, mt_id, psych).json()["uuid"]

    assert client.post(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                       headers=_auth(tok_stu)).status_code == 201
    reg_id = _registration_id(gs_uuid, student_id)
    assert client.delete(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                         headers=_auth(tok_stu)).status_code == 204
    assert client.post(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                       headers=_auth(tok_stu)).status_code == 201

    assert _registration_id(gs_uuid, student_id) == reg_id   # тот же id
    assert len(_rows("group_session_registered", reg_id)) == 2
    assert len(_rows("group_session_registration_cancelled", reg_id)) == 1


def test_cancel_without_registration_writes_no_event(client):
    tok_sup, _ = _make_user(client, "supervisor")
    tok_stu, student_id = _make_user(client, "student")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok_sup, mt_id, psych).json()["uuid"]

    with SessionLocal() as db:
        before = db.query(AuditLog).filter(
            AuditLog.event_type == "group_session_registration_cancelled",
        ).count()

    r = client.delete(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                      headers=_auth(tok_stu))
    assert r.status_code == 404, r.text

    with SessionLocal() as db:
        assert db.query(AuditLog).filter(
            AuditLog.event_type == "group_session_registration_cancelled",
        ).count() == before


def test_duplicate_registration_writes_no_second_event(client):
    tok_sup, _ = _make_user(client, "supervisor")
    tok_stu, student_id = _make_user(client, "student")
    psych = _make_user(client, "psychologist")[1]
    mt_id = _group_meeting_type()
    gs_uuid = _create_gs(client, tok_sup, mt_id, psych).json()["uuid"]

    assert client.post(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                       headers=_auth(tok_stu)).status_code == 201
    reg_id = _registration_id(gs_uuid, student_id)

    # повторная регистрация → 409, без второй строки
    r = client.post(f"{STUDENT_GS_URL}/{gs_uuid}/register",
                    headers=_auth(tok_stu))
    assert r.status_code == 409, r.text
    assert len(_rows("group_session_registered", reg_id)) == 1
