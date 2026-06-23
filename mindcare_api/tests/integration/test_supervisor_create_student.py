"""
Integration tests for POST /api/supervisor/students — создание полноценного
зарегистрированного аккаунта студента силами admin/supervisor.

Покрывает:
- доступ: supervisor/admin → 201; psychologist/student → 403;
- duplicate email → 409;
- создаётся User с ролью student (is_active=True);
- временный пароль возвращается в ответе, но в БД только bcrypt-хеш;
- личное согласие (consent_records) фиксируется (accepted=True) — ФЗ-152;
- personal_data_consent отсутствует/False → 422;
- psychologist_id → создаётся active TherapyEngagement; студент пригоден для
  ручной supervisor-записи через student_id;
- невалидный/неактивный/не-психолог psychologist_id → ошибка, студент-orphan
  не создаётся;
- карточка незарегистрированного студента с matching normalized email и
  linked_user_id IS NULL → привязывается; уже привязанная к другому user — нет;
  без matching email — нет;
- failure-injection: сбой ConsentRecord/AuditLog откатывает всю core-транзакцию
  (ни User, ни TherapyEngagement не создаются).

Requires: dev PostgreSQL на alembic head, DATA_ENCRYPTION_KEY в .env,
seed с политиками privacy_policy и data_processing.
"""

import uuid as _uuid
from datetime import date, datetime, time, timedelta, timezone

import bcrypt
import pytest

from app.auth import storage as auth_storage
from app.db.session import SessionLocal
from app.db.models import (
    ConsentRecord,
    MeetingType,
    Role,
    ScheduleRule,
    TherapyEngagement,
    UnregisteredStudentCard,
    User,
    UserRole,
)

URL = "/api/supervisor/students"
PASSWORD = "SecurePass42!"
MOSCOW_TZ = timezone(timedelta(hours=3))


# ─── User / auth helpers ──────────────────────────────────────────────────────

