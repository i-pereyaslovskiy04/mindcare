"""
Integration tests for appointments system (reworked schedule/slot model).

Schedule model:
- MeetingType owns duration_minutes + buffer_minutes (the slot grid).
- ScheduleRule describes only availability windows (day_of_week, start/end,
  optional meeting_type_id, period, series_id), no slot duration.
- ScheduleBreak — recurring breaks (e.g. lunch 13:00–14:00).
- ScheduleException types: day_off / unavailable / extra_availability; multiple
  blockers per date are allowed (no unique-per-date constraint).

Coverage:
- Individual booking validations (no engagement / past / <1h / valid pending).
- Slots computed from MeetingType.duration_minutes (+ buffer affects next slot).
- Booking requires a valid meeting_type_id.
- Booking rejected outside the schedule (422); occupied slot → 409.
- Group sessions block individual slots.
- pending_confirmation / confirmed block the slot.
- Cancelling pending_confirmation soft-deletes (hidden from lists).
- Cancelling confirmed notifies the psychologist (system message).
- Multiple one-off blockers on one date do not cause a 500.
- Group session tests (capacity, re-registration, role access, etc.).
- Schedule rule bulk create (shared series_id) + invalid range rejected.

Requires: dev PostgreSQL on alembic head, DATA_ENCRYPTION_KEY in .env.
"""

import threading
import uuid as _uuid
from datetime import date, datetime, time, timedelta, timezone

import bcrypt

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    Appointment,
    ChatConversation,
    ChatMessage,
    GroupSession,
    GroupSessionRegistration,
    MeetingType,
    ScheduleBreak,
    ScheduleRule,
    TherapyEngagement,
    User,
)

PASSWORD = "SecurePass42!"
# Moscow is UTC+3, no DST since 2014
MOSCOW_TZ = timezone(timedelta(hours=3))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str):
    """Returns (token, user_id, email)."""
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_apt_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"AptTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()
        ).decode(),
        "role": role,
    })
    r = client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert r.status_code == 200
    return r.json()["session_token"], int(user["id"]), email


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_engagement(
    client_id: int,
    psychologist_id: int,
    eng_status: str = "active",
) -> int:
    with SessionLocal() as db:
        eng = TherapyEngagement(
            client_id=client_id,
            psychologist_id=psychologist_id,
            status=eng_status,
        )
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _future_slot(hours_ahead: float = 25.0) -> datetime:
    """Rounded future datetime in Moscow timezone (UTC+3 aware)."""
    msk = datetime.now(MOSCOW_TZ) + timedelta(hours=hours_ahead)
    return msk.replace(minute=0, second=0, microsecond=0)


def _future_date(days: int = 7) -> date:
    return (datetime.now(MOSCOW_TZ) + timedelta(days=days)).date()


def _hhmm(iso: str) -> str:
    dt = datetime.fromisoformat(iso).astimezone(MOSCOW_TZ)
    return dt.strftime("%H:%M")


def _make_meeting_type(
    db,
    is_group: bool = False,
    duration: int = 50,
    buffer: int = 10,
) -> MeetingType:
    mt = MeetingType(
        name=f"integ_type_{_uuid.uuid4().hex[:6]}",
        duration_minutes=duration,
        buffer_minutes=buffer,
        allow_in_person=True,
        allow_online=True,
        is_group=is_group,
        is_active=True,
        is_bookable=True,
        display_order=0,
    )
    db.add(mt)
    db.flush()
    return mt


def _add_rule(
    db,
    pid: int,
    dow: int,
    start: str,
    end: str,
    mt_id: int = None,
):
    """Create a ScheduleRule. mt_id is optional (working window, schedule v3)."""
    db.add(ScheduleRule(
        psychologist_id=pid,
        day_of_week=dow,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        meeting_type_id=mt_id,
        effective_from=date(2020, 1, 1),
        is_active=True,
    ))


def _setup_schedule(client, duration: int = 50, buffer: int = 10):
    """Psychologist with full-week availability and an individual meeting type.

    Returns (psych_token, psych_id, meeting_type_id).
    """
    tok_p, pid, _ = _make_user(client, "psychologist")
    with SessionLocal() as db:
        mt = _make_meeting_type(db, is_group=False, duration=duration, buffer=buffer)
        mt_id = mt.id
        for dow in range(7):
            _add_rule(db, pid, dow, "00:00", "23:59", mt_id=mt_id)
        db.commit()
    return tok_p, pid, mt_id


def _student_for(client, pid: int):
    tok_s, sid, _ = _make_user(client, "student")
    _make_engagement(sid, pid)
    return tok_s, sid


def _make_group_session(
    db,
    meeting_type_id: int,
    psychologist_id: int,
    capacity: int = 5,
    booking_enabled: bool = True,
    starts_at: datetime = None,
) -> GroupSession:
    if starts_at is None:
        starts_at = datetime.now(MOSCOW_TZ) + timedelta(days=3)
    gs = GroupSession(
        uuid=_uuid.uuid4(),
        meeting_type_id=meeting_type_id,
        psychologist_id=psychologist_id,
        title="Тест групповое",
        starts_at=starts_at,
        format="in_person",
        capacity=capacity,
        booking_enabled=booking_enabled,
        status="scheduled",
    )
    db.add(gs)
    db.flush()
    return gs


# ─── Individual appointment validation ────────────────────────────────────────

