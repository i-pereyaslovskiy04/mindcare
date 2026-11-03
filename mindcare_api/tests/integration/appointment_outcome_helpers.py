"""
ADR-035 — общие помощники integration-тестов итогов встреч и встреч клиента
(не тест-модуль). Встречи и walk-in-карточки — прямой insert; пользователи —
create_multi_role_user (integ_-префикс, cleanup conftest; встречи удаляются
каскадом по psychologist_id/client_id, карточки — фикстурой `cards`).
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.db.models import Appointment, UnregisteredStudentCard
from app.db.session import SessionLocal

MSK = timezone(timedelta(hours=3))


def now():
    return datetime.now(MSK)


def make_appt(psy_id, *, client_id=None, card_id=None, status="confirmed",
              starts_at=None, duration=50, ends_at="auto", deleted=False):
    starts_at = starts_at or (now() - timedelta(hours=2))
    if ends_at == "auto":
        ends_at = starts_at + timedelta(minutes=duration)
    with SessionLocal() as db:
        a = Appointment(
            client_id=client_id, unregistered_student_card_id=card_id,
            psychologist_id=psy_id, starts_at=starts_at, duration_minutes=duration,
            ends_at=ends_at, modality="in_person", status=status,
            booking_source="supervisor", created_at=now(), updated_at=now(),
            deleted_at=now() if deleted else None,
        )
        db.add(a)
        db.commit()
        return str(a.uuid)


def appt_row(appt_uuid):
    with SessionLocal() as db:
        a = db.query(Appointment).filter(Appointment.uuid == uuid.UUID(str(appt_uuid))).one()
        db.expunge(a)
        return a


def set_appt(appt_uuid, **values):
    with SessionLocal() as db:
        db.query(Appointment).filter(Appointment.uuid == uuid.UUID(str(appt_uuid))).update(values)
        db.commit()


@pytest.fixture
def cards():
    created = []

    def make(linked_user_id=None):
        with SessionLocal() as db:
            card = UnregisteredStudentCard(
                full_name="integ_card", personal_data_consent=True,
                consent_obtained_at=now(), linked_user_id=linked_user_id,
            )
            db.add(card)
            db.commit()
            created.append(card.id)
            return card.id

    yield make
    if created:
        with SessionLocal() as db:
            db.query(Appointment).filter(
                Appointment.unregistered_student_card_id.in_(created)).delete(
                synchronize_session=False)
            db.query(UnregisteredStudentCard).filter(
                UnregisteredStudentCard.id.in_(created)).delete(synchronize_session=False)
            db.commit()