def _make_user(client, role: str):
    """Создаёт пользователя нужной роли и логинит. Returns (token, id, email)."""
    suffix = _uuid.uuid4().hex[:10]
    email = f"integ_scs_{role}_{suffix}@example.com"
    user = auth_storage.save_user({
        "name": f"ScsTest {role.capitalize()} {_uuid.uuid4().hex[:6]}",
        "email": email,
        "hashed_password": bcrypt.hashpw(
            PASSWORD.encode(), bcrypt.gensalt()
        ).decode(),
        "role": role,
    })
    r = client.post(
        "/api/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text
    return r.json()["session_token"], int(user["id"]), email


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _email() -> str:
    return f"integ_{_uuid.uuid4().hex[:12]}@example.com"


def _body(email: str, **over) -> dict:
    body = {
        "full_name": "Студент Тестовый",
        "email": email,
        "personal_data_consent": True,
    }
    body.update(over)
    return body


# ─── DB inspection helpers ────────────────────────────────────────────────────

def _user_row(email: str):
    """Возвращает dict с полями созданного пользователя или None."""
    with SessionLocal() as db:
        u = (
            db.query(User)
            .filter(User.email == email.strip().lower())
            .first()
        )
        if not u:
            return None
        role = (
            db.query(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .filter(UserRole.user_id == u.id)
            .scalar()
        )
        return {
            "id": u.id,
            "role": role,
            "is_active": u.is_active,
            "password_hash": u.password_hash,
            "deleted_at": u.deleted_at,
        }


def _consents(user_id: int) -> list:
    with SessionLocal() as db:
        return [
            r.accepted
            for r in db.query(ConsentRecord.accepted)
            .filter(ConsentRecord.user_id == user_id)
            .all()
        ]


def _active_engagement(client_id: int):
    with SessionLocal() as db:
        eng = (
            db.query(TherapyEngagement)
            .filter(
                TherapyEngagement.client_id == client_id,
                TherapyEngagement.status == "active",
                TherapyEngagement.ended_at.is_(None),
            )
            .first()
        )
        if not eng:
            return None
        return {
            "id": eng.id,
            "psychologist_id": eng.psychologist_id,
            "status": eng.status,
            "ended_at": eng.ended_at,
        }


def _deactivate(user_id: int) -> None:
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update({"is_active": False})
        db.commit()


# ─── Unregistered student card helpers ────────────────────────────────────────

def _make_card(email, linked_user_id=None) -> int:
    with SessionLocal() as db:
        card = UnregisteredStudentCard(
            full_name=f"integ_card_{_uuid.uuid4().hex[:8]}",
            email=email,
            normalized_email=(email.strip().lower() if email else None),
            personal_data_consent=True,
            linked_user_id=linked_user_id,
        )
        db.add(card)
        db.commit()
        db.refresh(card)
        return card.id


def _card_linked_id(card_id: int):
    with SessionLocal() as db:
        return (
            db.query(UnregisteredStudentCard.linked_user_id)
            .filter(UnregisteredStudentCard.id == card_id)
            .scalar()
        )


# ─── Schedule helpers (for «bookable via student_id») ─────────────────────────

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


def _add_rule(db, pid: int, dow: int, start: str, end: str, mt_id: int = None):
    db.add(ScheduleRule(
        psychologist_id=pid,
        day_of_week=dow,
        start_time=time.fromisoformat(start),
        end_time=time.fromisoformat(end),
        meeting_type_id=mt_id,
        effective_from=date(2020, 1, 1),
        is_active=True,
    ))


def _setup_schedule(client):
    """Психолог с круглонедельной доступностью + индивидуальный тип встречи."""
    tok_p, pid, _ = _make_user(client, "psychologist")
    with SessionLocal() as db:
        mt = _make_meeting_type(db)
        mt_id = mt.id
        for dow in range(7):
            _add_rule(db, pid, dow, "00:00", "23:59", mt_id=mt_id)
        db.commit()
    return tok_p, pid, mt_id


def _future_slot(hours_ahead: float = 40.0) -> datetime:
    msk = datetime.now(MOSCOW_TZ) + timedelta(hours=hours_ahead)
    return msk.replace(minute=0, second=0, microsecond=0)


# ─── Access control ───────────────────────────────────────────────────────────

class TestAccess:

    def test_supervisor_creates_student_201(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        r = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["email"] == email
        assert data["role"] == "student"
        assert data["is_active"] is True
        assert data["temporary_password"]
        assert data["engagement"] is None
        assert data["linked_cards_count"] == 0

    def test_admin_creates_student_201(self, client):
        tok_admin, _, _ = _make_user(client, "admin")
        r = client.post(URL, json=_body(_email()), headers=_auth(tok_admin))
        assert r.status_code == 201, r.text
        assert r.json()["role"] == "student"

    def test_psychologist_forbidden_403(self, client):
        tok_p, _, _ = _make_user(client, "psychologist")
        email = _email()
        r = client.post(URL, json=_body(email), headers=_auth(tok_p))
        assert r.status_code == 403
        assert _user_row(email) is None

    def test_student_forbidden_403(self, client):
        tok_s, _, _ = _make_user(client, "student")
        email = _email()
        r = client.post(URL, json=_body(email), headers=_auth(tok_s))
        assert r.status_code == 403
        assert _user_row(email) is None


# ─── Core creation invariants ─────────────────────────────────────────────────

class TestCreation:

    def test_created_user_has_student_role(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        r = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r.status_code == 201, r.text
        row = _user_row(email)
        assert row is not None
        assert row["role"] == "student"
        assert row["is_active"] is True
        assert row["deleted_at"] is None

    def test_temp_password_returned_but_only_hash_stored(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        r = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r.status_code == 201, r.text
        temp = r.json()["temporary_password"]
        row = _user_row(email)
        # В БД — bcrypt-хеш, не plaintext.
        assert row["password_hash"] != temp
        assert row["password_hash"].startswith("$2")
        assert bcrypt.checkpw(temp.encode(), row["password_hash"].encode())

    def test_consent_records_created(self, client):
        """ФЗ-152: личное согласие субъекта зафиксировано (privacy + data_processing)."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        r = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r.status_code == 201, r.text
        accepted = _consents(_user_row(email)["id"])
        assert len(accepted) >= 2
        assert all(accepted)

    def test_duplicate_email_409(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        r1 = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r1.status_code == 201, r1.text
        r2 = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r2.status_code == 409, r2.text

    def test_missing_consent_422(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        body = _body(email)
        del body["personal_data_consent"]
        r = client.post(URL, json=body, headers=_auth(tok_sv))
        assert r.status_code == 422
        assert _user_row(email) is None

    def test_consent_false_422(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        r = client.post(
            URL, json=_body(email, personal_data_consent=False),
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422
        assert _user_row(email) is None


# ─── Psychologist assignment ──────────────────────────────────────────────────

class TestWithPsychologist:

    def test_creates_active_engagement(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        email = _email()
        r = client.post(
            URL, json=_body(email, psychologist_id=pid, primary_concern="тревога"),
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        assert r.json()["engagement"]["status"] == "active"

        row = _user_row(email)
        eng = _active_engagement(row["id"])
        assert eng is not None
        assert eng["psychologist_id"] == pid
        assert eng["ended_at"] is None

    def test_psychologist_not_found_404_no_orphan(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        r = client.post(
            URL, json=_body(email, psychologist_id=999_999_999),
            headers=_auth(tok_sv),
        )
        assert r.status_code == 404, r.text
        assert _user_row(email) is None  # студент-orphan не создан

    def test_not_a_psychologist_400_no_orphan(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, other_student_id, _ = _make_user(client, "student")
        email = _email()
        r = client.post(
            URL, json=_body(email, psychologist_id=other_student_id),
            headers=_auth(tok_sv),
        )
        assert r.status_code == 400, r.text
        assert _user_row(email) is None

    def test_inactive_psychologist_422_no_orphan(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        _deactivate(pid)
        email = _email()
        r = client.post(
            URL, json=_body(email, psychologist_id=pid),
            headers=_auth(tok_sv),
        )
        assert r.status_code == 422, r.text
        assert _user_row(email) is None

    def test_assigned_student_bookable_via_student_id(self, client):
        """После создания с psychologist_id студент пригоден для ручной записи."""
        tok_sv, _, _ = _make_user(client, "supervisor")
        tok_p, pid, mt_id = _setup_schedule(client)

        email = _email()
        r = client.post(
            URL, json=_body(email, psychologist_id=pid),
            headers=_auth(tok_sv),
        )
        assert r.status_code == 201, r.text
        sid = _user_row(email)["id"]

        slot = _future_slot(40)
        rb = client.post(
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
        assert rb.status_code == 201, rb.text
        assert rb.json()["client_id"] == sid
        assert rb.json()["status"] == "pending_confirmation"


# ─── Unregistered card linking ────────────────────────────────────────────────

class TestCardLinking:

    def test_matching_card_gets_linked(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()
        card_id = _make_card(email, linked_user_id=None)

        r = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r.status_code == 201, r.text
        new_id = _user_row(email)["id"]
        assert _card_linked_id(card_id) == new_id
        assert r.json()["linked_cards_count"] >= 1

    def test_card_linked_to_other_user_not_relinked(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, other_id, _ = _make_user(client, "student")
        email = _email()
        card_id = _make_card(email, linked_user_id=other_id)

        r = client.post(URL, json=_body(email), headers=_auth(tok_sv))
        assert r.status_code == 201, r.text
        # Карточка остаётся за прежним пользователем.
        assert _card_linked_id(card_id) == other_id

    def test_card_without_matching_email_not_linked(self, client):
        tok_sv, _, _ = _make_user(client, "supervisor")
        card_id = _make_card(_email(), linked_user_id=None)

        r = client.post(URL, json=_body(_email()), headers=_auth(tok_sv))
        assert r.status_code == 201, r.text
        assert _card_linked_id(card_id) is None


# ─── Atomicity (failure injection on real DB) ─────────────────────────────────

class TestAtomicity:

    def test_consent_failure_rolls_back_user(self, client, monkeypatch):
        tok_sv, _, _ = _make_user(client, "supervisor")
        email = _email()

        class Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("consent write failed (test)")

        monkeypatch.setattr("app.supervisor.storage.ConsentRecord", Boom)
        with pytest.raises(RuntimeError, match="consent write failed"):
            client.post(URL, json=_body(email), headers=_auth(tok_sv))

        assert _user_row(email) is None

    def test_audit_failure_rolls_back_user_and_engagement(self, client, monkeypatch):
        tok_sv, _, _ = _make_user(client, "supervisor")
        _, pid, _ = _make_user(client, "psychologist")
        email = _email()

        class Boom:
            def __init__(self, *a, **kw):
                raise RuntimeError("audit write failed (test)")

        monkeypatch.setattr("app.supervisor.storage.AuditLog", Boom)
        with pytest.raises(RuntimeError, match="audit write failed"):
            client.post(
                URL, json=_body(email, psychologist_id=pid),
                headers=_auth(tok_sv),
            )

        # Ни студент, ни engagement не созданы — вся транзакция откатилась.
        assert _user_row(email) is None
