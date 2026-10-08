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


# ── VK ID (Stage Social Auth VK-1B): email выбирает пользователь ─────────────

@pytest.fixture
def vk():
    """VK не отдал email — адрес задаётся на init."""
    with registered(FakeProvider("vk", email=None, suggested_name=NAME)) as p:
        yield p


def _vk_ticket(vk) -> str:
    start = oauth_service.start_login("vk")
    outcome = oauth_service.handle_callback(
        "vk", {"state": start.state, "code": vk.issue_code(start.state)}, start.state,
    )
    assert outcome.fragment.get("result") == "registration", outcome.fragment
    assert outcome.fragment.get("step") == "email"
    return outcome.fragment["ticket"]


def _vk_init(ticket, email, capture_emails) -> str:
    oauth_service.registration_init(ticket, email)
    return capture_emails[email][-1]


def _ticket_email(ticket):
    with SessionLocal() as db:
        return db.get(OAuthPendingTicket, oauth_service.sha256_hex(ticket)).email


def test_vk_two_tickets_of_one_subject_with_different_emails_register_once(
    client, vk, test_email, capture_emails,
):
    other_email = "integ_second_" + test_email.split("_", 1)[1]
    first, second = _vk_ticket(vk), _vk_ticket(vk)        # один и тот же VK subject
    code_a = _vk_init(first, test_email, capture_emails)
    code_b = _vk_init(second, other_email, capture_emails)

    results = _run_parallel([
        lambda: _confirm(first, code_a),
        lambda: _confirm(second, code_b),
    ])

    successes, failures = _split(results)
    assert len(successes) == 1 and len(failures) == 1
    assert isinstance(failures[0], OAuthRegistrationError)
    assert failures[0].code == "oauth_identity_already_linked"
    users_a, identities, _ = _counts(test_email, vk.subject)
    users_b, _, _ = _counts(other_email)
    # Ровно один user и одна identity: проигравший не оставил осиротевшего аккаунта.
    assert identities == 1 and users_a + users_b == 1


def test_vk_parallel_confirm_of_one_ticket_registers_exactly_once(
    client, vk, test_email, capture_emails,
):
    ticket = _vk_ticket(vk)
    code = _vk_init(ticket, test_email, capture_emails)

    results = _run_parallel([lambda: _confirm(ticket, code)] * THREADS)

    successes, failures = _split(results)
    assert len(successes) == 1 and len(failures) == THREADS - 1
    assert all(isinstance(exc, OAuthTicketInvalidError) for exc in failures)
    assert _counts(test_email, vk.subject) == (1, 1, 1)


def test_vk_different_subjects_on_one_email_create_one_user(
    client, vk, test_email, capture_emails,
):
    first = _vk_ticket(vk)
    first_subject = vk.subject
    vk.subject = vk.subject + "_other"                    # другой аккаунт VK
    second = _vk_ticket(vk)
    second_subject = vk.subject
    _vk_init(first, test_email, capture_emails)
    _skip_cooldown(test_email)
    code = _vk_init(second, test_email, capture_emails)   # действует последний код

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
        ).count() == 1                                    # проигравший subject не привязан


def test_vk_parallel_email_choice_for_one_ticket_leaves_one_consistent_email(
    client, vk, test_email, capture_emails,
):
    """Параллельный выбор разных адресов одним ticket сериализуется блокировкой
    ticket: итоговый адрес — один из двух, и подтверждает его только свой код."""
    other_email = "integ_second_" + test_email.split("_", 1)[1]
    ticket = _vk_ticket(vk)

    results = _run_parallel([
        lambda: oauth_service.registration_init(ticket, test_email),
        lambda: oauth_service.registration_init(ticket, other_email),
    ])

    successes, failures = _split(results)
    assert len(successes) == 2 and failures == []         # оба кода отправлены
    final = _ticket_email(ticket)
    assert final in {test_email, other_email}
    loser = other_email if final == test_email else test_email

    loser_code, final_code = capture_emails[loser][-1], capture_emails[final][-1]
    if loser_code != final_code:
        with pytest.raises(OAuthRegistrationError) as ei:
            _confirm(ticket, loser_code)                  # код другого адреса не годится
        assert ei.value.code == "otp_invalid"
    _confirm(ticket, final_code)
    assert _counts(final, vk.subject) == (1, 1, 1)
    assert _counts(loser)[0] == 0                         # на втором адресе аккаунта нет


def test_vk_email_change_races_with_confirm(client, vk, test_email, capture_emails):
    """confirm и смена адреса одного ticket идут под одной блокировкой: либо
    регистрация на прежнем адресе состоялась (и смена получает невалидный
    ticket), либо адрес сменился (и код прежнего адреса отклонён). Аккаунт на
    «чужом» адресе с кодом от другого адреса невозможен."""
    other_email = "integ_second_" + test_email.split("_", 1)[1]
    ticket = _vk_ticket(vk)
    code_a = _vk_init(ticket, test_email, capture_emails)

    results = _run_parallel([
        lambda: _confirm(ticket, code_a),
        lambda: oauth_service.registration_init(ticket, other_email),
    ])

    (confirm_kind, confirm_res), (change_kind, change_res) = results
    users_a, identities, _ = _counts(test_email, vk.subject)
    users_b, _, _ = _counts(other_email)
    if confirm_kind == "ok":
        assert (users_a, users_b, identities) == (1, 0, 1)
        if change_kind == "error":
            assert isinstance(change_res, (OAuthTicketInvalidError, OAuthRegistrationError))
    else:
        # Адрес сменился раньше: код от A не подтвердил регистрацию на B.
        assert isinstance(confirm_res, OAuthRegistrationError)
        assert confirm_res.code == "otp_invalid"
        assert (users_a, users_b, identities) == (0, 0, 0)
        assert _ticket_email(ticket) == other_email