class TestIndividualAppointments:

    def test_01_cannot_book_without_engagement(self, client):
        """Студент без назначения получает 403."""
        tok, _, _ = _make_user(client, "student")
        payload = {
            "starts_at": _future_slot().isoformat(),
            "modality": "in_person",
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok)
        )
        assert r.status_code == 403
        assert "психолог" in r.json()["detail"].lower()

    def test_02_cannot_book_past_time(self, client):
        """Нельзя записаться на прошедшее время."""
        tok, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)

        past = datetime.now(MOSCOW_TZ) - timedelta(hours=2)
        payload = {"starts_at": past.isoformat(), "modality": "in_person"}
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok)
        )
        assert r.status_code == 422

    def test_03_cannot_book_less_than_1h_ahead(self, client):
        """Нельзя записаться менее чем за 1 час."""
        tok, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)

        soon = datetime.now(MOSCOW_TZ) + timedelta(minutes=30)
        payload = {"starts_at": soon.isoformat(), "modality": "in_person"}
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok)
        )
        assert r.status_code == 422

    def test_04_appointment_created_pending(self, client):
        """Успешная запись на валидный слот → pending_confirmation."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid = _student_for(client, pid)

        payload = {
            "starts_at": _future_slot(26).isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["status"] == "pending_confirmation"
        assert data["client_id"] == sid
        assert data["psychologist_id"] == pid

    def test_05_slot_blocked_by_pending(self, client):
        """Второй студент не может занять тот же слот (409)."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok1, _ = _student_for(client, pid)
        tok2, _ = _student_for(client, pid)

        slot = _future_slot(27)
        payload = {
            "starts_at": slot.isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }

        r1 = client.post(
            "/api/appointments", json=payload, headers=_auth(tok1)
        )
        assert r1.status_code == 201, r1.text

        r2 = client.post(
            "/api/appointments", json=payload, headers=_auth(tok2)
        )
        assert r2.status_code == 409

    def test_06_psychologist_can_only_confirm_own(self, client):
        """Чужой психолог не может подтвердить запись."""
        tok_p1, pid1, mt_id = _setup_schedule(client)
        tok_p2, _, _ = _make_user(client, "psychologist")
        tok_s, _ = _student_for(client, pid1)

        payload = {
            "starts_at": _future_slot(28).isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 201, r.text
        appt_uuid = r.json()["uuid"]

        r_deny = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/confirm",
            headers=_auth(tok_p2),
        )
        assert r_deny.status_code == 403

        r_ok = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/confirm",
            headers=_auth(tok_p1),
        )
        assert r_ok.status_code == 200
        assert r_ok.json()["status"] == "confirmed"

    def test_07_student_sees_pending_in_list(self, client):
        """Студент видит запись в списке со статусом pending."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, _ = _student_for(client, pid)

        payload = {
            "starts_at": _future_slot(29).isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        client.post("/api/appointments", json=payload, headers=_auth(tok_s))

        r = client.get("/api/appointments/my", headers=_auth(tok_s))
        assert r.status_code == 200
        statuses = [i["status"] for i in r.json()["items"]]
        assert "pending_confirmation" in statuses

    def test_08_student_can_cancel_before_appointment_day(self, client):
        """Студент отменяет запись за несколько дней."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, _ = _student_for(client, pid)

        payload = {
            "starts_at": _future_slot(24 * 5).isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 201, r.text
        appt_uuid = r.json()["uuid"]

        r_cancel = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={"reason": "Не смогу прийти"},
            headers=_auth(tok_s),
        )
        assert r_cancel.status_code == 200
        assert r_cancel.json()["status"] == "cancelled"

    def test_07b_appointment_response_has_meeting_type_name(self, client):
        """Appointment response отдаёт meeting_type_name и duration."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, _ = _student_for(client, pid)

        with SessionLocal() as db:
            mt_name = db.query(MeetingType).filter(
                MeetingType.id == mt_id
            ).first().name

        payload = {
            "starts_at": _future_slot(31).isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 201, r.text
        assert r.json()["meeting_type_name"] == mt_name
        assert r.json()["meeting_type_duration_minutes"] == 50

        # И в списке психолога имя типа также присутствует.
        r_list = client.get(
            "/api/psychologist/appointments", headers=_auth(tok_p)
        )
        assert r_list.status_code == 200, r_list.text
        names = [i["meeting_type_name"] for i in r_list.json()["items"]]
        assert mt_name in names

    def test_08b_cannot_cancel_on_appointment_day(self, client):
        """Нельзя отменить запись в день записи (UTC+3)."""
        tok, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)

        now_msk = datetime.now(MOSCOW_TZ)
        today_slot = now_msk.replace(
            hour=23, minute=0, second=0, microsecond=0
        )
        if today_slot <= now_msk:
            today_slot = today_slot + timedelta(hours=1)

        with SessionLocal() as db:
            eng = db.query(TherapyEngagement).filter(
                TherapyEngagement.client_id == sid,
                TherapyEngagement.status == "active",
            ).first()
            appt = Appointment(
                client_id=sid,
                psychologist_id=pid,
                engagement_id=eng.id,
                starts_at=today_slot,
                duration_minutes=50,
                modality="in_person",
                status="pending_confirmation",
            )
            db.add(appt)
            db.commit()
            db.refresh(appt)
            appt_uuid = str(appt.uuid)

        r = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={},
            headers=_auth(tok),
        )
        assert r.status_code == 422
        assert "до дня" in r.json()["detail"].lower()


# ─── Slot computation (MeetingType-driven) ────────────────────────────────────

class TestSlotComputation:

    def test_slots_use_meeting_type_duration(self, client):
        """Слоты считаются по MeetingType.duration_minutes (+ buffer)."""
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(7)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            _add_rule(db, pid, target.weekday(), "09:00", "12:00", mt_id=mt_id)
            db.commit()

        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={mt_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        slots = r.json()["slots"]
        assert all(s["duration_minutes"] == 50 for s in slots)
        starts = sorted(_hhmm(s["starts_at"]) for s in slots)
        # 50+10 = 60 min step: 09:00, 10:00, 11:00 (11:00+50=11:50 ≤ 12:00)
        assert starts == ["09:00", "10:00", "11:00"]

    def test_buffer_affects_next_slot(self, client):
        """buffer_minutes сдвигает старт следующего слота."""
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(8)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=20)
            mt_id = mt.id
            _add_rule(db, pid, target.weekday(), "09:00", "11:00", mt_id=mt_id)
            db.commit()

        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={mt_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        starts = sorted(_hhmm(s["starts_at"]) for s in r.json()["slots"])
        # 09:00–09:50, then 09:50+20=10:10–11:00
        assert starts == ["09:00", "10:10"]

    def test_group_session_blocks_individual_slots(self, client):
        """Групповое занятие психолога блокирует индивидуальный слот."""
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(9)

        with SessionLocal() as db:
            mt_ind = _make_meeting_type(db, duration=50, buffer=10)
            ind_id = mt_ind.id
            mt_grp = _make_meeting_type(db, is_group=True, duration=50)
            _add_rule(db, pid, target.weekday(), "09:00", "12:00", mt_id=ind_id)
            gs_start = datetime.combine(target, time(10, 0)).replace(
                tzinfo=MOSCOW_TZ
            )
            _make_group_session(
                db, mt_grp.id, pid, capacity=10, starts_at=gs_start
            )
            db.commit()

        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={ind_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        starts = sorted(_hhmm(s["starts_at"]) for s in r.json()["slots"])
        # Group session 10:00–10:50 blocks the 10:00 slot
        assert "10:00" not in starts
        assert "09:00" in starts
        assert "11:00" in starts


# ─── Booking validation against schedule ──────────────────────────────────────

class TestBookingValidation:

    def test_cannot_book_without_meeting_type(self, client):
        """Нельзя записаться без валидного meeting_type_id (422)."""
        tok_p, pid, _ = _setup_schedule(client)
        tok_s, _ = _student_for(client, pid)

        payload = {
            "starts_at": _future_slot(30).isoformat(),
            "modality": "in_person",
            # no meeting_type_id
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 422

    def test_cannot_book_with_invalid_meeting_type(self, client):
        """Несуществующий meeting_type_id → 404/422."""
        tok_p, pid, _ = _setup_schedule(client)
        tok_s, _ = _student_for(client, pid)

        payload = {
            "starts_at": _future_slot(31).isoformat(),
            "modality": "in_person",
            "meeting_type_id": 99999999,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code in (404, 422)

    def test_cannot_book_outside_schedule(self, client):
        """Нельзя записаться на время вне расписания (422)."""
        tok_p, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            for dow in range(7):
                _add_rule(db, pid, dow, "09:00", "10:00", mt_id=mt_id)
            db.commit()
        tok_s, _ = _student_for(client, pid)

        # 14:00 is well outside the 09:00–10:00 window
        slot = _future_slot(48).replace(hour=14)
        payload = {
            "starts_at": slot.isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 422
        assert "расписан" in r.json()["detail"].lower()


# ─── Cancellation behaviour ───────────────────────────────────────────────────

class TestCancellation:

    def test_cancelled_pending_not_in_list(self, client):
        """Отменённый pending_confirmation soft-deleted и не виден в списке."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, _ = _student_for(client, pid)

        payload = {
            "starts_at": _future_slot(24 * 5).isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 201, r.text
        appt_uuid = r.json()["uuid"]

        r_cancel = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={},
            headers=_auth(tok_s),
        )
        assert r_cancel.status_code == 200

        r_list = client.get("/api/appointments/my", headers=_auth(tok_s))
        assert r_list.status_code == 200
        uuids = [i["uuid"] for i in r_list.json()["items"]]
        assert appt_uuid not in uuids

    def test_cancelled_confirmed_notifies_psychologist(self, client):
        """Отмена confirmed → запись видна как cancelled + system message психологу."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid = _student_for(client, pid)

        payload = {
            "starts_at": _future_slot(24 * 5).isoformat(),
            "modality": "in_person",
            "meeting_type_id": mt_id,
        }
        r = client.post(
            "/api/appointments", json=payload, headers=_auth(tok_s)
        )
        assert r.status_code == 201, r.text
        appt_uuid = r.json()["uuid"]

        # Psychologist confirms
        r_conf = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/confirm",
            headers=_auth(tok_p),
        )
        assert r_conf.status_code == 200
        assert r_conf.json()["status"] == "confirmed"

        # Student cancels the confirmed appointment
        r_cancel = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={"reason": "Передумал"},
            headers=_auth(tok_s),
        )
        assert r_cancel.status_code == 200
        assert r_cancel.json()["status"] == "cancelled"

        # Still visible in the student's list (not soft-deleted)
        r_list = client.get("/api/appointments/my", headers=_auth(tok_s))
        uuids = [i["uuid"] for i in r_list.json()["items"]]
        assert appt_uuid in uuids

        # Psychologist received a system message
        with SessionLocal() as db:
            conv = (
                db.query(ChatConversation)
                .filter(
                    ChatConversation.type == "system",
                    ChatConversation.recipient_id == pid,
                )
                .first()
            )
            assert conv is not None
            msg = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.conversation_id == conv.id,
                    ChatMessage.event_key == f"appointment_cancelled:{appt_uuid}",
                )
                .first()
            )
            assert msg is not None


# ─── One-off blockers (exceptions) ────────────────────────────────────────────

class TestScheduleExceptions:

    def test_multiple_blockers_same_date_no_500(self, client):
        """Несколько разовых блокировок на одну дату не дают 500."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        target = _future_date(10).isoformat()

        base = {
            "psychologist_id": pid,
            "exception_date": target,
            "exception_type": "unavailable",
        }
        r1 = client.post(
            "/api/supervisor/schedule-exceptions",
            json={**base, "start_time": "09:00", "end_time": "10:00"},
            headers=_auth(tok_sv),
        )
        assert r1.status_code == 201, r1.text

        r2 = client.post(
            "/api/supervisor/schedule-exceptions",
            json={**base, "start_time": "11:00", "end_time": "12:00"},
            headers=_auth(tok_sv),
        )
        assert r2.status_code == 201, r2.text


