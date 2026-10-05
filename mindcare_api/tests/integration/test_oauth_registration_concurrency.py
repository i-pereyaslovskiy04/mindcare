"""
Stage Social Auth 4 — конкурентность регистрации через провайдера (PostgreSQL).

  * параллельные confirm одного ticket → ровно один аккаунт, identity и сессия;
  * два registration-ticket одного subject → ровно одна identity;
  * два ticket (разные аккаунты провайдера) на один email → ровно один
    пользователь.

Потоки вызывают service напрямую (TestClient не потокобезопасен). Сериализацию
дают блокировки строк ticket и OTP (FOR UPDATE); последняя линия — UNIQUE.
Email и имя приходят из профиля провайдера (FakeProvider.email/suggested_name).
"""
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from app.db.models import (
    OAuthAuthRequest, OAuthPendingTicket, OtpVerification, User, UserOAuthIdentity,
    UserSession,
)
from app.db.session import SessionLocal
from app.oauth import service as oauth_service
from app.oauth.errors import OAuthRegistrationError, OAuthTicketInvalidError
from tests.oauth_fakes import FakeProvider, registered

THREADS = 4
NAME = "Интеграционный Студент"


@pytest.fixture(autouse=True)
def _cleanup_userless_rows(client):
    yield
    with SessionLocal() as db:
        db.query(OAuthAuthRequest).filter(OAuthAuthRequest.user_id.is_(None)).delete()
        db.query(OAuthPendingTicket).filter(OAuthPendingTicket.user_id.is_(None)).delete()
        db.commit()


@pytest.fixture
def fake(test_email):
    with registered(FakeProvider("yandex", email=test_email, suggested_name=NAME)) as p:
        yield p


def _run_parallel(calls):
    barrier = threading.Barrier(len(calls))

    def _task(fn):
        barrier.wait()
        try:
            return ("ok", fn())
        except Exception as exc:   # noqa: BLE001 — собираем исходы потоков
            return ("error", exc)

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(_task, calls))


def _registration_ticket(fake) -> str:
    start = oauth_service.start_login("yandex")
    outcome = oauth_service.handle_callback(
        "yandex", {"state": start.state, "code": fake.issue_code(start.state)}, start.state,
    )
    assert outcome.fragment.get("result") == "registration", outcome.fragment
    return outcome.fragment["ticket"]


def _init(ticket, email, capture_emails) -> str:
    oauth_service.registration_init(ticket)
    return capture_emails[email][-1]


def _confirm(ticket, code):
    return oauth_service.registration_confirm(ticket, code, consent_accepted=True)


def _skip_cooldown(email):
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == email).update(
            {"last_sent_at": datetime.utcnow() - timedelta(seconds=120)})
        db.commit()


def _split(results):
    return ([res for kind, res in results if kind == "ok"],
            [res for kind, res in results if kind == "error"])


def _counts(email=None, subject=None):
    with SessionLocal() as db:
        users = db.query(User).filter(User.email == email).all() if email else []
        identities = db.query(UserOAuthIdentity).filter(
            UserOAuthIdentity.provider_subject == subject).count() if subject else None
        sessions = sum(
            db.query(UserSession).filter(UserSession.user_id == u.id).count() for u in users
        )
        return len(users), identities, sessions


def test_parallel_confirm_of_one_ticket_registers_exactly_once(
    client, fake, test_email, capture_emails,
):
    ticket = _registration_ticket(fake)
    code = _init(ticket, test_email, capture_emails)

    results = _run_parallel([lambda: _confirm(ticket, code)] * THREADS)

    successes, failures = _split(results)
    assert len(successes) == 1 and len(failures) == THREADS - 1
    assert all(isinstance(exc, OAuthTicketInvalidError) for exc in failures)
    assert _counts(test_email, fake.subject) == (1, 1, 1)


def test_two_tickets_of_one_subject_create_one_identity(
    client, fake, test_email, capture_emails,
):
    other_email = "integ_second_" + test_email.split("_", 1)[1]
    first = _registration_ticket(fake)
    fake.email = other_email                            # профиль провайдера сменил email
    second = _registration_ticket(fake)                 # тот же Yandex subject
    code_a = _init(first, test_email, capture_emails)
    code_b = _init(second, other_email, capture_emails)

    results = _run_parallel([
        lambda: _confirm(first, code_a),
        lambda: _confirm(second, code_b),
    ])

    successes, failures = _split(results)
    assert len(successes) == 1 and len(failures) == 1
    assert isinstance(failures[0], OAuthRegistrationError)
    assert failures[0].code == "oauth_identity_already_linked"
    assert failures[0].status_code == 409
    users_a, identities, _ = _counts(test_email, fake.subject)
    users_b, _, _ = _counts(other_email)
    assert identities == 1 and users_a + users_b == 1   # без осиротевшего пользователя


def test_two_tickets_on_one_email_create_one_user(
    client, fake, test_email, capture_emails,
):
    first = _registration_ticket(fake)
    first_subject = fake.subject
    fake.subject = fake.subject + "_other"              # другой аккаунт провайдера
    second = _registration_ticket(fake)                 # с тем же email
    second_subject = fake.subject
    _init(first, test_email, capture_emails)
    _skip_cooldown(test_email)
    code = _init(second, test_email, capture_emails)    # действует последний код

    results = _run_parallel([
        lambda: _confirm(first, code),
        lambda: _confirm(second, code),
    ])

    successes, failures = _split(results)
    assert len(successes) == 1 and len(failures) == 1
    assert isinstance(failures[0], OAuthRegistrationError)
    assert failures[0].code in {"otp_invalid", "email_already_exists"}
    users, _, sessions = _counts(test_email)
    assert users == 1 and sessions == 1
    with SessionLocal() as db:
        assert db.query(UserOAuthIdentity).filter(
            UserOAuthIdentity.provider_subject.in_([first_subject, second_subject])
        ).count() == 1
