"""
Stage Social Auth 4 (UX hotfix) — регистрация через провайдера end-to-end
(FakeProvider): callback неизвестной identity → registration-ticket с email и
именем ИЗ ПРОФИЛЯ провайдера → init {ticket} (OTP на этот email) → confirm
{ticket, code, consent_accepted: true} → аккаунт без пароля + identity +
обычная сессия.

Проверяются: email/имя только из ticket (клиент их не передаёт), consent gate на
confirm, отказ для занятого и soft-deleted email без привязки/реактивации,
отсутствие обычного allowlist доменов у social-регистрации при неизменной
политике обычной регистрации, изоляция OTP между потоками, атомарность confirm
(failure-injection на реальной БД), аудит и отсутствие секретов в журнале и логах.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import service as auth_service
from app.auth.otp_service import MAX_ATTEMPTS
from app.auth.storage import RegistrationDataError
from app.db.models import (
    AllowedEmailDomain, AuthLog, ConsentRecord, OAuthAuthRequest, OAuthPendingTicket,
    OtpVerification, User, UserOAuthIdentity, UserRole, UserSession,
)
from app.db.session import SessionLocal
from app.oauth import service as oauth_service
from app.oauth import storage as oauth_storage
from tests.integration.conftest import create_test_user
from tests.oauth_fakes import FakeProvider, registered, state_from_authorize_url

COOKIE = "mindcare_oauth_state"
NAME = "Интеграционный Студент"
INIT_URL = "/api/auth/oauth/registration/init"
CONFIRM_URL = "/api/auth/oauth/registration/confirm"
EMAIL_EXISTS = "Аккаунт с таким email уже существует. Войдите по email и паролю."
PASSWORD = "SecurePass42!"


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolate(client):
    client.cookies.clear()
    yield
    client.cookies.clear()
    with SessionLocal() as db:
        db.query(OAuthAuthRequest).filter(OAuthAuthRequest.user_id.is_(None)).delete()
        db.query(OAuthPendingTicket).filter(OAuthPendingTicket.user_id.is_(None)).delete()
        db.commit()


@pytest.fixture
def fake(test_email):
    """Провайдер отдаёт email (разрешённый домен) и имя."""
    with registered(FakeProvider("yandex", email=test_email, suggested_name=NAME)) as p:
        yield p


# ── helpers ──────────────────────────────────────────────────────────────────

def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _callback_fragment(client, provider) -> dict:
    r = client.post("/api/auth/oauth/yandex/start")
    assert r.status_code == 200, r.text
    state = state_from_authorize_url(r.json()["authorize_url"])
    client.cookies.clear()
    r = client.get(
        "/api/auth/oauth/yandex/callback",
        params={"state": state, "code": provider.issue_code(state)},
        headers={"Cookie": f"{COOKIE}={state}"}, follow_redirects=False,
    )
    assert r.status_code == 302
    fragment = r.headers["location"].split("#", 1)[1]
    return dict(pair.split("=", 1) for pair in fragment.split("&"))


def _reg_ticket(client, provider) -> str:
    frag = _callback_fragment(client, provider)
    assert frag.get("result") == "registration", frag
    return frag["ticket"]


def _init(client, ticket):
    return client.post(INIT_URL, json={"ticket": ticket})


def _confirm(client, ticket, code, consent=True):
    return client.post(CONFIRM_URL, json={
        "ticket": ticket, "code": code, "consent_accepted": consent,
    })


def _started(client, provider, capture_emails):
    """ticket с отправленным кодом."""
    ticket = _reg_ticket(client, provider)
    r = _init(client, ticket)
    assert r.status_code == 200, r.text
    return ticket, capture_emails[provider.email][-1]


def _ticket_row(ticket):
    with SessionLocal() as db:
        return db.get(OAuthPendingTicket, _sha(ticket))


def _user(email):
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).one_or_none()


def _otp(email):
    with SessionLocal() as db:
        return db.query(OtpVerification).filter(OtpVerification.email == email).one_or_none()


def _identities(subject) -> int:
    with SessionLocal() as db:
        return db.query(UserOAuthIdentity).filter(
            UserOAuthIdentity.provider_subject == subject).count()


def _mark() -> int:
    with SessionLocal() as db:
        return db.query(AuthLog.id).order_by(AuthLog.id.desc()).limit(1).scalar() or 0


def _auth_rows(mark):
    with SessionLocal() as db:
        return db.query(AuthLog).filter(AuthLog.id > mark).order_by(AuthLog.id).all()


def _skip_cooldown(email):
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == email).update(
            {"last_sent_at": datetime.utcnow() - timedelta(seconds=120)})
        db.commit()


def _assert_nothing_created(email, subject):
    assert _user(email) is None
    assert _identities(subject) == 0


# ── CALLBACK: ticket несёт email и имя провайдера ────────────────────────────

def test_callback_ticket_holds_provider_email_and_name(client, fake, test_email):
    fake.email = "  " + test_email.upper() + " "
    ticket = _reg_ticket(client, fake)
    row = _ticket_row(ticket)
    assert (row.kind, row.user_id, row.consumed_at) == ("registration", None, None)
    assert (row.email, row.suggested_name) == (test_email, NAME)   # нормализован
    ttl = row.expires_at - row.created_at        # created_at — часы БД
    assert timedelta(minutes=29) <= ttl <= timedelta(minutes=31)
    _assert_nothing_created(test_email, fake.subject)
    assert _otp(test_email) is None                     # код ещё не отправлен


def test_callback_without_name_uses_email_local_part(client, fake, test_email):
    fake.suggested_name = None
    ticket = _reg_ticket(client, fake)
    assert _ticket_row(ticket).suggested_name == test_email.split("@", 1)[0]


@pytest.mark.parametrize("bad_email", [None, "not-an-email", "a@@b.ru"])
def test_callback_without_usable_email_fails_closed(client, fake, bad_email):
    fake.email = bad_email
    mark = _mark()
    with SessionLocal() as db:
        before = db.query(OAuthPendingTicket).count()

    frag = _callback_fragment(client, fake)

    assert frag == {"error": "oauth_email_required"}
    with SessionLocal() as db:
        assert db.query(OAuthPendingTicket).count() == before
    assert _identities(fake.subject) == 0 and _auth_rows(mark) == []


# ── INIT ─────────────────────────────────────────────────────────────────────

def test_init_sends_otp_to_ticket_email(client, fake, test_email, capture_emails):
    ticket = _reg_ticket(client, fake)
    r = _init(client, ticket)
    assert r.status_code == 200, r.text
    masked = f"{test_email[0]}***@{test_email.split('@', 1)[1]}"
    assert r.json() == {
        "message": "Код подтверждения отправлен на email", "email_masked": masked,
    }
    assert test_email not in r.text
    otp = _otp(test_email)
    assert otp is not None and otp.password_hash is None
    assert list(capture_emails) == [test_email] and len(capture_emails[test_email]) == 1
    row = _ticket_row(ticket)
    assert row.consumed_at is None and row.email == test_email
    _assert_nothing_created(test_email, fake.subject)


@pytest.mark.parametrize("body_patch", [
    {"email": "integ_attacker@donnu.ru"}, {"name": "Подмена"},
    {"consent_accepted": True}, {"provider": "vk"}, {"subject": "x"},
    {"user_id": 1}, {"password": "Secret123"},
])
def test_init_rejects_client_supplied_fields(client, fake, test_email, capture_emails,
                                             body_patch):
    ticket = _reg_ticket(client, fake)
    r = client.post(INIT_URL, json={"ticket": ticket, **body_patch})
    assert r.status_code == 422
    assert capture_emails == {} and _otp(test_email) is None
    assert _ticket_row(ticket).email == test_email      # ticket не изменён


def test_init_invalid_ticket(client, fake, capture_emails):
    r = _init(client, "t" * 43)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert capture_emails == {}


def test_init_expired_ticket(client, fake, capture_emails):
    ticket = _reg_ticket(client, fake)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        db.query(OAuthPendingTicket).filter_by(ticket_hash=_sha(ticket)).update(
            {"created_at": past, "expires_at": past + timedelta(minutes=30)})
        db.commit()
    r = _init(client, ticket)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert capture_emails == {}


def test_init_rejects_login_ticket(client, fake, foreign_test_email, capture_emails):
    user_id = int(create_test_user(foreign_test_email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=user_id, provider="yandex",
                                 provider_subject=fake.subject))
        db.commit()
    frag = _callback_fragment(client, fake)
    assert frag["result"] == "login"
    r = _init(client, frag["ticket"])
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert capture_emails == {}


def test_init_rejects_legacy_ticket_without_email(client, fake, capture_emails):
    """Ticket старого контракта (без email/имени) завершить нельзя."""
    raw = "legacy_" + "x" * 30
    with SessionLocal() as db:
        db.add(OAuthPendingTicket(
            ticket_hash=_sha(raw), kind="registration", provider="yandex",
            provider_subject=fake.subject, user_id=None,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        ))
        db.commit()
    assert _init(client, raw).json()["code"] == "oauth_ticket_invalid"
    assert _confirm(client, raw, "123456").json()["code"] == "oauth_ticket_invalid"
    assert _ticket_row(raw).consumed_at is None and capture_emails == {}


def test_init_existing_active_email_is_refused_without_link(client, fake, test_email,
                                                            capture_emails):
    existing = create_test_user(test_email)
    ticket = _reg_ticket(client, fake)
    r = _init(client, ticket)
    assert r.status_code == 409
    assert r.json() == {"detail": EMAIL_EXISTS, "code": "email_already_exists"}
    assert _ticket_row(ticket).consumed_at is not None   # email ticket не меняется
    assert capture_emails == {} and _otp(test_email) is None
    assert _identities(fake.subject) == 0             # не привязано к существующему
    with SessionLocal() as db:
        assert db.query(UserOAuthIdentity).filter_by(user_id=int(existing["id"])).count() == 0
        assert db.query(User).filter(User.email == test_email).count() == 1


def test_init_soft_deleted_email_is_refused_without_reactivation(client, fake, test_email,
                                                                 capture_emails):
    user_id = int(create_test_user(test_email)["id"])
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update(
            {"deleted_at": datetime.now(timezone.utc), "is_active": False})
        db.commit()
    ticket = _reg_ticket(client, fake)
    r = _init(client, ticket)
    assert r.status_code == 409
    # Тот же текст, что для активного аккаунта: состояние не раскрывается.
    assert r.json() == {"detail": EMAIL_EXISTS, "code": "email_already_exists"}
    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user.deleted_at is not None and user.is_active is False   # не реактивирован
    assert _identities(fake.subject) == 0 and capture_emails == {}


def test_init_identity_appeared_burns_ticket(client, fake, foreign_test_email,
                                             capture_emails):
    ticket = _reg_ticket(client, fake)
    other = int(create_test_user(foreign_test_email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=other, provider="yandex",
                                 provider_subject=fake.subject))
        db.commit()
    r = _init(client, ticket)
    assert r.status_code == 409 and r.json()["code"] == "oauth_identity_already_linked"
    assert _ticket_row(ticket).consumed_at is not None and capture_emails == {}
    assert _init(client, ticket).status_code == 400   # сожжён


def test_init_resend_after_cooldown(client, fake, test_email, capture_emails):
    ticket = _reg_ticket(client, fake)
    assert _init(client, ticket).status_code == 200
    expires = _ticket_row(ticket).expires_at

    r = _init(client, ticket)                         # сразу — cooldown
    assert r.status_code == 429 and r.json()["code"] == "otp_cooldown"
    assert len(capture_emails[test_email]) == 1

    _skip_cooldown(test_email)
    assert _init(client, ticket).status_code == 200
    assert len(capture_emails[test_email]) == 2
    assert _ticket_row(ticket).expires_at == expires  # TTL не продлевается
    # Действует последний код.
    first, last = capture_emails[test_email]
    if first != last:
        assert _confirm(client, ticket, first).json()["code"] == "otp_invalid"
    assert _confirm(client, ticket, last).status_code == 200


def test_init_smtp_failure_keeps_committed_state(client, fake, test_email, monkeypatch):
    def _smtp_down(*args, **kwargs):
        raise RuntimeError("SMTP SECRET detail")

    monkeypatch.setattr("app.services.email_service.send_email", _smtp_down)
    ticket = _reg_ticket(client, fake)
    r = _init(client, ticket)
    assert r.status_code == 500 and r.json()["code"] == "email_delivery_failed"
    assert "SECRET" not in r.text
    # Состояние БД закоммичено ДО отправки: OTP создан, ticket годен.
    assert _otp(test_email) is not None and _ticket_row(ticket).consumed_at is None
    monkeypatch.undo()
    assert _init(client, ticket).status_code == 429   # повтор — под cooldown


def test_init_rate_limited_per_ticket_digest(client, fake, test_email, capture_emails):
    from app.core import rate_limit

    ticket = _reg_ticket(client, fake)
    codes = []
    for _ in range(4):
        codes.append(_init(client, ticket).status_code)
        _skip_cooldown(test_email)
    assert codes == [200, 200, 200, 429]
    assert len(capture_emails[test_email]) == 3
    keys = list(rate_limit._limiter._hits)
    assert f"oauth_registration_init:ticket:{_sha(ticket)}" in keys
    assert all(ticket not in k for k in keys)         # raw ticket — никогда


# ── allowlist доменов: social — без него, обычная регистрация — с ним ───────

def test_social_registration_ignores_ordinary_domain_allowlist(
    client, fake, foreign_test_email, capture_emails, reset_email_domains,
):
    domain = foreign_test_email.split("@", 1)[1]
    with SessionLocal() as db:
        assert db.query(AllowedEmailDomain).filter(
            AllowedEmailDomain.domain == domain, AllowedEmailDomain.is_active.is_(True),
        ).count() == 0                                # домен НЕ разрешён
    fake.email = foreign_test_email

    ticket, code = _started(client, fake, capture_emails)
    r = _confirm(client, ticket, code)

    assert r.status_code == 200, r.text
    user = _user(foreign_test_email)
    assert user is not None and user.password_hash is None
    assert _identities(fake.subject) == 1


def test_domain_disabled_between_init_and_confirm_does_not_block_social(
    client, fake, test_email, capture_emails, reset_email_domains,
):
    ticket, code = _started(client, fake, capture_emails)
    domain = test_email.split("@", 1)[1]
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).filter(AllowedEmailDomain.domain == domain).update(
            {"is_active": False})
        db.commit()
    assert _confirm(client, ticket, code).status_code == 200
    assert _user(test_email) is not None


def test_ordinary_registration_still_enforces_domain_allowlist(
    client, fake, foreign_test_email, capture_emails, reset_email_domains,
):
    """Регрессия: social-исключение не ослабило обычную регистрацию."""
    r = client.post("/api/auth/register/init", json={
        "name": "Обычная Регистрация", "email": foreign_test_email, "password": PASSWORD,
    })
    assert r.status_code == 422
    assert capture_emails == {} and _otp(foreign_test_email) is None
    assert _user(foreign_test_email) is None


# ── CONFIRM: consent gate ────────────────────────────────────────────────────

@pytest.mark.parametrize("consent", [False, None, "true", 1, "missing"])
def test_confirm_without_literal_consent_creates_nothing(client, fake, test_email,
                                                         capture_emails, consent):
    ticket, code = _started(client, fake, capture_emails)
    body = {"ticket": ticket, "code": code}
    if consent != "missing":
        body["consent_accepted"] = consent
    mark = _mark()

    r = client.post(CONFIRM_URL, json=body)

    assert r.status_code == 422
    _assert_nothing_created(test_email, fake.subject)
    assert _otp(test_email).attempts == 0             # код не проверялся
    assert _ticket_row(ticket).consumed_at is None and _auth_rows(mark) == []
    with SessionLocal() as db:
        assert db.query(ConsentRecord).join(User, ConsentRecord.user_id == User.id).filter(
            User.email == test_email).count() == 0
    assert _confirm(client, ticket, code).status_code == 200   # с согласием проходит


def test_service_consent_gate_is_independent_of_schema(client, fake, test_email,
                                                       capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    with pytest.raises(oauth_service.OAuthRegistrationError) as ei:
        oauth_service.registration_confirm(ticket, code, consent_accepted=False)
    assert ei.value.code == "consent_required" and ei.value.status_code == 422
    _assert_nothing_created(test_email, fake.subject)
    assert _otp(test_email).attempts == 0


@pytest.mark.parametrize("body_patch", [
    {"email": "integ_attacker@donnu.ru"}, {"name": "Подмена"}, {"provider": "vk"},
])
def test_confirm_rejects_client_supplied_fields(client, fake, test_email, capture_emails,
                                                body_patch):
    ticket, code = _started(client, fake, capture_emails)
    r = client.post(CONFIRM_URL, json={
        "ticket": ticket, "code": code, "consent_accepted": True, **body_patch,
    })
    assert r.status_code == 422
    _assert_nothing_created(test_email, fake.subject)


# ── CONFIRM: успех ───────────────────────────────────────────────────────────

def test_confirm_creates_passwordless_student_with_identity_and_session(
    client, fake, test_email, capture_emails,
):
    ticket, code = _started(client, fake, capture_emails)
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"session_token", "expires_at", "roles", "role"}
    assert body["roles"] == ["student"] and body["role"] == "student"
    assert r.headers["cache-control"] == "no-store"

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == test_email).one()
        assert user.password_hash is None                 # без пароля и без заглушки
        assert user.full_name == NAME and user.deleted_at is None   # имя провайдера
        assert user.last_login is not None
        roles = db.query(UserRole).filter(UserRole.user_id == user.id).count()
        assert roles == 1
        consents = db.query(ConsentRecord).filter(ConsentRecord.user_id == user.id).all()
        assert len(consents) == len(auth_service.REQUIRED_CONSENTS)
        assert all(c.accepted and c.ip_address and c.user_agent for c in consents)
        identity = db.query(UserOAuthIdentity).filter_by(user_id=user.id).one()
        assert (identity.provider, identity.provider_subject) == ("yandex", fake.subject)
        assert identity.last_login_at is not None
        sessions = db.query(UserSession).filter(UserSession.user_id == user.id).all()
        assert len(sessions) == 1 and not sessions[0].is_revoked
        assert sessions[0].id == _sha(body["session_token"])   # в БД — hash
        user_id = user.id
    assert _ticket_row(ticket).consumed_at is not None
    assert _otp(test_email) is None

    headers = {"Authorization": f"Bearer {body['session_token']}"}
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == test_email and me["has_password"] is False
    assert me["name"] == NAME

    rows = _auth_rows(mark)
    assert [(x.event, x.auth_method, x.success) for x in rows] == [
        ("registration_succeeded", "yandex", True), ("login", "yandex", True),
    ]
    assert rows[0].user_id == user_id and rows[0].user_email == test_email
    assert rows[1].session_id == _sha(body["session_token"])
    blob = " ".join(
        f"{x.event}|{x.user_email}|{x.failure_reason}|{x.session_id}|{x.user_agent}"
        for x in rows
    )
    for secret in (ticket, _sha(ticket), code, fake.subject, NAME, body["session_token"]):
        assert secret not in blob


def test_passwordless_account_password_login_is_generic_401(client, fake, test_email,
                                                           capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    assert _confirm(client, ticket, code).status_code == 200
    r = client.post("/api/auth/login", json={"email": test_email, "password": "Whatever42!"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Неверный email или пароль"


def test_second_callback_after_registration_is_plain_login(client, fake, capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    assert _confirm(client, ticket, code).status_code == 200
    frag = _callback_fragment(client, fake)
    assert frag["result"] == "login"
    r = client.post("/api/auth/oauth/complete", json={"ticket": frag["ticket"]})
    assert r.status_code == 200


def test_confirm_replay_is_rejected(client, fake, test_email, capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    assert _confirm(client, ticket, code).status_code == 200
    mark = _mark()
    r = _confirm(client, ticket, code)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert [(x.event, x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("registration_failed", "oauth_ticket_invalid", None),
    ]
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == test_email).count() == 1


def test_post_commit_actions_run_and_their_failure_does_not_rollback(
    client, fake, test_email, capture_emails, monkeypatch,
):
    calls = []

    def _link_boom(user_id, email, **kwargs):
        calls.append(("cards", email))
        raise RuntimeError("card link failed")

    def _welcome_boom(**kwargs):
        calls.append(("welcome", kwargs["event_key"]))
        raise RuntimeError("welcome failed")

    monkeypatch.setattr("app.appointments.service.link_unregistered_cards_to_user", _link_boom)
    monkeypatch.setattr("app.chat.system_publisher.publish_system_message", _welcome_boom)
    ticket, code = _started(client, fake, capture_emails)

    r = _confirm(client, ticket, code)

    assert r.status_code == 200, r.text
    user = _user(test_email)
    # ADR-029: третий post-commit шаг — доставка приглашения подтвердить статус
    # студента ДонГУ через тот же publisher; его сбой тоже не откатывает.
    assert calls == [
        ("cards", test_email),
        ("welcome", f"welcome:user:{user.id}"),
        ("welcome", f"student_verification_invite:user:{user.id}"),
    ]
    assert _identities(fake.subject) == 1


# ── CONFIRM: OTP ─────────────────────────────────────────────────────────────

def test_wrong_code_keeps_ticket_and_counts_attempt(client, fake, test_email, capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    wrong = "000000" if code != "000000" else "111111"
    mark = _mark()

    r = _confirm(client, ticket, wrong)

    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    assert "Осталось попыток: 4" in r.json()["detail"]
    assert _otp(test_email).attempts == 1
    assert _ticket_row(ticket).consumed_at is None
    _assert_nothing_created(test_email, fake.subject)
    assert [(x.event, x.failure_reason, x.auth_method, x.user_email)
            for x in _auth_rows(mark)] == [
        ("registration_failed", "otp_invalid", "yandex", test_email),
    ]
    assert _confirm(client, ticket, code).status_code == 200      # верный код проходит


def test_exhausted_attempts_delete_otp_but_ticket_allows_resend(client, fake, test_email,
                                                               capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(MAX_ATTEMPTS):
        assert _confirm(client, ticket, wrong).status_code == 400
    assert _otp(test_email) is None
    assert _confirm(client, ticket, code).status_code == 400      # старый код мёртв
    assert _ticket_row(ticket).consumed_at is None
    _assert_nothing_created(test_email, fake.subject)

    assert _init(client, ticket).status_code == 200               # resend тем же ticket
    assert _confirm(client, ticket, capture_emails[test_email][-1]).status_code == 200


def test_expired_code(client, fake, test_email, capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == test_email).update(
            {"expires_at": datetime.utcnow() - timedelta(minutes=1)})
        db.commit()
    r = _confirm(client, ticket, code)
    assert r.status_code == 400 and r.json()["code"] == "otp_expired"
    assert _otp(test_email) is None and _ticket_row(ticket).consumed_at is None
    _assert_nothing_created(test_email, fake.subject)


def test_confirm_before_init_and_invalid_ticket(client, fake, test_email):
    r = _confirm(client, "t" * 43, "123456")
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    ticket = _reg_ticket(client, fake)               # код ещё не отправлялся
    mark = _mark()
    r = _confirm(client, ticket, "123456")
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    assert _ticket_row(ticket).consumed_at is None    # не сожжён: init ещё возможен
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("otp_invalid", "yandex"),
    ]
    _assert_nothing_created(test_email, fake.subject)


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "", "12 456"])
def test_confirm_code_format(client, fake, code):
    r = _confirm(client, "t" * 43, code)
    assert r.status_code == 422


# ── изоляция OTP между потоками ──────────────────────────────────────────────

def test_password_registration_otp_cannot_complete_social(client, fake, test_email,
                                                         capture_emails):
    ticket, _ = _started(client, fake, capture_emails)
    _skip_cooldown(test_email)
    r = client.post("/api/auth/register/init", json={
        "name": "Обычная Регистрация", "email": test_email, "password": PASSWORD})
    assert r.status_code == 200
    password_flow_code = capture_emails[test_email][-1]
    assert _otp(test_email).password_hash is not None

    r = _confirm(client, ticket, password_flow_code)

    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    assert _otp(test_email).attempts == 0                 # чужие попытки не сожжены
    _assert_nothing_created(test_email, fake.subject)
    # Сам обычный поток при этом работает и создаёт аккаунт С паролем.
    r = client.post("/api/auth/register/confirm",
                    json={"email": test_email, "code": password_flow_code})
    assert r.status_code == 201
    assert _user(test_email).password_hash is not None and _identities(fake.subject) == 0


def test_social_otp_cannot_complete_password_registration(client, fake, test_email,
                                                         capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    r = client.post("/api/auth/register/confirm", json={"email": test_email, "code": code})
    assert r.status_code == 400
    assert _user(test_email) is None
    assert _confirm(client, ticket, code).status_code == 200      # social-код не потрачен


def test_reset_otp_cannot_complete_social(client, fake, test_email, capture_emails):
    """Email заняли после init (аккаунт создан в обход регистрации) и для него
    выпущен reset-OTP: social confirm его не принимает и попытки не трогает."""
    ticket, _ = _started(client, fake, capture_emails)
    create_test_user(test_email)
    _skip_cooldown(test_email)
    assert client.post("/api/auth/password/reset/init",
                       json={"email": test_email}).status_code == 200
    reset_code = capture_emails[test_email][-1]

    r = _confirm(client, ticket, reset_code)

    assert r.status_code == 409 and r.json()["code"] == "email_already_exists"
    assert _ticket_row(ticket).consumed_at is not None
    assert _otp(test_email).attempts == 0 and _identities(fake.subject) == 0
    # reset-поток своим кодом по-прежнему работает.
    r = client.post("/api/auth/password/reset/confirm", json={
        "email": test_email, "code": reset_code, "new_password": "NewSecure43!"})
    assert r.status_code == 200


def test_social_otp_is_not_a_password_reset_without_account(client, fake, test_email,
                                                           capture_emails):
    _, code = _started(client, fake, capture_emails)
    r = client.post("/api/auth/password/reset/confirm", json={
        "email": test_email, "code": code, "new_password": "NewSecure43!"})
    assert r.status_code == 404
    assert _user(test_email) is None and _otp(test_email) is not None


# ── гонки состояния между init и confirm ─────────────────────────────────────

def test_email_appeared_between_init_and_confirm(client, fake, test_email, capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    existing = int(create_test_user(test_email)["id"])
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 409 and r.json() == {
        "detail": EMAIL_EXISTS, "code": "email_already_exists"}
    assert _ticket_row(ticket).consumed_at is not None            # сожжён
    assert _identities(fake.subject) == 0
    with SessionLocal() as db:
        assert db.query(UserOAuthIdentity).filter_by(user_id=existing).count() == 0
        assert db.query(User).filter(User.email == test_email).count() == 1
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("email_already_exists", "yandex"),
    ]


def test_identity_appeared_between_init_and_confirm(client, fake, test_email,
                                                    foreign_test_email, capture_emails):
    ticket, code = _started(client, fake, capture_emails)
    other = int(create_test_user(foreign_test_email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=other, provider="yandex",
                                 provider_subject=fake.subject))
        db.commit()
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 409 and r.json()["code"] == "oauth_identity_already_linked"
    assert _ticket_row(ticket).consumed_at is not None
    assert _user(test_email) is None and _identities(fake.subject) == 1
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("oauth_identity_already_linked", "yandex"),
    ]


# ── failure-injection: полный откат ──────────────────────────────────────────

def _boom(*args, **kwargs):
    raise RuntimeError("injected technical failure")


def _seed_missing(*args, **kwargs):
    raise RegistrationDataError("seed missing: SECRET internals")


def _svc_confirm(ticket, code):
    return oauth_service.registration_confirm(ticket, code, consent_accepted=True)


def _assert_rolled_back_and_retryable(client, fake, ticket, code, email):
    _assert_nothing_created(email, fake.subject)
    assert _ticket_row(ticket).consumed_at is None
    otp = _otp(email)
    assert otp is not None and otp.attempts == 0
    assert _confirm(client, ticket, code).status_code == 200      # повтор успешен
    assert _identities(fake.subject) == 1


@pytest.mark.parametrize("target", [
    "_new_user", "_add_consents", "_new_identity", "create_session_in_tx",
])
def test_technical_failure_rolls_back_everything(client, fake, test_email, capture_emails,
                                                 monkeypatch, target):
    ticket, code = _started(client, fake, capture_emails)
    monkeypatch.setattr(oauth_storage, target, _boom)
    with pytest.raises(RuntimeError, match="injected technical failure"):
        _svc_confirm(ticket, code)
    monkeypatch.undo()
    _assert_rolled_back_and_retryable(client, fake, ticket, code, test_email)


def test_commit_failure_rolls_back_everything(client, fake, test_email, capture_emails,
                                              monkeypatch):
    ticket, code = _started(client, fake, capture_emails)
    real_factory = oauth_storage.SessionLocal

    def _failing_commit_factory():
        db = real_factory()
        db.commit = _boom
        return db

    monkeypatch.setattr(oauth_storage, "SessionLocal", _failing_commit_factory)
    with pytest.raises(RuntimeError, match="injected technical failure"):
        _svc_confirm(ticket, code)
    monkeypatch.undo()
    _assert_rolled_back_and_retryable(client, fake, ticket, code, test_email)


@pytest.mark.parametrize("target", ["_assign_role", "required_consent_ids"])
def test_missing_seed_data_is_internal_error_not_otp_error(client, fake, test_email,
                                                          capture_emails, monkeypatch, target):
    ticket, code = _started(client, fake, capture_emails)
    monkeypatch.setattr(oauth_storage, target, _seed_missing)
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 500 and r.json()["code"] == "internal_error"
    assert "SECRET" not in r.text and "seed" not in r.text
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("internal_error", "yandex"),
    ]
    monkeypatch.undo()
    _assert_rolled_back_and_retryable(client, fake, ticket, code, test_email)


def test_technical_failure_is_not_reported_as_wrong_code(client, fake, test_email,
                                                        capture_emails, monkeypatch):
    ticket, code = _started(client, fake, capture_emails)
    monkeypatch.setattr(oauth_storage, "create_session_in_tx", _boom)
    mark = _mark()
    with pytest.raises(RuntimeError):
        _svc_confirm(ticket, code)
    assert _auth_rows(mark) == []                         # не otp_invalid
    assert _otp(test_email).attempts == 0


# ── лимиты и секреты ─────────────────────────────────────────────────────────

def test_confirm_rate_limited_per_ticket_digest(client, fake, capture_emails):
    from app.core import rate_limit

    ticket, code = _started(client, fake, capture_emails)
    wrong = "000000" if code != "000000" else "111111"
    statuses = [_confirm(client, ticket, wrong).status_code for _ in range(11)]
    assert statuses[-1] == 429
    keys = list(rate_limit._limiter._hits)
    assert any(k == f"oauth_registration_confirm:ticket:{_sha(ticket)}" for k in keys)
    assert all(ticket not in k for k in keys)             # raw ticket — никогда


def test_no_registration_secrets_in_logs(client, fake, test_email, capture_emails, caplog):
    caplog.set_level(logging.DEBUG)
    ticket, code = _started(client, fake, capture_emails)
    r = _confirm(client, ticket, code)
    token = r.json()["session_token"]
    app_text = "\n".join(
        rec.getMessage() for rec in caplog.records if not rec.name.startswith("httpx")
    )
    for secret in (ticket, _sha(ticket), code, token, fake.subject, NAME, test_email):
        assert secret not in app_text