# ─── Group session tests ───────────────────────────────────────────────────────

class TestGroupSessions:

    def test_09_supervisor_creates_group_session(self, client):
        """Супервизор создаёт групповое занятие (+ description)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            mt_id = mt.id
            db.commit()

        payload = {
            "meeting_type_id": mt_id,
            "psychologist_id": pid,
            "title": "Групповая сессия 1",
            "description": "Описание занятия",
            "starts_at": _future_slot(48).isoformat(),
            "format": "in_person",
            "capacity": 10,
            "booking_enabled": True,
        }
        r = client.post(
            "/api/supervisor/group-sessions",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["status"] == "scheduled"
        assert data["capacity"] == 10
        assert data["booking_enabled"] is True
        assert data["description"] == "Описание занятия"

    def test_10_supervisor_toggle_booking(self, client):
        """Супервизор открывает/закрывает запись."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(db, mt.id, pid, booking_enabled=True)
            gs_uuid = str(gs.uuid)
            db.commit()

        url_close = (
            f"/api/supervisor/group-sessions/{gs_uuid}/booking?enabled=false"
        )
        r_close = client.patch(url_close, headers=_auth(tok_sv))
        assert r_close.status_code == 200
        assert r_close.json()["booking_enabled"] is False

        url_open = (
            f"/api/supervisor/group-sessions/{gs_uuid}/booking?enabled=true"
        )
        r_open = client.patch(url_open, headers=_auth(tok_sv))
        assert r_open.status_code == 200
        assert r_open.json()["booking_enabled"] is True

    def test_11_student_registers_for_group_session(self, client):
        """Студент успешно записывается на занятие."""
        tok_s, _, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(
                db, mt.id, pid, capacity=10, booking_enabled=True
            )
            gs_uuid = str(gs.uuid)
            db.commit()

        r = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 201
        assert r.json()["status"] == "registered"

    def test_12_cannot_register_twice(self, client):
        """Нельзя записаться дважды на одно занятие."""
        tok_s, _, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(db, mt.id, pid, capacity=10)
            gs_uuid = str(gs.uuid)
            db.commit()

        r1 = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r1.status_code == 201

        r2 = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r2.status_code == 409
        assert "зарегистрированы" in r2.json()["detail"].lower()

    def test_13_cannot_exceed_capacity(self, client):
        """Нельзя превысить вместимость занятия."""
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(db, mt.id, pid, capacity=2)
            gs_uuid = str(gs.uuid)
            db.commit()

        students = [_make_user(client, "student") for _ in range(3)]

        r1 = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(students[0][0]),
        )
        assert r1.status_code == 201
        r2 = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(students[1][0]),
        )
        assert r2.status_code == 201

        r3 = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(students[2][0]),
        )
        assert r3.status_code == 409
        assert "мест" in r3.json()["detail"].lower()

    def test_14_cannot_register_for_closed_session(self, client):
        """Нельзя записаться на закрытое занятие."""
        tok_s, _, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(
                db, mt.id, pid, capacity=10, booking_enabled=False
            )
            gs_uuid = str(gs.uuid)
            db.commit()

        r = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 422
        assert "закрыта" in r.json()["detail"].lower()

    def test_15_group_registration_no_confirmation_needed(self, client):
        """Регистрация на группу активна без подтверждения."""
        tok_s, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(db, mt.id, pid, capacity=10)
            gs_uuid = str(gs.uuid)
            db.commit()

        r = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 201
        assert r.json()["status"] == "registered"

        with SessionLocal() as db:
            reg = (
                db.query(GroupSessionRegistration)
                .filter(GroupSessionRegistration.student_id == sid)
                .order_by(GroupSessionRegistration.created_at.desc())
                .first()
            )
            assert reg is not None
            assert reg.status == "registered"


