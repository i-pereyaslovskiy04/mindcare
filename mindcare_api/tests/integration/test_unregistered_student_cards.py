"""
Integration tests for unregistered student cards (walk-in subjects) and manual
supervisor booking by card.

An unregistered student card lets supervisor/admin book an appointment for a
person who came in person and has no account yet — WITHOUT creating a fake user.

Coverage:
- supervisor/admin create a card when personal_data_consent=true;
- create rejected without full_name;
- create rejected without consent;
- archive (soft) hides a card from the default list;
- search by name / email / phone;
- supervisor books an appointment by card without an engagement;
- card appointment has client_id NULL, card id set, booking_source/created_by;
- exactly one of student_id / unregistered_student_card_id is required;
- registered-student path still requires an active engagement;
- card appointment blocks the slot for the next booking;
- psychologist appointment list returns the card appointment (with brief);
- a registered student's /api/appointments/my excludes unlinked card appts;
- card-only endpoints are staff-only (student -> 403);
- psychologist can confirm / decline a card appointment (no crash, no notify);
- a registered student cannot cancel an unlinked card appointment (403).

Requires: dev PostgreSQL on alembic head, DATA_ENCRYPTION_KEY in .env.
"""

import uuid as _uuid
from datetime import date, datetime, time, timedelta, timezone

import bcrypt

from app.auth import otp_service
from app.auth import service as auth_service
from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    ChatConversation,
    ChatMessage,
    MeetingType,
    ScheduleRule,
    TherapyEngagement,
    UnregisteredStudentCard,
)

PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))

CARDS_URL = "/api/supervisor/unregistered-student-cards"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(client, role: str):
    """Returns (token, user_id, email)."""
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_usc_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"UscTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
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


def _make_engagement(client_id: int, psychologist_id: int) -> int:
    with SessionLocal() as db:
        eng = TherapyEngagement(
            client_id=client_id,
            psychologist_id=psychologist_id,
            status="active",
        )
        db.add(eng)
        db.commit()
        db.refresh(eng)
        return eng.id


def _future_slot(hours_ahead: float = 40.0) -> datetime:
    msk = datetime.now(MOSCOW_TZ) + timedelta(hours=hours_ahead)
    return msk.replace(minute=0, second=0, microsecond=0)


def _make_meeting_type(db, duration: int = 50, buffer: int = 10) -> MeetingType:
    mt = MeetingType(
        name=f"integ_type_{_uuid.uuid4().hex[:6]}",
        duration_minutes=duration,
        buffer_minutes=buffer,
        allow_in_person=True,
        allow_online=True,
        is_group=False,
        is_active=True,
        is_bookable=True,
        display_order=0,
    )
    db.add(mt)
    db.flush()
    return mt


def _setup_schedule(client):
    """Psychologist with full-week availability + an individual meeting type.

    Returns (psych_token, psych_id, meeting_type_id).
    """
    tok_p, pid, _ = _make_user(client, "psychologist")
    with SessionLocal() as db:
        mt = _make_meeting_type(db)
        mt_id = mt.id
        for dow in range(7):
            db.add(ScheduleRule(
                psychologist_id=pid,
                day_of_week=dow,
                start_time=time(0, 0),
                end_time=time(23, 59),
                meeting_type_id=mt_id,
                effective_from=date(2020, 1, 1),
                is_active=True,
            ))
        db.commit()
    return tok_p, pid, mt_id


def _card_payload(**overrides) -> dict:
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
    return client.post(
        CARDS_URL, json=_card_payload(**overrides), headers=_auth(token)
    )


def _book_card(client, token, *, pid, mt_id, card_id, slot):
    return client.post(
        "/api/supervisor/appointments",
        json={
            "unregistered_student_card_id": card_id,
            "psychologist_id": pid,
            "meeting_type_id": mt_id,
            "starts_at": slot.isoformat(),
            "modality": "in_person",
        },
        headers=_auth(token),
    )


# ─── Card CRUD ────────────────────────────────────────────────────────────────

