"""
Stage 5B-1 — gated integration: audit trail для individual appointments и walk-in
cards. Запуск ТОЛЬКО через Stage 1 isolated runner (scripts/isolated_test_db.py)
при безопасном TEST_DATABASE_URL; dev/prod запрещены.

Проверяет success-события lifecycle: appointment_created/confirmed/declined/
cancelled и unregistered_student_card_created/updated/archived/linked с точными
actor/target/outcome/metadata, отсутствием ПДн, before/after по entity_id,
per-card linking (A self-registration actor=student, B staff-created actor=
supervisor/admin), no-op update/archive.

Requires: PostgreSQL on alembic head, DATA_ENCRYPTION_KEY, seeded roles/consents.
"""
import uuid as _uuid
from datetime import date, datetime, time, timedelta, timezone

import bcrypt

from app.auth import otp_service
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    AuditLog, MeetingType, ScheduleRule, TherapyEngagement,
    UnregisteredStudentCard, User,
)

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))
CARDS_URL = "/api/supervisor/unregistered-student-cards"
ALLOWED_DOMAIN = "donnu.ru"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _make_user(client, role, *, domain="example.com"):
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_apa_{role}_{suffix}@{domain}"
    user = auth_storage.save_user({
        "name": f"ApaTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
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
                                psychologist_id=psychologist_id, status="active")
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _setup_schedule(client):
    tok_p, pid, _ = _make_user(client, "psychologist")
    with SessionLocal() as db:
        mt = MeetingType(
            name=f"integ_type_{_uuid.uuid4().hex[:6]}", duration_minutes=50,
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


def _card_payload(**overrides):
    suffix = _uuid.uuid4().hex[:8]
    payload = {
        "full_name": f"integ_card_{suffix}",
        "phone": "+70000000001",
        "email": f"integ_card_{suffix}@example.com",
        "personal_data_consent": True,
    }
    payload.update(overrides)
    return payload


def _create_card(client, token, **overrides):
    return client.post(CARDS_URL, json=_card_payload(**overrides),
                       headers=_auth(token))


def _rows(event_type, entity_id):
    with SessionLocal() as db:
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.event_type == event_type,
                    AuditLog.entity_type.in_(("appointment",
                                              "unregistered_student_card")),
                    AuditLog.entity_id == entity_id)
            .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
            .all()
        )
        for r in rows:
            db.expunge(r)
        return rows


def _assert_success(row, entity_type, entity_id, actor_id, actor_role,
                    metadata=None):
    assert row.entity_type == entity_type and row.entity_id == entity_id
    assert row.outcome == "success" and row.failure_reason_code is None
    assert row.description is None
    assert (row.log_metadata or {}) == (metadata or {})
    assert row.user_id == actor_id and row.user_role == actor_role


def _card_id_by_uuid(card_uuid):
    with SessionLocal() as db:
        row = db.query(UnregisteredStudentCard.id).filter(
            UnregisteredStudentCard.uuid == card_uuid).first()
        return row.id


def _appt_id_by_uuid(appt_uuid):
    from app.db.models import Appointment
    with SessionLocal() as db:
        row = db.query(Appointment.id).filter(
            Appointment.uuid == appt_uuid).first()
        return row.id


# ─── Cards: create / update / archive ─────────────────────────────────────────

def test_card_create_writes_created(client):
    tok, sup_id, _ = _make_user(client, "supervisor")
    r = _create_card(client, tok)
    assert r.status_code == 201, r.text
    cid = _card_id_by_uuid(r.json()["uuid"])
    rows = _rows("unregistered_student_card_created", cid)
    assert len(rows) == 1
    _assert_success(rows[0], "unregistered_student_card", cid, sup_id,
                    "supervisor")


def test_card_update_real_diff_and_noop(client):
    tok, sup_id, _ = _make_user(client, "supervisor")
    r = _create_card(client, tok, full_name="integ_before")
    cid = _card_id_by_uuid(r.json()["uuid"])
    url = f"{CARDS_URL}/{cid}"

    # real diff → одна строка
    assert client.patch(url, json={"full_name": "integ_after"},
                        headers=_auth(tok)).status_code == 200
    assert len(_rows("unregistered_student_card_updated", cid)) == 1

    # empty PATCH и identical → 0 новых строк
    before = len(_rows("unregistered_student_card_updated", cid))
    assert client.patch(url, json={}, headers=_auth(tok)).status_code == 200
    assert client.patch(url, json={"full_name": "integ_after"},
                        headers=_auth(tok)).status_code == 200
    assert len(_rows("unregistered_student_card_updated", cid)) == before


