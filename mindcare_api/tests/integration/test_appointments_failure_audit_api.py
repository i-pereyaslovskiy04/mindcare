"""
Stage 5B-2 — gated integration: durable best-effort failure audit для individual
appointments и walk-in cards. Запуск ТОЛЬКО через Stage 1 isolated runner
(scripts/isolated_test_db.py) при безопасном TEST_DATABASE_URL; dev/prod запрещены.

Проверяет 5 failure-событий (appointment_create/cancel/confirm/decline_failed +
unregistered_student_card_create_failed): точный actor + failure_reason_code,
outcome=failure, entity_type/entity_id отсутствуют, metadata={}, description=None,
отсутствие success-события и business-мутации, negative control (неаудируемый
отказ → 0 строк), отсутствие ПДн.

Requires: PostgreSQL on alembic head, DATA_ENCRYPTION_KEY, seeded roles/consents.
"""
import uuid as _uuid
from datetime import date, datetime, time, timedelta, timezone

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, Appointment, MeetingType, ScheduleRule, TherapyEngagement,
    UnregisteredStudentCard, User,
)

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))
CARDS_URL = "/api/supervisor/unregistered-student-cards"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role, *, domain="example.com"):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_fa_{role}_{suffix}@{domain}"
    user = auth_storage.save_user({
        "name": f"FaTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()).decode(),
        "role": role,
    })
    r = client.post("/api/auth/login",
                    json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"]), email


def _make_engagement(client_id, psychologist_id):
    with SessionLocal() as db:
        eng = TherapyEngagement(client_id=client_id,
                                psychologist_id=psychologist_id,
                                status="active")
        db.add(eng)
        db.commit()


def _setup_schedule(client):
    tok_p, pid, _ = _make_user(client, "psychologist")
    with SessionLocal() as db:
        mt = MeetingType(
            name=f"integ_fa_type_{_uuid.uuid4().hex[:6]}", duration_minutes=50,
            buffer_minutes=10, allow_in_person=True, allow_online=True,
            is_group=False, is_active=True, is_bookable=True, display_order=0,
        )
        db.add(mt)
        db.flush()
        mt_id = mt.id
        for dow in range(7):
            db.add(ScheduleRule(
                psychologist_id=pid, day_of_week=dow, start_time=time(0, 0),
                end_time=time(23, 59), meeting_type_id=mt_id,
                effective_from=date(2020, 1, 1), is_active=True,
            ))
        db.commit()
    return tok_p, pid, mt_id


def _future_slot(hours=40.0):
    msk = datetime.now(MOSCOW_TZ) + timedelta(hours=hours)
    return msk.replace(minute=0, second=0, microsecond=0)


def _book(client, tok_s, mt_id, slot):
    return client.post("/api/appointments", json={
        "starts_at": slot.isoformat(), "modality": "in_person",
        "meeting_type_id": mt_id,
    }, headers=_auth(tok_s))


def _fail_rows(event_type, user_id):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type,
                    AuditLog.user_id == user_id,
                    AuditLog.outcome == "failure")
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _assert_failure(row, actor_id, actor_role, code):
    assert row.outcome == "failure"
    assert row.failure_reason_code == code
    assert row.user_id == actor_id and row.user_role == actor_role
    assert row.entity_type is None and row.entity_id is None
    assert (row.log_metadata or {}) == {}
    assert row.description is None


def _appt_count(client_id):
    with SessionLocal() as db:
        return (
            db.query(Appointment)
            .filter(Appointment.client_id == client_id).count()
        )


# ─── appointment_create_failed ────────────────────────────────────────────────