class TestUnregisteredStudentCardCRUD:

    def test_supervisor_creates_card(self, client):
        """supervisor создаёт карточку при consent=true → 201 + поля."""
        tok_sv, sv_id, _ = _make_user(client, "supervisor")
        suffix = _uuid.uuid4().hex[:8]
        email = f"INTEG_CARD_{suffix}@EXAMPLE.COM"
        r = _create_card(
            client, tok_sv,
            full_name=f"integ_card_{suffix}",
            email=email,
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["personal_data_consent"] is True
        assert data["normalized_email"] == email.lower()
        assert data["created_by"] == sv_id
        assert data["consent_obtained_at"] is not None
        assert data["archived_at"] is None

    def test_admin_creates_card(self, client):
        """admin тоже создаёт карточку (staff-доступ)."""
        tok_admin, _, _ = _make_user(client, "admin")
        r = _create_card(client, tok_admin)
        assert r.status_code == 201, r.text

    def test_create_without_full_name(self, client):
        """Пустой full_name → 422."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        r = client.post(
            CARDS_URL,
            json={"full_name": "   ", "personal_data_consent": True},
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422

    def test_create_without_consent(self, client):
        """personal_data_consent=false → 422 (нет активной карточки без согласия)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        r = _create_card(client, tok_sv, personal_data_consent=False)
        assert r.status_code == 422

    def test_archive_hides_from_default_list(self, client):
        """Архивирование скрывает карточку из дефолтного списка."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        suffix = _uuid.uuid4().hex[:8]
        full_name = f"integ_card_arch_{suffix}"
        r = _create_card(client, tok_sv, full_name=full_name)
        assert r.status_code == 201, r.text
        card_id = r.json()["id"]

        r_arch = client.post(
            f"{CARDS_URL}/{card_id}/archive", headers=_auth(tok_sv)
        )
        assert r_arch.status_code == 200, r_arch.text
        assert r_arch.json()["archived_at"] is not None

        # Default list excludes archived
        r_list = client.get(
            f"{CARDS_URL}?q={full_name}", headers=_auth(tok_sv)
        )
        assert r_list.status_code == 200
        assert all(
            i["id"] != card_id for i in r_list.json()["items"]
        )

        # include_archived=true shows it
        r_arch_list = client.get(
            f"{CARDS_URL}?q={full_name}&include_archived=true",
            headers=_auth(tok_sv),
        )
        ids = [i["id"] for i in r_arch_list.json()["items"]]
        assert card_id in ids

    def test_search_by_name_email_phone(self, client):
        """Поиск находит карточку по ФИО / email / телефону."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        suffix = _uuid.uuid4().hex[:8]
        full_name = f"integ_card_search_{suffix}"
        phone = f"+7999{suffix[:7]}"
        email = f"integ_search_{suffix}@example.com"
        r = _create_card(
            client, tok_sv, full_name=full_name, phone=phone, email=email
        )
        assert r.status_code == 201, r.text
        card_id = r.json()["id"]

        for term in (full_name, email, phone):
            r_s = client.get(
                f"{CARDS_URL}?q={term}", headers=_auth(tok_sv)
            )
            assert r_s.status_code == 200, r_s.text
            ids = [i["id"] for i in r_s.json()["items"]]
            assert card_id in ids, f"not found by term: {term}"


# ─── Access control ───────────────────────────────────────────────────────────

class TestCardAccess:

    def test_student_cannot_list_cards(self, client):
        """Студент не имеет доступа к карточкам (403)."""
        tok_s, _, _ = _make_user(client, "student")
        r = client.get(CARDS_URL, headers=_auth(tok_s))
        assert r.status_code == 403

    def test_staff_can_list_cards(self, client):
        """supervisor и admin видят список (200)."""
        for role in ("supervisor", "admin"):
            tok, _, _ = _make_user(client, role)
            r = client.get(CARDS_URL, headers=_auth(tok))
            assert r.status_code == 200, f"{role}: {r.text}"


# ─── Booking by card ──────────────────────────────────────────────────────────

class TestSupervisorBookingByCard:

    def test_book_by_card_without_engagement(self, client):
        """Запись по карточке без engagement → 201 + аудит-поля + system msg."""
        tok_sv, sv_id, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        r_card = _create_card(client, tok_sv)
        assert r_card.status_code == 201, r_card.text
        card_id = r_card.json()["id"]

        slot = _future_slot(40)
        r = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card_id, slot=slot
        )
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["status"] == "pending_confirmation"
        assert data["client_id"] is None
        assert data["unregistered_student_card_id"] == card_id
        assert data["booking_source"] == "supervisor"
        assert data["created_by"] == sv_id
        assert data["unregistered_student_card"]["full_name"]
        appt_uuid = data["uuid"]

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

    def test_book_with_both_subjects_rejected(self, client):
        """student_id и card_id одновременно → 422."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid, _ = _make_user(client, "student")
        _make_engagement(sid, pid)
        r_card = _create_card(client, tok_sv)
        card_id = r_card.json()["id"]

        r = client.post(
            "/api/supervisor/appointments",
            json={
                "student_id": sid,
                "unregistered_student_card_id": card_id,
                "psychologist_id": pid,
                "meeting_type_id": mt_id,
                "starts_at": _future_slot(41).isoformat(),
                "modality": "in_person",
            },
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422

    def test_book_with_neither_subject_rejected(self, client):
        """Ни student_id, ни card_id → 422."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)

        r = client.post(
            "/api/supervisor/appointments",
            json={
                "psychologist_id": pid,
                "meeting_type_id": mt_id,
                "starts_at": _future_slot(42).isoformat(),
                "modality": "in_person",
            },
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422

    def test_registered_path_still_requires_engagement(self, client):
        """student_id без active engagement → 422 (не закреплён)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid, _ = _make_user(client, "student")  # no engagement

        r = client.post(
            "/api/supervisor/appointments",
            json={
                "student_id": sid,
                "psychologist_id": pid,
                "meeting_type_id": mt_id,
                "starts_at": _future_slot(43).isoformat(),
                "modality": "in_person",
            },
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422
        assert "закреп" in r.json()["detail"].lower()

    def test_card_appointment_blocks_slot(self, client):
        """Запись по карточке занимает слот → следующая запись 409."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        r_c1 = _create_card(client, tok_sv)
        r_c2 = _create_card(client, tok_sv)
        card1 = r_c1.json()["id"]
        card2 = r_c2.json()["id"]

        slot = _future_slot(44)
        r1 = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card1, slot=slot
        )
        assert r1.status_code == 201, r1.text

        r2 = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card2, slot=slot
        )
        assert r2.status_code == 409

    def test_archived_card_cannot_be_booked(self, client):
        """Архивированную карточку нельзя записать → 422."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        r_card = _create_card(client, tok_sv)
        card_id = r_card.json()["id"]
        client.post(f"{CARDS_URL}/{card_id}/archive", headers=_auth(tok_sv))

        r = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card_id,
            slot=_future_slot(45),
        )
        assert r.status_code == 422


# ─── Card appointment visibility ──────────────────────────────────────────────

class TestCardAppointmentVisibility:

    def test_psychologist_list_returns_card_appointment(self, client):
        """Психолог видит card-appointment с brief и client_id=None."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        suffix = _uuid.uuid4().hex[:8]
        r_card = _create_card(
            client, tok_sv,
            full_name=f"integ_card_vis_{suffix}",
            phone="+70001112233",
            email=f"integ_vis_{suffix}@example.com",
        )
        card_id = r_card.json()["id"]
        r_book = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card_id,
            slot=_future_slot(46),
        )
        assert r_book.status_code == 201, r_book.text
        appt_uuid = r_book.json()["uuid"]

        r = client.get(
            "/api/psychologist/appointments", headers=_auth(tok_p)
        )
        assert r.status_code == 200, r.text
        item = next(
            (i for i in r.json()["items"] if i["uuid"] == appt_uuid), None
        )
        assert item is not None
        assert item["client_id"] is None
        assert item["unregistered_student_card_id"] == card_id
        card = item["unregistered_student_card"]
        assert card["full_name"] == f"integ_card_vis_{suffix}"
        assert card["phone"] == "+70001112233"
        assert card["email"] == f"integ_vis_{suffix}@example.com"

    def test_registered_student_my_excludes_card_appointment(self, client):
        """/api/appointments/my зарегистрированного студента не содержит card-appt."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        tok_s, sid, _ = _make_user(client, "student")
        _make_engagement(sid, pid)

        r_card = _create_card(client, tok_sv)
        card_id = r_card.json()["id"]
        r_book = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card_id,
            slot=_future_slot(47),
        )
        assert r_book.status_code == 201, r_book.text
        appt_uuid = r_book.json()["uuid"]

        r = client.get("/api/appointments/my", headers=_auth(tok_s))
        assert r.status_code == 200
        uuids = [i["uuid"] for i in r.json()["items"]]
        assert appt_uuid not in uuids


# ─── Card appointment lifecycle (confirm / decline / cancel) ──────────────────

class TestCardAppointmentLifecycle:

    def _book(self, client, hours):
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        card_id = _create_card(client, tok_sv).json()["id"]
        r = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card_id,
            slot=_future_slot(hours),
        )
        assert r.status_code == 201, r.text
        return tok_p, r.json()["uuid"]

    def test_psychologist_confirm_card_appointment(self, client):
        """Психолог подтверждает card-appointment → 200 confirmed (без падения)."""
        tok_p, appt_uuid = self._book(client, 48)
        r = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/confirm",
            headers=_auth(tok_p),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "confirmed"
        assert r.json()["client_id"] is None

    def test_psychologist_decline_card_appointment(self, client):
        """Психолог отклоняет card-appointment → 200 declined (без падения)."""
        tok_p, appt_uuid = self._book(client, 49)
        r = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/decline",
            json={"reason": "не подходит"},
            headers=_auth(tok_p),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "declined"

    def test_registered_student_cannot_cancel_card_appointment(self, client):
        """Зарегистрированный студент не может отменить unlinked card-appointment → 403."""
        tok_p, appt_uuid = self._book(client, 50)
        tok_s, _, _ = _make_user(client, "student")
        r = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={},
            headers=_auth(tok_s),
        )
        assert r.status_code == 403


# ─── Stage 2: linking card to account after confirmed registration ────────────

def _unique_email(prefix: str = "integ_link") -> str:
    # Разрешённый домен: эти пользователи регистрируются через register/confirm
    # (guarded email-allowlist). Карточка использует тот же email для linking.
    return f"{prefix}_{_uuid.uuid4().hex[:10]}@donnu.ru"


def _register_and_confirm(client, email: str, name: str = "Integ Linked"):
    """Seed OTP, confirm registration (links cards), log in.

    Returns (session_token, user_id). Uses the service entry point directly so
    the post-commit card-linking runs exactly as in production confirm flow.
    """
    pw_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
    code = otp_service.create_or_update_otp(email, name, pw_hash)
    user = auth_service.register_confirm(
        email=email, code=code, ip="127.0.0.1", user_agent="pytest"
    )
    r = client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"])


def _card_linked_user_id(card_id: int):
    """Return linked_user_id of a card (read inside a session)."""
    with SessionLocal() as db:
        c = (
            db.query(UnregisteredStudentCard)
            .filter(UnregisteredStudentCard.id == card_id)
            .first()
        )
        return c.linked_user_id if c else "MISSING"


def _has_system_message(recipient_id: int, event_key: str) -> bool:
    with SessionLocal() as db:
        conv = (
            db.query(ChatConversation)
            .filter(
                ChatConversation.type == "system",
                ChatConversation.recipient_id == recipient_id,
            )
            .first()
        )
        if conv is None:
            return False
        msg = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.conversation_id == conv.id,
                ChatMessage.event_key == event_key,
            )
            .first()
        )
        return msg is not None


class TestCardAccountLinking:

    def test_confirm_links_card_by_email(self, client):
        """Подтверждение регистрации с email карточки проставляет linked_user_id."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _unique_email("integ_link_basic")
        card_id = _create_card(client, tok_sv, email=email).json()["id"]

        _, uid = _register_and_confirm(client, email)
        assert _card_linked_user_id(card_id) == uid

    def test_link_normalizes_email(self, client):
        """Карточка UPPER@DONNU.RU и user lower@donnu.ru связываются."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        suffix = _uuid.uuid4().hex[:10]
        upper = f"INTEG_LINK_NORM_{suffix}@DONNU.RU"
        card_id = _create_card(client, tok_sv, email=upper).json()["id"]

        _, uid = _register_and_confirm(client, upper.lower())
        assert _card_linked_user_id(card_id) == uid

    def test_card_not_linked_before_confirmation(self, client):
        """Карточка НЕ связывается до подтверждения email; связывается после."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _unique_email("integ_link_pre")
        card_id = _create_card(client, tok_sv, email=email).json()["id"]

        # init only (seed OTP), no confirm yet → card stays unlinked
        pw_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()
        code = otp_service.create_or_update_otp(email, "Integ", pw_hash)
        assert _card_linked_user_id(card_id) is None

        # confirm → now linked
        auth_service.register_confirm(
            email=email, code=code, ip="127.0.0.1", user_agent="pytest"
        )
        assert _card_linked_user_id(card_id) is not None

    def test_card_not_linked_by_phone(self, client):
        """Карточка НЕ связывается по телефону (только по подтверждённому email)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        card_email = _unique_email("integ_link_cardmail")
        card_id = _create_card(
            client, tok_sv, email=card_email, phone="+79991234567"
        ).json()["id"]

        # Register a DIFFERENT email — registration has no phone anyway.
        _register_and_confirm(client, _unique_email("integ_link_other"))
        assert _card_linked_user_id(card_id) is None

    def test_already_linked_card_not_relinked(self, client):
        """Карточка, привязанная к другому user, НЕ перепривязывается."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, owner_id = _register_and_confirm(
            client, _unique_email("integ_link_owner")
        )
        email = _unique_email("integ_link_shared")
        card_id = _create_card(client, tok_sv, email=email).json()["id"]

        # Manually link the card to the existing owner.
        with SessionLocal() as db:
            c = (
                db.query(UnregisteredStudentCard)
                .filter(UnregisteredStudentCard.id == card_id)
                .first()
            )
            c.linked_user_id = owner_id
            db.commit()

        # A new user registers with the card's email — must NOT steal the link.
        _, new_id = _register_and_confirm(client, email)
        assert new_id != owner_id
        assert _card_linked_user_id(card_id) == owner_id

    def test_multiple_unlinked_cards_same_email_all_linked(self, client):
        """Несколько unlinked карточек с одним email связываются с новым user."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _unique_email("integ_link_multi")
        c1 = _create_card(client, tok_sv, email=email).json()["id"]
        c2 = _create_card(client, tok_sv, email=email).json()["id"]

        _, uid = _register_and_confirm(client, email)
        assert _card_linked_user_id(c1) == uid
        assert _card_linked_user_id(c2) == uid


class TestLinkedCardAppointments:

    def _book_card_appt(self, client, email, hours=40):
        """Walk-in scenario: supervisor books a card appointment before the
        student registers. Returns (psych_token, pid, card_id, appt_uuid)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)
        card_id = _create_card(client, tok_sv, email=email).json()["id"]
        r = _book_card(
            client, tok_sv, pid=pid, mt_id=mt_id, card_id=card_id,
            slot=_future_slot(hours),
        )
        assert r.status_code == 201, r.text
        return tok_p, pid, card_id, r.json()["uuid"]

    def test_my_shows_linked_card_appointment(self, client):
        """После привязки студент видит card-appointment в /api/appointments/my."""
        email = _unique_email("integ_link_my")
        _, _, card_id, appt_uuid = self._book_card_appt(client, email)
        tok_s, _ = _register_and_confirm(client, email)

        r = client.get("/api/appointments/my", headers=_auth(tok_s))
        assert r.status_code == 200, r.text
        item = next(
            (i for i in r.json()["items"] if i["uuid"] == appt_uuid), None
        )
        assert item is not None
        assert item["client_id"] is None
        assert item["unregistered_student_card_id"] == card_id
        assert item["unregistered_student_card"]["full_name"]

    def test_my_excludes_unlinked_card_appointment(self, client):
        """/my не показывает unlinked card-appointment."""
        email = _unique_email("integ_link_unlinked")
        _, _, _, appt_uuid = self._book_card_appt(client, email)
        # Different user registers; the card (email) stays unlinked.
        tok_other, _ = _register_and_confirm(
            client, _unique_email("integ_link_nobody")
        )
        r = client.get("/api/appointments/my", headers=_auth(tok_other))
        uuids = [i["uuid"] for i in r.json()["items"]]
        assert appt_uuid not in uuids

    def test_my_excludes_card_linked_to_other_user(self, client):
        """/my не показывает card-appointment, привязанный к другому user."""
        email = _unique_email("integ_link_owned")
        _, _, _, appt_uuid = self._book_card_appt(client, email)
        _register_and_confirm(client, email)  # links card to this owner
        tok_other, _ = _register_and_confirm(
            client, _unique_email("integ_link_stranger")
        )
        r = client.get("/api/appointments/my", headers=_auth(tok_other))
        uuids = [i["uuid"] for i in r.json()["items"]]
        assert appt_uuid not in uuids

    def test_linked_student_can_cancel_card_appointment(self, client):
        """Привязанный студент может отменить linked card-appointment (до дня)."""
        email = _unique_email("integ_link_cancel")
        _, _, _, appt_uuid = self._book_card_appt(client, email, hours=24 * 5)
        tok_s, _ = _register_and_confirm(client, email)

        r = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={"reason": "не смогу"},
            headers=_auth(tok_s),
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "cancelled"

    def test_other_user_cannot_cancel_linked_card_appointment(self, client):
        """Чужой user не может отменить card-appointment, привязанный к другому → 403."""
        email = _unique_email("integ_link_cancel_other")
        _, _, _, appt_uuid = self._book_card_appt(client, email, hours=24 * 5)
        _register_and_confirm(client, email)  # links to owner
        tok_other, _ = _register_and_confirm(
            client, _unique_email("integ_link_intruder")
        )
        r = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={},
            headers=_auth(tok_other),
        )
        assert r.status_code == 403

    def test_confirmed_linked_card_cancellation_notifies_psychologist(self, client):
        """Отмена подтверждённой linked card-записи уведомляет психолога."""
        email = _unique_email("integ_link_confcancel")
        tok_p, pid, _, appt_uuid = self._book_card_appt(
            client, email, hours=24 * 5
        )
        tok_s, _ = _register_and_confirm(client, email)

        r_conf = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/confirm",
            headers=_auth(tok_p),
        )
        assert r_conf.status_code == 200, r_conf.text

        r_cancel = client.patch(
            f"/api/appointments/{appt_uuid}/cancel",
            json={"reason": "передумал"},
            headers=_auth(tok_s),
        )
        assert r_cancel.status_code == 200, r_cancel.text
        assert r_cancel.json()["status"] == "cancelled"
        assert _has_system_message(
            pid, f"appointment_cancelled:{appt_uuid}"
        )

    def test_psychologist_confirm_notifies_linked_user(self, client):
        """После привязки confirm card-записи шлёт system message linked user."""
        email = _unique_email("integ_link_confnotify")
        tok_p, _, _, appt_uuid = self._book_card_appt(client, email)
        _, uid = _register_and_confirm(client, email)

        r = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/confirm",
            headers=_auth(tok_p),
        )
        assert r.status_code == 200, r.text
        assert _has_system_message(uid, f"appointment_confirmed:{appt_uuid}")

    def test_psychologist_decline_notifies_linked_user(self, client):
        """После привязки decline card-записи шлёт system message linked user."""
        email = _unique_email("integ_link_decnotify")
        tok_p, _, _, appt_uuid = self._book_card_appt(client, email)
        _, uid = _register_and_confirm(client, email)

        r = client.patch(
            f"/api/psychologist/appointments/{appt_uuid}/decline",
            json={"reason": "не подходит"},
            headers=_auth(tok_p),
        )
        assert r.status_code == 200, r.text
        assert _has_system_message(uid, f"appointment_declined:{appt_uuid}")