def test_card_archive_transition_and_repeat(client):
    tok, sup_id, _ = _make_user(client, "supervisor")
    cid = _card_id_by_uuid(_create_card(client, tok).json()["uuid"])
    url = f"{CARDS_URL}/{cid}/archive"

    assert client.post(url, headers=_auth(tok)).status_code == 200
    rows = _rows("unregistered_student_card_archived", cid)
    assert len(rows) == 1
    _assert_success(rows[0], "unregistered_student_card", cid, sup_id,
                    "supervisor")
    # повторный archive → 0 новых строк
    assert client.post(url, headers=_auth(tok)).status_code == 200
    assert len(_rows("unregistered_student_card_archived", cid)) == 1


# ─── Linking: A self-registration (actor=student) ──────────────────────────────

def _seed_otp(email):
    return otp_service.create_or_update_otp(
        email, "Link Tester", bcrypt.hashpw(PASSWORD.encode(),
                                            bcrypt.gensalt()).decode())


def test_linking_self_registration_actor_student(client):
    tok_sv, _, _ = _make_user(client, "supervisor")
    email = f"integ_linkA_{_uuid.uuid4().hex[:8]}@{ALLOWED_DOMAIN}"
    cid = _card_id_by_uuid(_create_card(client, tok_sv, email=email).json()["uuid"])

    code = _seed_otp(email)
    r = client.post("/api/auth/register/confirm",
                    json={"email": email, "code": code})
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        uid = db.query(User.id).filter(User.email == email.lower()).scalar()

    rows = _rows("unregistered_student_card_linked", cid)
    assert len(rows) == 1
    _assert_success(rows[0], "unregistered_student_card", cid, uid, "student",
                    metadata={"linked_user_id": uid})
    # ПДн карточки не в audit
    import json as _json
    blob = _json.dumps(rows[0].log_metadata or {}, ensure_ascii=False)
    assert email not in blob


def test_linking_idempotent_no_second_row(client):
    tok_sv, _, _ = _make_user(client, "supervisor")
    email = f"integ_linkI_{_uuid.uuid4().hex[:8]}@{ALLOWED_DOMAIN}"
    cid = _card_id_by_uuid(_create_card(client, tok_sv, email=email).json()["uuid"])
    code = _seed_otp(email)
    assert client.post("/api/auth/register/confirm",
                       json={"email": email, "code": code}).status_code == 201
    before = len(_rows("unregistered_student_card_linked", cid))
    # повторная привязка того же email в service идемпотентна (0 unlinked)
    from app.appointments.service import link_unregistered_cards_to_user
    with SessionLocal() as db:
        uid = db.query(User.id).filter(User.email == email.lower()).scalar()
    link_unregistered_cards_to_user(
        uid, email, actor_id=uid, actor_role="student")
    assert len(_rows("unregistered_student_card_linked", cid)) == before


# ─── Appointments: booking / confirm / decline / cancel ────────────────────────

def _book_student(client, tok_s, mt_id, slot):
    return client.post("/api/appointments", json={
        "starts_at": slot.isoformat(), "modality": "in_person",
        "meeting_type_id": mt_id,
    }, headers=_auth(tok_s))