class TestGroupSessionValidations:

    def test_16_reregister_after_cancel(self, client):
        """Студент может повторно записаться после отмены."""
        tok_s, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(db, mt.id, pid, capacity=10)
            gs_uuid = str(gs.uuid)
            db.commit()

        r1 = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r1.status_code == 201

        r_cancel = client.delete(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r_cancel.status_code == 204

        r2 = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r2.status_code == 201
        assert r2.json()["status"] == "registered"

        with SessionLocal() as db:
            rows = (
                db.query(GroupSessionRegistration)
                .filter(
                    GroupSessionRegistration.student_id == sid,
                    GroupSessionRegistration.status == "registered",
                )
                .all()
            )
            assert len(rows) == 1

    def test_17_inactive_meeting_type_blocks_registration(self, client):
        """Неактивный тип занятия — регистрация отклоняется."""
        tok_s, _, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = MeetingType(
                name=f"integ_inactive_{_uuid.uuid4().hex[:6]}",
                duration_minutes=60,
                buffer_minutes=10,
                allow_in_person=True,
                allow_online=False,
                is_group=True,
                is_active=False,
                is_bookable=True,
                display_order=0,
            )
            db.add(mt)
            db.flush()
            gs = _make_group_session(db, mt.id, pid, capacity=10)
            gs_uuid = str(gs.uuid)
            db.commit()

        r = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 422
        assert "недоступен" in r.json()["detail"].lower()

    def test_18_non_bookable_meeting_type_blocks_registration(self, client):
        """is_bookable=False — регистрация отклоняется."""
        tok_s, _, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = MeetingType(
                name=f"integ_nonbookable_{_uuid.uuid4().hex[:6]}",
                duration_minutes=60,
                buffer_minutes=10,
                allow_in_person=True,
                allow_online=False,
                is_group=True,
                is_active=True,
                is_bookable=False,
                display_order=0,
            )
            db.add(mt)
            db.flush()
            gs = _make_group_session(db, mt.id, pid, capacity=10)
            gs_uuid = str(gs.uuid)
            db.commit()

        r = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 422
        assert "недоступен" in r.json()["detail"].lower()

    def test_19_cannot_register_less_than_1h_before_start(self, client):
        """Нельзя записаться менее чем за 1 час до начала."""
        tok_s, _, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        soon = datetime.now(MOSCOW_TZ) + timedelta(minutes=30)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(
                db, mt.id, pid, capacity=10, starts_at=soon
            )
            gs_uuid = str(gs.uuid)
            db.commit()

        r = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 422
        assert "1 час" in r.json()["detail"].lower()

    def test_20_cannot_cancel_group_on_day_of(self, client):
        """Нельзя отменить регистрацию в день занятия (МСК)."""
        tok_s, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        now_msk = datetime.now(MOSCOW_TZ)
        today_evening = now_msk.replace(
            hour=23, minute=59, second=0, microsecond=0
        )
        if today_evening <= now_msk:
            today_evening += timedelta(days=1)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(
                db, mt.id, pid, capacity=10, starts_at=today_evening
            )
            reg = GroupSessionRegistration(
                uuid=_uuid.uuid4(),
                group_session_id=gs.id,
                student_id=sid,
                status="registered",
            )
            db.add(reg)
            db.commit()
            db.refresh(gs)
            gs_uuid = str(gs.uuid)

        r = client.delete(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 422
        assert "до дня" in r.json()["detail"].lower()

    def test_21_concurrent_registrations_respect_capacity(self, client):
        """Параллельные регистрации не превышают вместимость (cap=1)."""
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(db, mt.id, pid, capacity=1)
            gs_uuid = str(gs.uuid)
            db.commit()

        students = [_make_user(client, "student") for _ in range(3)]
        results = []

        def try_register(tok):
            r = client.post(
                f"/api/group-sessions/{gs_uuid}/register",
                headers=_auth(tok),
            )
            results.append(r.status_code)

        threads = [
            threading.Thread(target=try_register, args=(s[0],))
            for s in students
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        successes = results.count(201)
        rejections = [c for c in results if c != 201]
        assert successes == 1, f"Expected 1 success, got {successes}: {results}"
        assert all(c == 409 for c in rejections), (
            f"Expected 409s, got {rejections}"
        )

    def test_22_advisory_lock_does_not_crash(self, client):
        """acquire_slot_lock работает без ошибок внутри транзакции."""
        from app.appointments import storage as apt_storage

        _, pid, _ = _make_user(client, "psychologist")
        slot = _future_slot(50)

        with SessionLocal() as db:
            apt_storage.acquire_slot_lock(pid, slot, db)
            db.rollback()


# ─── Meeting types: role access + schema fields ───────────────────────────────

class TestMeetingTypesAccess:

    def _payload(self):
        return {
            "name": f"integ_type_{_uuid.uuid4().hex[:6]}",
            "description": "Тестовый тип",
            "duration_minutes": 50,
            "buffer_minutes": 10,
            "allow_in_person": True,
            "allow_online": True,
            "is_group": False,
            "is_active": True,
            "is_bookable": True,
            "display_order": 0,
        }

    def test_23_admin_can_create_meeting_type(self, client):
        """admin создаёт тип встречи через supervisor-эндпоинт."""
        tok_admin, _, _ = _make_user(client, "admin")
        r = client.post(
            "/api/supervisor/meeting-types",
            json=self._payload(),
            headers=_auth(tok_admin),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["is_group"] is False
        assert data["buffer_minutes"] == 10
        assert data["description"] == "Тестовый тип"

    def test_24_supervisor_can_create_meeting_type(self, client):
        """supervisor создаёт тип встречи."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        r = client.post(
            "/api/supervisor/meeting-types",
            json=self._payload(),
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201

    def test_25_student_cannot_create_meeting_type(self, client):
        """Студент не может создавать типы встреч (403)."""
        tok_s, _, _ = _make_user(client, "student")
        r = client.post(
            "/api/supervisor/meeting-types",
            json=self._payload(),
            headers=_auth(tok_s),
        )
        assert r.status_code == 403

    def test_26_update_accepts_all_frontend_fields(self, client):
        """PATCH принимает все поля формы фронта, включая is_group/buffer."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        payload = self._payload()
        payload["allow_online"] = True
        payload["allow_in_person"] = False
        r = client.post(
            "/api/supervisor/meeting-types",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201
        mt_id = r.json()["id"]

        update = {
            "name": f"integ_type_{_uuid.uuid4().hex[:6]}",
            "description": "Обновлённое описание",
            "duration_minutes": 90,
            "buffer_minutes": 15,
            "allow_in_person": False,
            "allow_online": True,
            "is_group": True,
            "is_active": True,
            "is_bookable": True,
            "display_order": 3,
        }
        r2 = client.patch(
            f"/api/supervisor/meeting-types/{mt_id}",
            json=update,
            headers=_auth(tok_sv),
        )
        assert r2.status_code == 200, r2.text
        data = r2.json()
        assert data["is_group"] is True
        assert data["duration_minutes"] == 90
        assert data["buffer_minutes"] == 15
        assert data["display_order"] == 3


# ─── Psychologist group sessions endpoint ─────────────────────────────────────

class TestPsychologistGroupSessions:

    def test_27_psychologist_sees_only_own_group_sessions(self, client):
        """Психолог видит только свои группы и верный счётчик."""
        tok_p1, pid1, _ = _make_user(client, "psychologist")
        _, pid2, _ = _make_user(client, "psychologist")
        tok_s, _, _ = _make_user(client, "student")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs1 = _make_group_session(db, mt.id, pid1, capacity=10)
            _make_group_session(db, mt.id, pid2, capacity=10)
            gs1_uuid = str(gs1.uuid)
            db.commit()

        r_reg = client.post(
            f"/api/group-sessions/{gs1_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r_reg.status_code == 201

        r = client.get(
            "/api/psychologist/group-sessions",
            headers=_auth(tok_p1),
        )
        assert r.status_code == 200
        items = r.json()["items"]
        uuids = [i["uuid"] for i in items]
        assert gs1_uuid in uuids
        assert all(i["psychologist_id"] == pid1 for i in items)
        own = next(i for i in items if i["uuid"] == gs1_uuid)
        assert own["registered_count"] == 1

    def test_28_endpoint_rejects_non_psychologist(self, client):
        """Эндпоинт доступен только роли psychologist."""
        tok_s, _, _ = _make_user(client, "student")
        r = client.get(
            "/api/psychologist/group-sessions",
            headers=_auth(tok_s),
        )
        assert r.status_code == 403

    def test_29_inactive_student_cannot_register(self, client):
        """Неактивный студент не может записаться (403)."""
        tok_s, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db, is_group=True)
            gs = _make_group_session(db, mt.id, pid, capacity=10)
            gs_uuid = str(gs.uuid)
            db.query(User).filter(User.id == sid).update(
                {"is_active": False}
            )
            db.commit()

        r = client.post(
            f"/api/group-sessions/{gs_uuid}/register",
            headers=_auth(tok_s),
        )
        assert r.status_code == 403
        assert "неактив" in r.json()["detail"].lower()


# ─── Schedule rules (supervisor) ──────────────────────────────────────────────

class TestScheduleRules:

    def test_30_supervisor_bulk_creates_rules(self, client):
        """supervisor создаёт правила на несколько дней с общим series_id."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")

        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        payload = {
            "psychologist_id": pid,
            "days_of_week": [0, 1, 2],
            "start_time": "09:00",
            "end_time": "17:00",
            "meeting_type_id": mt_id,
            "period": "morning",
            "effective_from": "2026-07-01",
        }
        r = client.post(
            "/api/supervisor/schedule-rules",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        rules = r.json()
        assert len(rules) == 3
        series_ids = {rule["series_id"] for rule in rules}
        assert len(series_ids) == 1
        assert series_ids != {None}
        assert all(rule["meeting_type_id"] == mt_id for rule in rules)
        assert {rule["day_of_week"] for rule in rules} == {0, 1, 2}

        r_list = client.get(
            f"/api/supervisor/schedule-rules?psychologist_id={pid}",
            headers=_auth(tok_sv),
        )
        assert r_list.status_code == 200
        listed_ids = {rule["id"] for rule in r_list.json()}
        assert all(rule["id"] in listed_ids for rule in rules)

    def test_31_invalid_time_range_rejected(self, client):
        """start_time >= end_time → 422."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")

        payload = {
            "psychologist_id": pid,
            "days_of_week": [2],
            "start_time": "18:00",
            "end_time": "09:00",
            "effective_from": "2026-07-01",
        }
        r = client.post(
            "/api/supervisor/schedule-rules",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422


# ─── Recurring breaks (supervisor) ────────────────────────────────────────────

class TestScheduleBreaks:

    def test_32_recurring_break_blocks_slots(self, client):
        """Обеденный перерыв исключает пересекающиеся слоты."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(11)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            _add_rule(db, pid, target.weekday(), "12:00", "16:00", mt_id=mt_id)
            db.commit()

        # Lunch break — effective_from in the past, so it IS active
        r_break = client.post(
            "/api/supervisor/schedule-breaks",
            json={
                "psychologist_id": pid,
                "days_of_week": [target.weekday()],
                "start_time": "13:00",
                "end_time": "14:00",
                "title": "Обед",
                "effective_from": "2020-01-01",
            },
            headers=_auth(tok_sv),
        )
        assert r_break.status_code == 201, r_break.text

        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={mt_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        starts = sorted(_hhmm(s["starts_at"]) for s in r.json()["slots"])
        # 12:00, [13:00 & 13:00-blocked by lunch], 14:00, 15:00
        # 12:00–12:50 ok; 13:00–13:50 overlaps lunch → excluded;
        # 14:00–14:50 ok; 15:00–15:50 ok
        assert "13:00" not in starts
        assert "12:00" in starts
        assert "14:00" in starts
        assert "15:00" in starts


# ── Schedule v3: ScheduleRule.meeting_type_id is optional ─────────────────────

class TestScheduleRuleOptionalMeetingType:

    def test_33_rule_without_meeting_type_now_allowed(self, client):
        """A schedule rule with no meeting_type_id is a working window (201)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        payload = {
            "psychologist_id": pid,
            "days_of_week": [0],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": "2026-01-01",
            # meeting_type_id intentionally omitted — now allowed
        }
        r = client.post(
            "/api/supervisor/schedule-rules",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        rules = r.json()
        assert len(rules) == 1
        assert rules[0]["meeting_type_id"] is None

    def test_34_rule_with_invalid_time_still_422(self, client):
        """Invalid time range on a rule with meeting_type_id gives 422."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()
        payload = {
            "psychologist_id": pid,
            "days_of_week": [2],
            "start_time": "18:00",
            "end_time": "09:00",
            "meeting_type_id": mt_id,
            "effective_from": "2026-07-01",
        }
        r = client.post(
            "/api/supervisor/schedule-rules",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422

    def test_35_rule_with_meeting_type_listed_correctly(self, client):
        """Rule created with meeting_type_id is returned with that id."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()
        payload = {
            "psychologist_id": pid,
            "days_of_week": [1],
            "start_time": "10:00",
            "end_time": "18:00",
            "meeting_type_id": mt_id,
            "effective_from": "2026-09-01",
        }
        r = client.post(
            "/api/supervisor/schedule-rules",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        rules = r.json()
        assert len(rules) == 1
        assert rules[0]["meeting_type_id"] == mt_id


# ── Issue 3: ScheduleBreak.effective_from / effective_until ───────────────────

class TestScheduleBreakPeriods:

    def test_36_break_api_requires_effective_from(self, client):
        """API rejects a break creation without effective_from (422)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        payload = {
            "psychologist_id": pid,
            "days_of_week": [0],
            "start_time": "13:00",
            "end_time": "14:00",
            # effective_from intentionally omitted
        }
        r = client.post(
            "/api/supervisor/schedule-breaks",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422

    def test_37_break_future_effective_from_not_applied(self, client):
        """Break with effective_from after target does not block target."""
        from app.db.models import ScheduleBreak as SB
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(7)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            _add_rule(
                db, pid, target.weekday(),
                "09:00", "12:00", mt_id=mt_id,
            )
            # Break starts one day AFTER target — must NOT block target
            after_target = target + timedelta(days=1)
            br = SB(
                psychologist_id=pid,
                day_of_week=target.weekday(),
                start_time=time(9, 0),
                end_time=time(12, 0),
                effective_from=after_target,
                is_active=True,
            )
            db.add(br)
            db.commit()

        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={mt_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        # Break not yet started → slots on target are NOT blocked
        assert len(r.json()["slots"]) > 0

    def test_38_break_past_effective_until_not_applied(self, client):
        """Break with effective_until yesterday does not block slots."""
        from app.db.models import ScheduleBreak as SB
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)

        # Find next Monday (or any day with a stable dow=0 rule)
        base = datetime.now(MOSCOW_TZ).date() + timedelta(days=8)
        while base.weekday() != 0:
            base = base + timedelta(days=1)
        target = base

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            _add_rule(
                db, pid, 0, "09:00", "12:00", mt_id=mt_id,
            )
            yesterday = (
                datetime.now(MOSCOW_TZ) - timedelta(days=1)
            ).date()
            br = SB(
                psychologist_id=pid,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(12, 0),
                effective_from=date(2020, 1, 1),
                effective_until=yesterday,   # expired
                is_active=True,
            )
            db.add(br)
            db.commit()

        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={mt_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        # Expired break → slots on target are NOT blocked
        assert len(r.json()["slots"]) > 0

    def test_39_break_within_period_blocks_slots(self, client):
        """Break with effective_from in the past and no until blocks slots."""
        from app.db.models import ScheduleBreak as SB
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(13)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            _add_rule(
                db, pid, target.weekday(),
                "09:00", "12:00", mt_id=mt_id,
            )
            # Break from the beginning of time, no expiry → active
            br = SB(
                psychologist_id=pid,
                day_of_week=target.weekday(),
                start_time=time(9, 0),
                end_time=time(12, 0),
                effective_from=date(2020, 1, 1),
                effective_until=None,
                is_active=True,
            )
            db.add(br)
            db.commit()

        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={mt_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        # Break covers full window → no slots
        assert len(r.json()["slots"]) == 0

    def test_40_break_api_accepts_effective_from(self, client):
        """Break created via API with effective_from is returned correctly."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        payload = {
            "psychologist_id": pid,
            "days_of_week": [3],
            "start_time": "13:00",
            "end_time": "14:00",
            "title": "Обед",
            "effective_from": "2026-09-01",
            "effective_until": "2026-12-31",
        }
        r = client.post(
            "/api/supervisor/schedule-breaks",
            json=payload,
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert len(data) == 1
        b = data[0]
        assert b["effective_from"] == "2026-09-01"
        assert b["effective_until"] == "2026-12-31"
        assert b["day_of_week"] == 3


# ── Unified schedule create (rules + breaks in one series) ────────────────────

def _add_months_local(d: date, months: int) -> date:
    import calendar
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class TestUnifiedScheduleCreate:

    def test_41_bulk_create_rules_and_breaks(self, client):
        """POST /schedules creates rules on several days + breaks (one series)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        payload = {
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "days_of_week": [0, 1, 2],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": "2026-07-01",
            "breaks": [
                {"start_time": "13:00", "end_time": "14:00", "title": "Обед"}
            ],
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert len(data["rules"]) == 3
        assert {ru["day_of_week"] for ru in data["rules"]} == {0, 1, 2}
        # one break per day → 3 break rows, all sharing the series_id
        assert len(data["breaks"]) == 3
        series_id = data["series_id"]
        assert all(ru["series_id"] == series_id for ru in data["rules"])
        assert all(b["series_id"] == series_id for b in data["breaks"])
        assert data["auto_extend"] is False

    def test_42_auto_extend_requires_effective_until(self, client):
        """auto_extend=true without effective_until → 422."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        payload = {
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "days_of_week": [0],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": "2026-07-01",
            "auto_extend": True,
            # effective_until intentionally omitted
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 422

    def test_43_auto_extend_with_effective_until_ok(self, client):
        """auto_extend=true with effective_until → 201."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        payload = {
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "days_of_week": [0],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": "2026-07-01",
            "effective_until": "2026-09-30",
            "auto_extend": True,
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 201, r.text
        assert r.json()["auto_extend"] is True


class TestScheduleSoftDelete:

    def _create_series_for_target(self, client, tok_sv, pid, mt_id, target):
        payload = {
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "days_of_week": [target.weekday()],
            "start_time": "09:00",
            "end_time": "12:00",
            "effective_from": "2020-01-01",
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 201, r.text
        return r.json()["series_id"]

    def test_44_soft_delete_hides_from_active_list_and_slots(self, client):
        """Soft-delete hides the schedule from the active list and from slots."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(14)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            db.commit()

        series_id = self._create_series_for_target(
            client, tok_sv, pid, mt_id, target
        )

        # Slots exist before deletion
        url = (
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={mt_id}&modality=in_person"
        )
        r_before = client.get(url, headers=_auth(tok_s))
        assert r_before.status_code == 200
        assert len(r_before.json()["slots"]) > 0

        # Soft-delete the schedule
        r_del = client.delete(
            f"/api/supervisor/schedules/{series_id}", headers=_auth(tok_sv)
        )
        assert r_del.status_code == 200, r_del.text
        assert r_del.json()["deactivated_rules"] == 1

        # Active list no longer contains the series rules
        r_active = client.get(
            f"/api/supervisor/schedule-rules?psychologist_id={pid}",
            headers=_auth(tok_sv),
        )
        assert r_active.status_code == 200
        assert all(
            ru["series_id"] != series_id for ru in r_active.json()
        )

        # include_inactive=true shows them again
        r_all = client.get(
            f"/api/supervisor/schedule-rules?psychologist_id={pid}"
            f"&include_inactive=true",
            headers=_auth(tok_sv),
        )
        assert any(ru["series_id"] == series_id for ru in r_all.json())

        # Slots gone after deletion
        r_after = client.get(url, headers=_auth(tok_s))
        assert r_after.status_code == 200
        assert len(r_after.json()["slots"]) == 0

    def test_45_restore_returns_schedule(self, client):
        """Restore re-activates the schedule (back in active list)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        target = _future_date(15)
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        series_id = self._create_series_for_target(
            client, tok_sv, pid, mt_id, target
        )
        client.delete(
            f"/api/supervisor/schedules/{series_id}", headers=_auth(tok_sv)
        )

        r_restore = client.post(
            f"/api/supervisor/schedules/{series_id}/restore",
            headers=_auth(tok_sv),
        )
        assert r_restore.status_code == 200, r_restore.text
        assert r_restore.json()["is_active"] is True
        assert all(
            ru["is_active"] for ru in r_restore.json()["rules"]
        )

        r_active = client.get(
            f"/api/supervisor/schedule-rules?psychologist_id={pid}",
            headers=_auth(tok_sv),
        )
        assert any(ru["series_id"] == series_id for ru in r_active.json())

    def test_46_soft_delete_keeps_existing_appointments(self, client):
        """Deactivating a schedule does NOT delete existing appointments."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, _ = _make_user(client, "psychologist")
        tok_s, sid = _student_for(client, pid)
        target = _future_date(16)
        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            db.commit()

        series_id = self._create_series_for_target(
            client, tok_sv, pid, mt_id, target
        )

        # Student books a slot in the schedule
        slot = datetime.combine(target, time(9, 0)).replace(tzinfo=MOSCOW_TZ)
        r_book = client.post(
            "/api/appointments",
            json={
                "starts_at": slot.isoformat(),
                "modality": "in_person",
                "meeting_type_id": mt_id,
            },
            headers=_auth(tok_s),
        )
        assert r_book.status_code == 201, r_book.text
        appt_uuid = r_book.json()["uuid"]

        # Soft-delete the schedule
        r_del = client.delete(
            f"/api/supervisor/schedules/{series_id}", headers=_auth(tok_sv)
        )
        assert r_del.status_code == 200

        # Appointment still exists in the student's list and in the DB
        r_list = client.get("/api/appointments/my", headers=_auth(tok_s))
        uuids = [i["uuid"] for i in r_list.json()["items"]]
        assert appt_uuid in uuids
        with SessionLocal() as db:
            appt = (
                db.query(Appointment)
                .filter(Appointment.uuid == appt_uuid)
                .first()
            )
            assert appt is not None
            assert appt.deleted_at is None

    def test_47_soft_delete_warns_about_future_appointments(self, client):
        """Soft-delete returns a future_appointments count > 0 when relevant."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, _ = _make_user(client, "psychologist")
        tok_s, sid = _student_for(client, pid)
        target = _future_date(17)
        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            db.commit()

        series_id = self._create_series_for_target(
            client, tok_sv, pid, mt_id, target
        )
        slot = datetime.combine(target, time(9, 0)).replace(tzinfo=MOSCOW_TZ)
        r_book = client.post(
            "/api/appointments",
            json={
                "starts_at": slot.isoformat(),
                "modality": "in_person",
                "meeting_type_id": mt_id,
            },
            headers=_auth(tok_s),
        )
        assert r_book.status_code == 201, r_book.text

        r_del = client.delete(
            f"/api/supervisor/schedules/{series_id}", headers=_auth(tok_sv)
        )
        assert r_del.status_code == 200, r_del.text
        assert r_del.json()["future_appointments"] >= 1


class TestScheduleExtend:

    def test_48_extend_by_month_changes_effective_until(self, client):
        """Quick action 'extend by month' moves effective_until by ~1 month."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        payload = {
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "days_of_week": [0],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": "2026-07-01",
            "effective_until": "2026-09-30",
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 201, r.text
        series_id = r.json()["series_id"]
        assert r.json()["effective_until"] == "2026-09-30"

        r_ext = client.post(
            f"/api/supervisor/schedules/{series_id}/extend",
            headers=_auth(tok_sv),
        )
        assert r_ext.status_code == 200, r_ext.text
        expected = _add_months_local(date(2026, 9, 30), 1).isoformat()
        assert r_ext.json()["effective_until"] == expected
        assert all(
            ru["effective_until"] == expected for ru in r_ext.json()["rules"]
        )


class TestSupervisorManualBooking:

    def test_49_supervisor_books_student_on_free_slot(self, client):
        """Supervisor manually books a student → pending appt + slot occupied."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid = _student_for(client, pid)

        slot = _future_slot(40)
        r = client.post(
            "/api/supervisor/appointments",
            json={
                "student_id": sid,
                "psychologist_id": pid,
                "meeting_type_id": mt_id,
                "starts_at": slot.isoformat(),
                "modality": "in_person",
            },
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["status"] == "pending_confirmation"
        assert data["client_id"] == sid
        assert data["psychologist_id"] == pid
        appt_uuid = data["uuid"]

        # Slot is now occupied: another student cannot book it
        tok_s2, _ = _student_for(client, pid)
        r2 = client.post(
            "/api/appointments",
            json={
                "starts_at": slot.isoformat(),
                "modality": "in_person",
                "meeting_type_id": mt_id,
            },
            headers=_auth(tok_s2),
        )
        assert r2.status_code == 409

        # Psychologist received a system message about the supervisor booking
        with SessionLocal() as db:
            conv = (
                db.query(ChatConversation)
                .filter(
                    ChatConversation.type == "system",
                    ChatConversation.recipient_id == pid,
                )
                .first()
            )
            assert conv is not None
            msg = (
                db.query(ChatMessage)
                .filter(
                    ChatMessage.conversation_id == conv.id,
                    ChatMessage.event_key
                    == f"appointment_supervisor_new:{appt_uuid}",
                )
                .first()
            )
            assert msg is not None

    def test_50_cannot_manually_book_occupied_slot(self, client):
        """Supervisor cannot book a student on an already-occupied slot (409)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s1, _ = _student_for(client, pid)
        tok_s2, sid2 = _student_for(client, pid)

        slot = _future_slot(41)
        # First student books the slot
        r1 = client.post(
            "/api/appointments",
            json={
                "starts_at": slot.isoformat(),
                "modality": "in_person",
                "meeting_type_id": mt_id,
            },
            headers=_auth(tok_s1),
        )
        assert r1.status_code == 201, r1.text

        # Supervisor tries to book a second student on the same slot
        r2 = client.post(
            "/api/supervisor/appointments",
            json={
                "student_id": sid2,
                "psychologist_id": pid,
                "meeting_type_id": mt_id,
                "starts_at": slot.isoformat(),
                "modality": "in_person",
            },
            headers=_auth(tok_sv),
        )
        assert r2.status_code == 409


class TestAutoExtendMaintenance:

    def test_51_auto_extend_moves_until_and_notifies(self, client):
        """Maintenance auto-extend bumps due auto_extend series + notifies sv."""
        from app.appointments import service

        tok_sv, sv_id, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        today = datetime.now(MOSCOW_TZ).date()
        until = today + timedelta(days=5)   # within the default 14-day window
        payload = {
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "days_of_week": [0],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": (today - timedelta(days=1)).isoformat(),
            "effective_until": until.isoformat(),
            "auto_extend": True,
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 201, r.text
        series_id = r.json()["series_id"]

        result = service.auto_extend_schedules(within_days=14, months=1)
        assert result["extended_series"] >= 1
        assert result["dry_run"] is False

        # effective_until moved by 1 month for this series
        expected = _add_months_local(until, 1).isoformat()
        r_rules = client.get(
            f"/api/supervisor/schedule-rules?psychologist_id={pid}",
            headers=_auth(tok_sv),
        )
        series_rules = [
            ru for ru in r_rules.json() if ru["series_id"] == series_id
        ]
        assert series_rules
        assert all(ru["effective_until"] == expected for ru in series_rules)

        # Supervisor (creator) received a system message
        with SessionLocal() as db:
            conv = (
                db.query(ChatConversation)
                .filter(
                    ChatConversation.type == "system",
                    ChatConversation.recipient_id == sv_id,
                )
                .first()
            )
            assert conv is not None

    def test_52_auto_extend_dry_run_no_change(self, client):
        """dry-run reports candidates but does not change effective_until."""
        from app.appointments import service

        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            db.commit()

        today = datetime.now(MOSCOW_TZ).date()
        until = today + timedelta(days=3)
        payload = {
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "days_of_week": [0],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": (today - timedelta(days=1)).isoformat(),
            "effective_until": until.isoformat(),
            "auto_extend": True,
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 201, r.text
        series_id = r.json()["series_id"]

        result = service.auto_extend_schedules(
            within_days=14, months=1, dry_run=True
        )
        assert result["dry_run"] is True

        r_rules = client.get(
            f"/api/supervisor/schedule-rules?psychologist_id={pid}",
            headers=_auth(tok_sv),
        )
        series_rules = [
            ru for ru in r_rules.json() if ru["series_id"] == series_id
        ]
        assert series_rules
        # Unchanged by dry-run
        assert all(
            ru["effective_until"] == until.isoformat() for ru in series_rules
        )


# ── Audit fields: booking_source + created_by ─────────────────────────────────

class TestBookingAuditFields:

    def test_53_supervisor_booking_sets_created_by_and_source(self, client):
        """Supervisor manual booking records created_by=sv_id, source=supervisor."""
        tok_sv, sv_id, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid = _student_for(client, pid)

        slot = _future_slot(42)
        r = client.post(
            "/api/supervisor/appointments",
            json={
                "student_id": sid,
                "psychologist_id": pid,
                "meeting_type_id": mt_id,
                "starts_at": slot.isoformat(),
                "modality": "in_person",
            },
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["booking_source"] == "supervisor"
        assert data["created_by"] == sv_id

    def test_54_student_self_booking_sets_correct_audit_fields(self, client):
        """Student self-booking records booking_source=student_self, created_by=student."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid = _student_for(client, pid)

        slot = _future_slot(43)
        r = client.post(
            "/api/appointments",
            json={
                "starts_at": slot.isoformat(),
                "modality": "in_person",
                "meeting_type_id": mt_id,
            },
            headers=_auth(tok_s),
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["booking_source"] == "student_self"
        assert data["created_by"] == sid


# ── Schedule impact: time-window filtering ────────────────────────────────────

class TestScheduleImpactTimeWindow:

    def _create_series_09_12(self, client, tok_sv, pid, mt_id, target):
        """Series: target weekday, 09:00–12:00."""
        r = client.post(
            "/api/supervisor/schedules",
            json={
                "psychologist_id": pid,
                "meeting_type_id": mt_id,
                "days_of_week": [target.weekday()],
                "start_time": "09:00",
                "end_time": "12:00",
                "effective_from": "2020-01-01",
            },
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        return r.json()["series_id"]

    def test_55_impact_excludes_appointment_outside_time_window(self, client):
        """Appointment on the same weekday/type but outside window → not counted."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        tok_s, sid = _student_for(client, pid)
        target = _future_date(22)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            db.commit()

        series_id = self._create_series_09_12(
            client, tok_sv, pid, mt_id, target
        )

        # Insert appointment at 14:00 — outside the 09:00–12:00 window
        outside_slot = datetime.combine(
            target, time(14, 0)
        ).replace(tzinfo=MOSCOW_TZ)
        with SessionLocal() as db:
            appt = Appointment(
                uuid=_uuid.uuid4(),
                client_id=sid,
                psychologist_id=pid,
                engagement_id=None,
                meeting_type_id=mt_id,
                starts_at=outside_slot,
                duration_minutes=50,
                ends_at=outside_slot + timedelta(minutes=50),
                modality="in_person",
                status="pending_confirmation",
            )
            db.add(appt)
            db.commit()

        r = client.get(
            f"/api/supervisor/schedules/{series_id}/impact",
            headers=_auth(tok_sv),
        )
        assert r.status_code == 200, r.text
        assert r.json()["future_appointments"] == 0

    def test_56_impact_counts_appointment_inside_time_window(self, client):
        """Appointment inside the rule's 09:00–12:00 window IS counted."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        tok_s, sid = _student_for(client, pid)
        target = _future_date(23)

        with SessionLocal() as db:
            mt = _make_meeting_type(db, duration=50, buffer=10)
            mt_id = mt.id
            db.commit()

        series_id = self._create_series_09_12(
            client, tok_sv, pid, mt_id, target
        )

        # Insert appointment at 10:00 — inside the 09:00–12:00 window
        inside_slot = datetime.combine(
            target, time(10, 0)
        ).replace(tzinfo=MOSCOW_TZ)
        with SessionLocal() as db:
            appt = Appointment(
                uuid=_uuid.uuid4(),
                client_id=sid,
                psychologist_id=pid,
                engagement_id=None,
                meeting_type_id=mt_id,
                starts_at=inside_slot,
                duration_minutes=50,
                ends_at=inside_slot + timedelta(minutes=50),
                modality="in_person",
                status="pending_confirmation",
            )
            db.add(appt)
            db.commit()

        r = client.get(
            f"/api/supervisor/schedules/{series_id}/impact",
            headers=_auth(tok_sv),
        )
        assert r.status_code == 200, r.text
        assert r.json()["future_appointments"] == 1


# ── Student meeting-types endpoint (schedule v2 frontend) ─────────────────────

class TestStudentMeetingTypes:

    def test_57_returns_only_bookable_individual(self, client):
        """Студент видит только активные, bookable, индивидуальные типы."""
        tok_s, _, _ = _make_user(client, "student")
        with SessionLocal() as db:
            indiv = _make_meeting_type(db, is_group=False)
            indiv_id = indiv.id
            group = _make_meeting_type(db, is_group=True)
            group_id = group.id
            nonbookable = MeetingType(
                name=f"integ_nb_{_uuid.uuid4().hex[:6]}",
                duration_minutes=50, buffer_minutes=10,
                allow_in_person=True, allow_online=True,
                is_group=False, is_active=True, is_bookable=False,
                display_order=0,
            )
            inactive = MeetingType(
                name=f"integ_inact_{_uuid.uuid4().hex[:6]}",
                duration_minutes=50, buffer_minutes=10,
                allow_in_person=True, allow_online=True,
                is_group=False, is_active=False, is_bookable=True,
                display_order=0,
            )
            db.add_all([nonbookable, inactive])
            db.commit()
            nb_id, inactive_id = nonbookable.id, inactive.id

        r = client.get(
            "/api/appointments/meeting-types", headers=_auth(tok_s)
        )
        assert r.status_code == 200, r.text
        ids = [mt["id"] for mt in r.json()]
        assert indiv_id in ids
        assert group_id not in ids
        assert nb_id not in ids
        assert inactive_id not in ids

    def test_58_forbidden_for_psychologist(self, client):
        """Эндпоинт типов для студента закрыт для психолога (403)."""
        tok_p, _, _ = _make_user(client, "psychologist")
        r = client.get(
            "/api/appointments/meeting-types", headers=_auth(tok_p)
        )
        assert r.status_code == 403


# ── Psychologist read-only schedule endpoint ──────────────────────────────────

class TestPsychologistSchedule:

    def test_59_returns_own_active_rules_breaks_and_types(self, client):
        """Психолог видит свои активные rules+breaks и типы этих правил."""
        tok_p, pid, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            mt_id = mt.id
            active_rule = ScheduleRule(
                psychologist_id=pid, day_of_week=1,
                start_time=time(9, 0), end_time=time(12, 0),
                meeting_type_id=mt_id, effective_from=date(2020, 1, 1),
                is_active=True,
            )
            inactive_rule = ScheduleRule(
                psychologist_id=pid, day_of_week=2,
                start_time=time(9, 0), end_time=time(12, 0),
                meeting_type_id=mt_id, effective_from=date(2020, 1, 1),
                is_active=False,
            )
            active_break = ScheduleBreak(
                psychologist_id=pid, day_of_week=1,
                start_time=time(13, 0), end_time=time(14, 0),
                effective_from=date(2020, 1, 1), is_active=True,
            )
            inactive_break = ScheduleBreak(
                psychologist_id=pid, day_of_week=1,
                start_time=time(15, 0), end_time=time(16, 0),
                effective_from=date(2020, 1, 1), is_active=False,
            )
            db.add_all([
                active_rule, inactive_rule, active_break, inactive_break,
            ])
            db.commit()
            ar_id, ir_id = active_rule.id, inactive_rule.id
            ab_id, ib_id = active_break.id, inactive_break.id

        r = client.get("/api/psychologist/schedule", headers=_auth(tok_p))
        assert r.status_code == 200, r.text
        data = r.json()
        rule_ids = [x["id"] for x in data["rules"]]
        break_ids = [x["id"] for x in data["breaks"]]
        type_ids = [x["id"] for x in data["meeting_types"]]
        assert ar_id in rule_ids
        assert ir_id not in rule_ids
        assert ab_id in break_ids
        assert ib_id not in break_ids
        assert mt_id in type_ids

    def test_60_other_psychologist_isolated(self, client):
        """Психолог не видит расписание другого психолога."""
        tok_p1, pid1, _ = _make_user(client, "psychologist")
        tok_p2, _, _ = _make_user(client, "psychologist")
        with SessionLocal() as db:
            mt = _make_meeting_type(db)
            db.add(ScheduleRule(
                psychologist_id=pid1, day_of_week=1,
                start_time=time(9, 0), end_time=time(12, 0),
                meeting_type_id=mt.id, effective_from=date(2020, 1, 1),
                is_active=True,
            ))
            db.commit()
        r = client.get("/api/psychologist/schedule", headers=_auth(tok_p2))
        assert r.status_code == 200, r.text
        assert r.json()["rules"] == []

    def test_61_forbidden_for_non_psychologist(self, client):
        """Расписание психолога закрыто для студента и супервизора (403)."""
        tok_s, _, _ = _make_user(client, "student")
        tok_sv, _, _ = _make_user(client, "supervisor")
        assert client.get(
            "/api/psychologist/schedule", headers=_auth(tok_s)
        ).status_code == 403
        assert client.get(
            "/api/psychologist/schedule", headers=_auth(tok_sv)
        ).status_code == 403


# ── Supervisor slots endpoint (manual booking via free slots) ─────────────────

class TestSupervisorSlots:

    def test_62_returns_slots_and_excludes_busy(self, client):
        """Супервизор видит свободные слоты психолога; занятый слот исчезает."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid = _student_for(client, pid)
        d = _future_date(9)
        params = {
            "psychologist_id": pid,
            "date": d.isoformat(),
            "meeting_type_id": mt_id,
            "modality": "in_person",
        }

        r = client.get(
            "/api/supervisor/slots", params=params, headers=_auth(tok_sv)
        )
        assert r.status_code == 200, r.text
        slots = r.json()["slots"]
        assert len(slots) > 0
        target_slot = slots[0]["starts_at"]

        rb = client.post(
            "/api/appointments",
            json={
                "starts_at": target_slot,
                "modality": "in_person",
                "meeting_type_id": mt_id,
            },
            headers=_auth(tok_s),
        )
        assert rb.status_code == 201, rb.text

        r2 = client.get(
            "/api/supervisor/slots", params=params, headers=_auth(tok_sv)
        )
        assert r2.status_code == 200, r2.text
        remaining = [s["starts_at"] for s in r2.json()["slots"]]
        assert target_slot not in remaining

    def test_63_forbidden_for_student(self, client):
        """Эндпоинт слотов супервизора закрыт для студента (403)."""
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid = _student_for(client, pid)
        r = client.get(
            "/api/supervisor/slots",
            params={
                "psychologist_id": pid,
                "date": _future_date(9).isoformat(),
                "meeting_type_id": mt_id,
                "modality": "in_person",
            },
            headers=_auth(tok_s),
        )
        assert r.status_code == 403


# ── Schedule v3: working windows decoupled from meeting type ──────────────────

class TestScheduleV3WorkingWindows:
    """Schedule = working windows; meeting type chosen only when booking.

    Rules no longer carry a meeting type; slot duration/buffer come from the
    MeetingType selected at slot/booking time.
    """

    def test_64_create_schedule_without_meeting_type(self, client):
        """POST /schedules creates a working window with no meeting type."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        payload = {
            "psychologist_id": pid,
            "days_of_week": [0, 1],
            "start_time": "09:00",
            "end_time": "17:00",
            "effective_from": "2026-07-01",
        }
        r = client.post(
            "/api/supervisor/schedules", json=payload, headers=_auth(tok_sv)
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert len(data["rules"]) == 2
        assert data["meeting_type_id"] is None
        assert all(ru["meeting_type_id"] is None for ru in data["rules"])

    def test_65_slots_same_window_different_meeting_types(self, client):
        """One working window serves slots for different meeting types."""
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(18)

        with SessionLocal() as db:
            mt30 = _make_meeting_type(db, duration=30, buffer=0)
            mt60 = _make_meeting_type(db, duration=60, buffer=0)
            mt30_id, mt60_id = mt30.id, mt60.id
            # Working window with NO meeting type
            db.add(ScheduleRule(
                psychologist_id=pid, day_of_week=target.weekday(),
                start_time=time(9, 0), end_time=time(12, 0),
                meeting_type_id=None, effective_from=date(2020, 1, 1),
                is_active=True,
            ))
            db.commit()

        def _slots(mt_id):
            r = client.get(
                f"/api/appointments/slots?date={target.isoformat()}"
                f"&meeting_type_id={mt_id}&modality=in_person",
                headers=_auth(tok_s),
            )
            assert r.status_code == 200, r.text
            return r.json()["slots"]

        s30 = _slots(mt30_id)
        s60 = _slots(mt60_id)
        # 09:00–12:00, 30-min step → 6 slots; 60-min step → 3 slots
        assert len(s30) == 6
        assert len(s60) == 3
        assert all(s["duration_minutes"] == 30 for s in s30)
        assert all(s["duration_minutes"] == 60 for s in s60)

    def test_66_legacy_rule_meeting_type_does_not_restrict(self, client):
        """Legacy rule with a meeting_type_id is a window for ANY type."""
        tok_s, sid, _ = _make_user(client, "student")
        tok_p, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        target = _future_date(19)

        with SessionLocal() as db:
            mt_a = _make_meeting_type(db, duration=50, buffer=10)
            mt_b = _make_meeting_type(db, duration=50, buffer=10)
            a_id, b_id = mt_a.id, mt_b.id
            # Rule references meeting type A (legacy data)
            _add_rule(db, pid, target.weekday(), "09:00", "12:00", mt_id=a_id)
            db.commit()

        # Request slots for meeting type B — the legacy rule must NOT restrict
        r = client.get(
            f"/api/appointments/slots?date={target.isoformat()}"
            f"&meeting_type_id={b_id}&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["slots"]) > 0

    def test_67_impact_counts_any_meeting_type_in_window(self, client):
        """Impact counts a future appointment of any type inside the window."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        tok_s, sid = _student_for(client, pid)
        target = _future_date(20)

        with SessionLocal() as db:
            mt_other = _make_meeting_type(db, duration=50, buffer=10)
            mt_other_id = mt_other.id
            db.commit()

        # Working window (no meeting type) 09:00–12:00 on the target weekday
        r = client.post(
            "/api/supervisor/schedules",
            json={
                "psychologist_id": pid,
                "days_of_week": [target.weekday()],
                "start_time": "09:00",
                "end_time": "12:00",
                "effective_from": "2020-01-01",
            },
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        series_id = r.json()["series_id"]

        inside = datetime.combine(
            target, time(10, 0)
        ).replace(tzinfo=MOSCOW_TZ)
        with SessionLocal() as db:
            db.add(Appointment(
                uuid=_uuid.uuid4(), client_id=sid, psychologist_id=pid,
                engagement_id=None, meeting_type_id=mt_other_id,
                starts_at=inside, duration_minutes=50,
                ends_at=inside + timedelta(minutes=50),
                modality="in_person", status="pending_confirmation",
            ))
            db.commit()

        r_imp = client.get(
            f"/api/supervisor/schedules/{series_id}/impact",
            headers=_auth(tok_sv),
        )
        assert r_imp.status_code == 200, r_imp.text
        assert r_imp.json()["future_appointments"] == 1

    def test_68_student_slots_require_meeting_type(self, client):
        """GET /appointments/slots still requires meeting_type_id (422)."""
        tok_s, sid, _ = _make_user(client, "student")
        _, pid, _ = _make_user(client, "psychologist")
        _make_engagement(sid, pid)
        r = client.get(
            f"/api/appointments/slots?date={_future_date(7).isoformat()}"
            f"&modality=in_person",
            headers=_auth(tok_s),
        )
        assert r.status_code == 422

    def test_69_supervisor_slots_require_meeting_type(self, client):
        """GET /supervisor/slots still requires meeting_type_id (422)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        r = client.get(
            f"/api/supervisor/slots?psychologist_id={pid}"
            f"&date={_future_date(7).isoformat()}&modality=in_person",
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422