def test_book_without_engagement_writes_engagement_required(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")   # без engagement
    before = _appt_count(sid)
    r = _book(client, tok_s, mt_id, _future_slot(40))
    assert r.status_code == 403, r.text
    rows = _fail_rows("appointment_create_failed", sid)
    assert len(rows) == 1
    _assert_failure(rows[0], sid, "student", "engagement_required")
    assert _appt_count(sid) == before          # business-мутации нет
    # success-события нет
    with SessionLocal() as db:
        assert db.query(AuditLog).filter(
            AuditLog.event_type == "appointment_created",
            AuditLog.user_id == sid).count() == 0


def test_book_inactive_account_writes_account_inactive(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    with SessionLocal() as db:
        db.query(User).filter(User.id == sid).update({"is_active": False})
        db.commit()
    r = _book(client, tok_s, mt_id, _future_slot(42))
    assert r.status_code == 403, r.text
    rows = _fail_rows("appointment_create_failed", sid)
    assert len(rows) == 1
    _assert_failure(rows[0], sid, "student", "account_inactive")


def test_supervisor_book_unlinked_writes_engagement_required(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")   # НЕ закреплён за pid
    tok_sv, sup_id, _ = _make_user(client, "supervisor")
    r = client.post("/api/supervisor/appointments", json={
        "student_id": sid, "psychologist_id": pid, "meeting_type_id": mt_id,
        "starts_at": _future_slot(44).isoformat(), "modality": "in_person",
    }, headers=_auth(tok_sv))
    assert r.status_code == 422, r.text
    rows = _fail_rows("appointment_create_failed", sup_id)
    assert len(rows) == 1
    _assert_failure(rows[0], sup_id, "supervisor", "engagement_required")


# ─── appointment_cancel/confirm/decline_failed (access_denied) ────────────────

def test_cancel_others_appointment_writes_access_denied(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_a, sid_a, _ = _make_user(client, "student")
    tok_b, sid_b, _ = _make_user(client, "student")
    _make_engagement(sid_a, pid)
    booked = _book(client, tok_a, mt_id, _future_slot(46))
    assert booked.status_code == 201, booked.text
    u = booked.json()["uuid"]
    r = client.patch(f"/api/appointments/{u}/cancel", json={"reason": "x"},
                     headers=_auth(tok_b))         # B не владелец
    assert r.status_code == 403, r.text
    rows = _fail_rows("appointment_cancel_failed", sid_b)
    assert len(rows) == 1
    _assert_failure(rows[0], sid_b, "student", "access_denied")


def test_confirm_others_appointment_writes_access_denied(client):
    tok_p1, pid1, mt_id = _setup_schedule(client)
    tok_p2, pid2, _ = _make_user(client, "psychologist")
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid1)
    booked = _book(client, tok_s, mt_id, _future_slot(48))
    assert booked.status_code == 201, booked.text
    u = booked.json()["uuid"]
    r = client.patch(f"/api/psychologist/appointments/{u}/confirm",
                     headers=_auth(tok_p2))        # чужой психолог
    assert r.status_code == 403, r.text
    rows = _fail_rows("appointment_confirm_failed", pid2)
    assert len(rows) == 1
    _assert_failure(rows[0], pid2, "psychologist", "access_denied")


def test_decline_others_appointment_writes_access_denied(client):
    tok_p1, pid1, mt_id = _setup_schedule(client)
    tok_p2, pid2, _ = _make_user(client, "psychologist")
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid1)
    booked = _book(client, tok_s, mt_id, _future_slot(50))
    assert booked.status_code == 201, booked.text
    u = booked.json()["uuid"]
    r = client.patch(f"/api/psychologist/appointments/{u}/decline",
                     json={"reason": "нет"}, headers=_auth(tok_p2))
    assert r.status_code == 403, r.text
    rows = _fail_rows("appointment_decline_failed", pid2)
    assert len(rows) == 1
    _assert_failure(rows[0], pid2, "psychologist", "access_denied")


# ─── unregistered_student_card_create_failed (consent_required) ───────────────

def test_card_create_without_consent_writes_consent_required(client):
    tok_sv, sup_id, _ = _make_user(client, "supervisor")
    suffix = _uuid.uuid4().hex[:8]
    r = client.post(CARDS_URL, json={
        "full_name": f"integ_fa_card_{suffix}",
        "email": f"integ_fa_card_{suffix}@example.com",
        "personal_data_consent": False,
    }, headers=_auth(tok_sv))
    assert r.status_code == 422, r.text
    rows = _fail_rows("unregistered_student_card_create_failed", sup_id)
    assert len(rows) == 1
    _assert_failure(rows[0], sup_id, "supervisor", "consent_required")
    # карточка не создана
    with SessionLocal() as db:
        assert db.query(UnregisteredStudentCard).filter(
            UnregisteredStudentCard.created_by == sup_id).count() == 0


def test_admin_card_create_without_consent_actor_admin(client):
    tok_ad, ad_id, _ = _make_user(client, "admin")
    suffix = _uuid.uuid4().hex[:8]
    r = client.post(CARDS_URL, json={
        "full_name": f"integ_fa_adcard_{suffix}",
        "personal_data_consent": False,
    }, headers=_auth(tok_ad))
    assert r.status_code == 422, r.text
    rows = _fail_rows("unregistered_student_card_create_failed", ad_id)
    assert len(rows) == 1
    _assert_failure(rows[0], ad_id, "admin", "consent_required")


# ─── Negative control: неаудируемый отказ → 0 failure-строк ───────────────────

def test_non_auditable_rejection_writes_no_failure_row(client):
    # booking_lead_time (starts_at ≤ cutoff, 422) — обычное бизнес-правило,
    # не аудируется. Ни одной appointment_create_failed строки.
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    r = _book(client, tok_s, mt_id, _future_slot(0.2))   # ~12 мин → lead time
    assert r.status_code == 422, r.text
    assert _fail_rows("appointment_create_failed", sid) == []


def test_no_pii_in_failure_audit(client):
    # Синтетические уникальные значения не должны попасть в failure-строку.
    import json as _json
    tok_sv, sup_id, _ = _make_user(client, "supervisor")
    secret = f"SECRETCARD_{_uuid.uuid4().hex}"
    r = client.post(CARDS_URL, json={
        "full_name": secret, "email": f"{secret}@example.com",
        "primary_concern": secret, "personal_data_consent": False,
    }, headers=_auth(tok_sv))
    assert r.status_code == 422, r.text
    for row in _fail_rows("unregistered_student_card_create_failed", sup_id):
        blob = (row.description or "") + _json.dumps(
            row.log_metadata or {}, ensure_ascii=False)
        assert secret not in blob