def test_student_booking_writes_created_actor_student(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    r = _book_student(client, tok_s, mt_id, _future_slot(40))
    assert r.status_code == 201, r.text
    aid = _appt_id_by_uuid(r.json()["uuid"])
    rows = _rows("appointment_created", aid)
    assert len(rows) == 1
    _assert_success(rows[0], "appointment", aid, sid, "student")


def test_supervisor_manual_booking_writes_created_actor_supervisor(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    tok_sv, sup_id, _ = _make_user(client, "supervisor")
    _make_engagement(sid, pid)
    r = client.post("/api/supervisor/appointments", json={
        "student_id": sid, "psychologist_id": pid, "meeting_type_id": mt_id,
        "starts_at": _future_slot(48).isoformat(), "modality": "in_person",
    }, headers=_auth(tok_sv))
    assert r.status_code == 201, r.text
    aid = _appt_id_by_uuid(r.json()["uuid"])
    rows = _rows("appointment_created", aid)
    assert len(rows) == 1
    _assert_success(rows[0], "appointment", aid, sup_id, "supervisor")


def test_confirm_and_decline(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    # confirm
    r = _book_student(client, tok_s, mt_id, _future_slot(40))
    u = r.json()["uuid"]
    aid = _appt_id_by_uuid(u)
    assert client.patch(f"/api/psychologist/appointments/{u}/confirm",
                        headers=_auth(tok_p)).status_code == 200
    rows = _rows("appointment_confirmed", aid)
    assert len(rows) == 1
    _assert_success(rows[0], "appointment", aid, pid, "psychologist")
    # decline (new appt)
    r2 = _book_student(client, tok_s, mt_id, _future_slot(64))
    u2 = r2.json()["uuid"]
    aid2 = _appt_id_by_uuid(u2)
    assert client.patch(f"/api/psychologist/appointments/{u2}/decline",
                        json={"reason": "занят"},
                        headers=_auth(tok_p)).status_code == 200
    drows = _rows("appointment_declined", aid2)
    assert len(drows) == 1
    _assert_success(drows[0], "appointment", aid2, pid, "psychologist")
    import json as _json
    assert "занят" not in _json.dumps(drows[0].log_metadata or {},
                                      ensure_ascii=False)


def test_cancel_pending_soft_delete_keeps_audit(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    r = _book_student(client, tok_s, mt_id, _future_slot(40))
    u = r.json()["uuid"]
    aid = _appt_id_by_uuid(u)
    assert client.patch(f"/api/appointments/{u}/cancel",
                        json={"reason": "передумал"},
                        headers=_auth(tok_s)).status_code == 200
    rows = _rows("appointment_cancelled", aid)
    assert len(rows) == 1                       # audit сохранён при soft-delete
    _assert_success(rows[0], "appointment", aid, sid, "student")
    from app.db.models import Appointment
    with SessionLocal() as db:
        appt = db.query(Appointment).filter(Appointment.id == aid).first()
        assert appt.deleted_at is not None      # запись soft-deleted


# ─── Corrective: walk-in / admin actor / confirmed cancel / linking B ──────────

def test_walk_in_card_manual_booking_actor_supervisor(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_sv, sup_id, _ = _make_user(client, "supervisor")
    cid = _card_id_by_uuid(_create_card(client, tok_sv).json()["uuid"])
    r = client.post("/api/supervisor/appointments", json={
        "unregistered_student_card_id": cid, "psychologist_id": pid,
        "meeting_type_id": mt_id, "starts_at": _future_slot(52).isoformat(),
        "modality": "in_person",
    }, headers=_auth(tok_sv))
    assert r.status_code == 201, r.text
    aid = _appt_id_by_uuid(r.json()["uuid"])
    rows = _rows("appointment_created", aid)
    assert len(rows) == 1
    _assert_success(rows[0], "appointment", aid, sup_id, "supervisor")


def test_admin_only_manual_booking_actor_admin(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    tok_ad, ad_id, _ = _make_user(client, "admin")
    _make_engagement(sid, pid)
    r = client.post("/api/supervisor/appointments", json={
        "student_id": sid, "psychologist_id": pid, "meeting_type_id": mt_id,
        "starts_at": _future_slot(56).isoformat(), "modality": "in_person",
    }, headers=_auth(tok_ad))
    assert r.status_code == 201, r.text
    aid = _appt_id_by_uuid(r.json()["uuid"])
    _assert_success(_rows("appointment_created", aid)[0],
                    "appointment", aid, ad_id, "admin")


def test_admin_card_create_update_archive(client):
    tok_ad, ad_id, _ = _make_user(client, "admin")
    cid = _card_id_by_uuid(_create_card(client, tok_ad).json()["uuid"])
    _assert_success(_rows("unregistered_student_card_created", cid)[0],
                    "unregistered_student_card", cid, ad_id, "admin")
    url = f"{CARDS_URL}/{cid}"
    assert client.patch(url, json={"full_name": "admin_upd"},
                        headers=_auth(tok_ad)).status_code == 200
    _assert_success(_rows("unregistered_student_card_updated", cid)[0],
                    "unregistered_student_card", cid, ad_id, "admin")
    assert client.post(f"{url}/archive", headers=_auth(tok_ad)).status_code == 200
    _assert_success(_rows("unregistered_student_card_archived", cid)[0],
                    "unregistered_student_card", cid, ad_id, "admin")


def test_confirmed_appointment_cancel_not_soft_deleted(client):
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    r = _book_student(client, tok_s, mt_id, _future_slot(40))
    u = r.json()["uuid"]
    aid = _appt_id_by_uuid(u)
    assert client.patch(f"/api/psychologist/appointments/{u}/confirm",
                        headers=_auth(tok_p)).status_code == 200
    assert client.patch(f"/api/appointments/{u}/cancel", json={"reason": "x"},
                        headers=_auth(tok_s)).status_code == 200
    rows = _rows("appointment_cancelled", aid)
    assert len(rows) == 1
    _assert_success(rows[0], "appointment", aid, sid, "student")
    from app.db.models import Appointment
    with SessionLocal() as db:
        appt = db.query(Appointment).filter(Appointment.id == aid).first()
        assert appt.deleted_at is None and appt.status == "cancelled"


def test_staff_created_student_linking_actor_staff(client):
    tok_sv, sup_id, _ = _make_user(client, "supervisor")
    email = f"integ_linkB_{_uuid.uuid4().hex[:8]}@{ALLOWED_DOMAIN}"
    cid = _card_id_by_uuid(_create_card(client, tok_sv, email=email).json()["uuid"])
    r = client.post("/api/supervisor/students", json={
        "full_name": "Студент Тестовый", "email": email,
        "personal_data_consent": True,
    }, headers=_auth(tok_sv))
    assert r.status_code in (200, 201), r.text
    with SessionLocal() as db:
        uid = db.query(User.id).filter(User.email == email.lower()).scalar()
    rows = _rows("unregistered_student_card_linked", cid)
    assert len(rows) == 1
    _assert_success(rows[0], "unregistered_student_card", cid, sup_id,
                    "supervisor", metadata={"linked_user_id": uid})


def test_multiple_matching_cards_linked_per_card(client):
    tok_sv, _, _ = _make_user(client, "supervisor")
    email = f"integ_multi_{_uuid.uuid4().hex[:8]}@{ALLOWED_DOMAIN}"
    cid1 = _card_id_by_uuid(_create_card(client, tok_sv, email=email).json()["uuid"])
    cid2 = _card_id_by_uuid(_create_card(client, tok_sv, email=email).json()["uuid"])
    code = _seed_otp(email)
    assert client.post("/api/auth/register/confirm",
                       json={"email": email, "code": code}).status_code == 201
    assert len(_rows("unregistered_student_card_linked", cid1)) == 1
    assert len(_rows("unregistered_student_card_linked", cid2)) == 1


def test_already_linked_to_other_no_mutation_or_audit(client):
    tok_sv, _, _ = _make_user(client, "supervisor")
    _, other_id, _ = _make_user(client, "student")
    email = f"integ_alnk_{_uuid.uuid4().hex[:8]}@{ALLOWED_DOMAIN}"
    cid = _card_id_by_uuid(_create_card(client, tok_sv, email=email).json()["uuid"])
    with SessionLocal() as db:
        c = db.query(UnregisteredStudentCard).filter(
            UnregisteredStudentCard.id == cid).first()
        c.linked_user_id = other_id   # уже привязана к другому user
        db.commit()

    code = _seed_otp(email)
    assert client.post("/api/auth/register/confirm",
                       json={"email": email, "code": code}).status_code == 201
    assert _rows("unregistered_student_card_linked", cid) == []   # не переприв.
    with SessionLocal() as db:
        c = db.query(UnregisteredStudentCard).filter(
            UnregisteredStudentCard.id == cid).first()
        assert c.linked_user_id == other_id   # связь не изменилась


def test_no_pii_in_appointment_audit(client):
    # Синтетические уникальные значения; ни одно не должно попасть в audit payload.
    import json as _json
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    secret_topic = f"SECRETTOPIC_{_uuid.uuid4().hex}"
    r = client.post("/api/appointments", json={
        "starts_at": _future_slot(40).isoformat(), "modality": "in_person",
        "meeting_type_id": mt_id, "topic": secret_topic,
    }, headers=_auth(tok_s))
    assert r.status_code == 201, r.text
    aid = _appt_id_by_uuid(r.json()["uuid"])
    for row in _rows("appointment_created", aid):
        blob = (row.description or "") + _json.dumps(
            row.log_metadata or {}, ensure_ascii=False)
        assert secret_topic not in blob


# ─── Corrective (final pass, item 2/3): comprehensive gated privacy coverage ───

def _blob(row):
    """description + JSON-serialised metadata, for substring PII checks."""
    import json as _json
    return (row.description or "") + _json.dumps(
        row.log_metadata or {}, ensure_ascii=False)


def _assert_full_contract(row, expected_event_type, entity_type, entity_id,
                          actor_id, actor_role, metadata=None):
    """Exact success contract: event_type is checked explicitly (final pass
    item 5), plus entity/actor/outcome/failure_reason_code/description/
    metadata — all fields, not just a subset."""
    assert row.event_type == expected_event_type
    _assert_success(row, entity_type, entity_id, actor_id, actor_role,
                    metadata=metadata)


def test_no_pii_across_all_appointment_and_card_events(client):
    """Corrective (final pass): synthetic unique values for every sensitive
    field (appointment topic/cancellation_reason/decline_reason; card
    full_name/phone/email/normalized_email/birth_date/comment/
    primary_concern/consent_source; appointment/card UUID) must not leak
    into description or metadata of ANY appointment/card audit row produced
    by this test — every such row the test itself creates is collected and
    checked (not a fixed subset). Linked event metadata stays strictly
    {"linked_user_id": int}."""
    tok_p, pid, mt_id = _setup_schedule(client)
    tok_sv, sup_id, _ = _make_user(client, "supervisor")
    suf = _uuid.uuid4().hex[:8]
    all_rows = []
    expected_count = 0
    secrets = []

    def _collect(event_type, entity_id, expected_actor_id, expected_role,
                metadata=None):
        rows = _rows(event_type, entity_id)
        assert len(rows) == 1, (event_type, entity_id)
        _assert_full_contract(rows[0], event_type,
                              "appointment" if event_type.startswith(
                                  "appointment_")
                              else "unregistered_student_card",
                              entity_id, expected_actor_id, expected_role,
                              metadata=metadata)
        nonlocal expected_count
        expected_count += len(rows)
        all_rows.extend(rows)

    # ── card 1: create / update / archive, full sensitive field set ────────
    secret_full_name = f"SECRETNAME{suf}"
    secret_phone = f"+7900{suf}"
    secret_email = f"secretcard_{suf}@example.com"
    secret_comment = f"SECRETCOMMENT{suf}"
    secret_concern = f"SECRETCONCERN{suf}"
    secret_consent_source = f"secsrc{suf}"
    secret_birth_date = "1999-09-09"

    r = _create_card(
        client, tok_sv,
        full_name=secret_full_name, phone=secret_phone, email=secret_email,
        comment=secret_comment, primary_concern=secret_concern,
        birth_date=secret_birth_date, consent_source=secret_consent_source,
    )
    assert r.status_code == 201, r.text
    card_uuid = r.json()["uuid"]
    cid = _card_id_by_uuid(card_uuid)
    _collect("unregistered_student_card_created", cid, sup_id, "supervisor")
    secrets += [secret_full_name, secret_phone, secret_email, secret_comment,
                secret_concern, secret_consent_source, secret_birth_date,
                card_uuid]

    secret_updated_name = f"SECRETUPD{suf}"
    url = f"{CARDS_URL}/{cid}"
    assert client.patch(url, json={"full_name": secret_updated_name},
                        headers=_auth(tok_sv)).status_code == 200
    _collect("unregistered_student_card_updated", cid, sup_id, "supervisor")
    secrets.append(secret_updated_name)

    assert client.post(f"{url}/archive", headers=_auth(tok_sv)).status_code == 200
    _collect("unregistered_student_card_archived", cid, sup_id, "supervisor")

    # ── card 2: walk-in manual booking with a secret topic ─────────────────
    secret_cid2_name = f"SECRETCID2{suf}"
    r2 = _create_card(client, tok_sv, full_name=secret_cid2_name)
    assert r2.status_code == 201, r2.text
    card2_uuid = r2.json()["uuid"]
    cid2 = _card_id_by_uuid(card2_uuid)
    _collect("unregistered_student_card_created", cid2, sup_id, "supervisor")
    secrets += [secret_cid2_name, card2_uuid]

    secret_topic = f"SECRETTOPIC{suf}"
    ar = client.post("/api/supervisor/appointments", json={
        "unregistered_student_card_id": cid2, "psychologist_id": pid,
        "meeting_type_id": mt_id, "starts_at": _future_slot(70).isoformat(),
        "modality": "in_person", "topic": secret_topic,
    }, headers=_auth(tok_sv))
    assert ar.status_code == 201, ar.text
    appt_uuid = ar.json()["uuid"]
    aid = _appt_id_by_uuid(appt_uuid)
    _collect("appointment_created", aid, sup_id, "supervisor")
    secrets += [secret_topic, appt_uuid]

    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)

    # ── appointment 3: student booking + decline with a secret reason ──────
    r3 = _book_student(client, tok_s, mt_id, _future_slot(80))
    assert r3.status_code == 201, r3.text
    u3 = r3.json()["uuid"]
    aid3 = _appt_id_by_uuid(u3)
    _collect("appointment_created", aid3, sid, "student")
    secrets.append(u3)

    secret_decline_reason = f"SECRETDECLINE{suf}"
    assert client.patch(f"/api/psychologist/appointments/{u3}/decline",
                        json={"reason": secret_decline_reason},
                        headers=_auth(tok_p)).status_code == 200
    _collect("appointment_declined", aid3, pid, "psychologist")
    secrets.append(secret_decline_reason)

    # ── appointment 4: student booking + cancel with a secret reason ───────
    r4 = _book_student(client, tok_s, mt_id, _future_slot(90))
    assert r4.status_code == 201, r4.text
    u4 = r4.json()["uuid"]
    aid4 = _appt_id_by_uuid(u4)
    _collect("appointment_created", aid4, sid, "student")
    secrets.append(u4)

    secret_cancel_reason = f"SECRETCANCEL{suf}"
    assert client.patch(f"/api/appointments/{u4}/cancel",
                        json={"reason": secret_cancel_reason},
                        headers=_auth(tok_s)).status_code == 200
    _collect("appointment_cancelled", aid4, sid, "student")
    secrets.append(secret_cancel_reason)

    # ── appointment 5: student booking + confirm with a secret topic ───────
    secret_confirm_topic = f"SECRETCONFIRM{suf}"
    r5 = client.post("/api/appointments", json={
        "starts_at": _future_slot(100).isoformat(), "modality": "in_person",
        "meeting_type_id": mt_id, "topic": secret_confirm_topic,
    }, headers=_auth(tok_s))
    assert r5.status_code == 201, r5.text
    u5 = r5.json()["uuid"]
    aid5 = _appt_id_by_uuid(u5)
    _collect("appointment_created", aid5, sid, "student")
    secrets += [secret_confirm_topic, u5]

    assert client.patch(f"/api/psychologist/appointments/{u5}/confirm",
                        headers=_auth(tok_p)).status_code == 200
    _collect("appointment_confirmed", aid5, pid, "psychologist")

    # ── card 3 + linking: actor=student (self-registration) ────────────────
    secret_cid3_name = f"SECRETCID3{suf}"
    link_email = f"integ_pii_link_{suf}@{ALLOWED_DOMAIN}"
    r6 = _create_card(client, tok_sv, email=link_email,
                      full_name=secret_cid3_name)
    assert r6.status_code == 201, r6.text
    card3_uuid = r6.json()["uuid"]
    cid3 = _card_id_by_uuid(card3_uuid)
    _collect("unregistered_student_card_created", cid3, sup_id, "supervisor")
    secrets += [secret_cid3_name, card3_uuid, link_email]

    code = _seed_otp(link_email)
    lr = client.post("/api/auth/register/confirm",
                     json={"email": link_email, "code": code})
    assert lr.status_code == 201, lr.text
    with SessionLocal() as db:
        linked_uid = db.query(User.id).filter(
            User.email == link_email.lower()).scalar()
    _collect("unregistered_student_card_linked", cid3, linked_uid, "student",
             metadata={"linked_user_id": linked_uid})

    # ── privacy blob-check across every row collected above ────────────────
    # expected_count is the sum of the per-operation len(rows)==1 checks
    # above, not a hardcoded literal — it grows with whatever operations
    # this test actually performs.
    assert len(all_rows) == expected_count
    for row in all_rows:
        blob = _blob(row)
        for secret in secrets:
            assert secret not in blob, (row.event_type, secret)
        # Allowed metadata is strictly {} or {"linked_user_id": int}.
        assert set(row.log_metadata or {}) <= {"linked_user_id"}
