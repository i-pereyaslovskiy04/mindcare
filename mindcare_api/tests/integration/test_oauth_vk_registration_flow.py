"""
Stage Social Auth VK-1B — регистрация через VK ID с выбором и подтверждением
email, end-to-end (FakeProvider под именем `vk`).

callback новой identity → registration-ticket (email VK — лишь предложение, его
может не быть) + `step=email` → preview (маскированный адрес, можно ли с ним
продолжить) → init {ticket[, email]} (allowlist, занятость, привязка адреса к
ticket, OTP MindCare) → confirm {ticket, code, consent} → аккаунт без пароля +
VK identity + обычная сессия.

Проверяются: allowlist доменов (тот же, что у обычной регистрации), занятый и
soft-deleted email без привязки и без сжигания ticket, смена email до confirm
(код прежнего адреса не подтверждает новый), email только из ticket на confirm,
повторные проверки домена/занятости внутри транзакции, аудит и отсутствие
секретов в логах. Регрессия Яндекса: его поток и политика не изменились.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone

import pytest

from app.auth import service as auth_service
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
NAME = "Интеграционный Вконтактов"
PREVIEW_URL = "/api/auth/oauth/registration/preview"
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
def vk():
    """VK не отдал email (как в живом smoke) — имя есть."""
    with registered(FakeProvider("vk", email=None, suggested_name=NAME)) as p:
        yield p


@pytest.fixture
def other_email(test_email):
    """Второй адрес на разрешённом домене (integ_* — убирается cleanup'ом)."""
    return "integ_other_" + test_email.split("_", 1)[1]


# ── helpers ──────────────────────────────────────────────────────────────────

def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _callback_fragment(client, provider, name="vk") -> dict:
    r = client.post(f"/api/auth/oauth/{name}/start")
    assert r.status_code == 200, r.text
    state = state_from_authorize_url(r.json()["authorize_url"])
    client.cookies.clear()
    r = client.get(
        f"/api/auth/oauth/{name}/callback",
        params={"state": state, "code": provider.issue_code(state)},
        headers={"Cookie": f"{COOKIE}={state}"}, follow_redirects=False,
    )
    assert r.status_code == 302
    fragment = r.headers["location"].split("#", 1)[1]
    return dict(pair.split("=", 1) for pair in fragment.split("&"))


def _reg_ticket(client, provider) -> str:
    frag = _callback_fragment(client, provider)
    assert frag.get("result") == "registration" and frag.get("step") == "email", frag
    return frag["ticket"]


def _preview(client, ticket):
    return client.post(PREVIEW_URL, json={"ticket": ticket})


def _init(client, ticket, email=None):
    body = {"ticket": ticket}
    if email is not None:
        body["email"] = email
    return client.post(INIT_URL, json=body)


def _confirm(client, ticket, code, consent=True):
    return client.post(CONFIRM_URL, json={
        "ticket": ticket, "code": code, "consent_accepted": consent,
    })


def _started(client, provider, email, capture_emails):
    """ticket с выбранным адресом и отправленным кодом."""
    ticket = _reg_ticket(client, provider)
    r = _init(client, ticket, email)
    assert r.status_code == 200, r.text
    return ticket, capture_emails[email][-1]


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


def _disable_domain(email):
    domain = email.split("@", 1)[1]
    with SessionLocal() as db:
        db.query(AllowedEmailDomain).filter(AllowedEmailDomain.domain == domain).update(
            {"is_active": False})
        db.commit()


def _assert_nothing_created(email, subject):
    assert _user(email) is None
    assert _identities(subject) == 0


# ── CALLBACK ─────────────────────────────────────────────────────────────────

def test_callback_creates_ticket_without_email_and_nothing_else(client, vk):
    mark = _mark()
    frag = _callback_fragment(client, vk)
    assert set(frag) == {"result", "ticket", "step"}
    assert (frag["result"], frag["step"]) == ("registration", "email")
    row = _ticket_row(frag["ticket"])
    assert (row.kind, row.provider, row.provider_subject) == ("registration", "vk", vk.subject)
    assert row.email is None and row.suggested_name == NAME
    assert row.user_id is None and row.consumed_at is None
    assert timedelta(minutes=29) <= row.expires_at - row.created_at <= timedelta(minutes=31)
    assert _identities(vk.subject) == 0 and _auth_rows(mark) == []
    # registration-ticket — не login-ticket.
    assert client.post("/api/auth/oauth/complete",
                       json={"ticket": frag["ticket"]}).status_code == 400


def test_callback_stores_provider_email_only_in_ticket(client, vk, foreign_test_email):
    vk.email = "  " + foreign_test_email.upper() + " "
    r = client.post("/api/auth/oauth/vk/start")
    state = state_from_authorize_url(r.json()["authorize_url"])
    client.cookies.clear()
    r = client.get(
        "/api/auth/oauth/vk/callback",
        params={"state": state, "code": vk.issue_code(state)},
        headers={"Cookie": f"{COOKIE}={state}"}, follow_redirects=False,
    )
    location = r.headers["location"]
    assert foreign_test_email not in location.lower()        # не в URL
    ticket = dict(p.split("=", 1) for p in location.split("#", 1)[1].split("&"))["ticket"]
    assert _ticket_row(ticket).email == foreign_test_email   # нормализован, в ticket


# ── PREVIEW ──────────────────────────────────────────────────────────────────

def test_preview_without_provider_email(client, vk):
    ticket = _reg_ticket(client, vk)
    r = _preview(client, ticket)
    assert r.status_code == 200
    assert r.json() == {
        "provider": "vk", "email_masked": None, "email_allowed": False,
        "email_editable": True,
    }
    assert r.headers["cache-control"] == "no-store"


def test_preview_masks_allowed_provider_email_and_changes_nothing(client, vk, test_email,
                                                                  capture_emails):
    vk.email = test_email
    ticket = _reg_ticket(client, vk)
    before = _ticket_row(ticket)

    for _ in range(3):
        r = _preview(client, ticket)
        assert r.status_code == 200
    masked = f"{test_email[0]}***@{test_email.split('@', 1)[1]}"
    assert r.json() == {
        "provider": "vk", "email_masked": masked, "email_allowed": True,
        "email_editable": True,
    }
    assert test_email not in r.text                          # raw email не отдаётся
    after = _ticket_row(ticket)
    assert (after.email, after.consumed_at, after.expires_at) == (
        before.email, None, before.expires_at)
    assert _otp(test_email) is None and capture_emails == {}   # код не отправлялся


def test_preview_provider_email_outside_allowlist(client, vk, foreign_test_email):
    vk.email = foreign_test_email
    ticket = _reg_ticket(client, vk)
    body = _preview(client, ticket).json()
    assert body["email_allowed"] is False and body["email_masked"] is not None
    assert foreign_test_email not in str(body)


@pytest.mark.parametrize("body_patch", [{"email": "a@donnu.ru"}, {"provider": "vk"}])
def test_preview_rejects_extra_fields(client, vk, body_patch):
    ticket = _reg_ticket(client, vk)
    assert client.post(PREVIEW_URL, json={"ticket": ticket, **body_patch}).status_code == 422


def test_preview_invalid_expired_and_login_tickets(client, vk, test_email):
    r = _preview(client, "t" * 43)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"

    ticket = _reg_ticket(client, vk)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        db.query(OAuthPendingTicket).filter_by(ticket_hash=_sha(ticket)).update(
            {"created_at": past, "expires_at": past + timedelta(minutes=30)})
        db.commit()
    assert _preview(client, ticket).json()["code"] == "oauth_ticket_invalid"

    user_id = int(create_test_user(test_email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=user_id, provider="vk",
                                 provider_subject=vk.subject))
        db.commit()
    frag = _callback_fragment(client, vk)
    assert frag["result"] == "login" and "step" not in frag
    assert _preview(client, frag["ticket"]).json()["code"] == "oauth_ticket_invalid"


def test_preview_rate_limited_per_ticket_digest(client, vk):
    from app.core import rate_limit

    ticket = _reg_ticket(client, vk)
    statuses = [_preview(client, ticket).status_code for _ in range(21)]
    assert statuses[:20] == [200] * 20 and statuses[-1] == 429
    keys = list(rate_limit._limiter._hits)
    assert f"oauth_registration_preview:ticket:{_sha(ticket)}" in keys
    assert all(ticket not in k for k in keys)


# ── INIT: выбор адреса ───────────────────────────────────────────────────────

def test_init_without_email_when_vk_gave_none_is_email_required(client, vk, capture_emails):
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket)
    assert r.status_code == 422 and r.json()["code"] == "email_required"
    assert capture_emails == {} and _ticket_row(ticket).consumed_at is None


def test_init_with_manual_email_binds_ticket_and_sends_otp(client, vk, test_email,
                                                          capture_emails):
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket, "  " + test_email.upper() + " ")
    assert r.status_code == 200, r.text
    masked = f"{test_email[0]}***@{test_email.split('@', 1)[1]}"
    assert r.json() == {
        "message": "Код подтверждения отправлен на email", "email_masked": masked,
    }
    assert test_email not in r.text
    row = _ticket_row(ticket)
    assert row.email == test_email and row.consumed_at is None   # нормализован, привязан
    otp = _otp(test_email)
    assert otp is not None and otp.password_hash is None
    assert list(capture_emails) == [test_email] and len(capture_emails[test_email]) == 1
    _assert_nothing_created(test_email, vk.subject)


def test_init_continue_with_provider_email(client, vk, test_email, capture_emails):
    vk.email = test_email
    ticket = _reg_ticket(client, vk)
    assert _init(client, ticket).status_code == 200            # «Продолжить»
    assert list(capture_emails) == [test_email]
    assert _ticket_row(ticket).email == test_email


@pytest.mark.parametrize("bad", ["not-an-email", "a@@donnu.ru", "user@", "us er@donnu.ru"])
def test_init_invalid_email_format(client, vk, capture_emails, bad):
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket, bad)
    assert r.status_code == 422 and r.json()["code"] == "email_invalid"
    assert _ticket_row(ticket).email is None and capture_emails == {}


@pytest.mark.parametrize("body_patch", [
    {"name": "Подмена"}, {"consent_accepted": True}, {"provider": "yandex"},
    {"subject": "x"}, {"user_id": 1}, {"password": "Secret123"},
])
def test_init_rejects_other_client_supplied_fields(client, vk, test_email, capture_emails,
                                                   body_patch):
    ticket = _reg_ticket(client, vk)
    r = client.post(INIT_URL, json={"ticket": ticket, "email": test_email, **body_patch})
    assert r.status_code == 422
    assert capture_emails == {} and _ticket_row(ticket).email is None


def test_init_disallowed_domain_keeps_ticket_and_can_be_corrected(
    client, vk, foreign_test_email, test_email, capture_emails, reset_email_domains,
):
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket, foreign_test_email)
    assert r.status_code == 422 and r.json()["code"] == "domain_not_allowed"
    row = _ticket_row(ticket)
    assert row.email is None and row.consumed_at is None       # ticket не изменён
    assert capture_emails == {} and _otp(foreign_test_email) is None

    assert _init(client, ticket, test_email).status_code == 200   # исправили адрес
    assert _ticket_row(ticket).email == test_email
    assert _confirm(client, ticket, capture_emails[test_email][-1]).status_code == 200


def test_init_provider_email_outside_allowlist_cannot_continue(
    client, vk, foreign_test_email, test_email, capture_emails,
):
    vk.email = foreign_test_email
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket)                                   # «Продолжить» с адресом VK
    assert r.status_code == 422 and r.json()["code"] == "domain_not_allowed"
    assert capture_emails == {}
    assert _init(client, ticket, test_email).status_code == 200  # указали актуальную
    assert _ticket_row(ticket).email == test_email


def test_init_occupied_email_is_refused_without_link_or_burn(
    client, vk, test_email, other_email, capture_emails,
):
    existing = int(create_test_user(test_email)["id"])
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket, test_email)
    assert r.status_code == 409
    assert r.json() == {"detail": EMAIL_EXISTS, "code": "email_already_exists"}
    row = _ticket_row(ticket)
    assert row.consumed_at is None and row.email is None        # не сожжён, не привязан
    assert capture_emails == {} and _otp(test_email) is None
    assert _identities(vk.subject) == 0                         # без auto-link
    with SessionLocal() as db:
        assert db.query(UserOAuthIdentity).filter_by(user_id=existing).count() == 0

    # Тем же ticket можно указать другой адрес и зарегистрироваться.
    assert _init(client, ticket, other_email).status_code == 200
    assert _confirm(client, ticket, capture_emails[other_email][-1]).status_code == 200
    assert _user(other_email) is not None and _identities(vk.subject) == 1


def test_init_soft_deleted_email_is_refused_without_reactivation(
    client, vk, test_email, capture_emails,
):
    user_id = int(create_test_user(test_email)["id"])
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update(
            {"deleted_at": datetime.now(timezone.utc), "is_active": False})
        db.commit()
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket, test_email)
    # Тот же ответ, что для активного аккаунта: состояние не раскрывается.
    assert r.status_code == 409
    assert r.json() == {"detail": EMAIL_EXISTS, "code": "email_already_exists"}
    with SessionLocal() as db:
        user = db.get(User, user_id)
        assert user.deleted_at is not None and user.is_active is False   # не восстановлен
    assert _identities(vk.subject) == 0 and capture_emails == {}
    assert _ticket_row(ticket).consumed_at is None


def test_init_identity_appeared_burns_ticket(client, vk, test_email, foreign_test_email,
                                             capture_emails):
    ticket = _reg_ticket(client, vk)
    other = int(create_test_user(foreign_test_email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=other, provider="vk", provider_subject=vk.subject))
        db.commit()
    r = _init(client, ticket, test_email)
    assert r.status_code == 409 and r.json()["code"] == "oauth_identity_already_linked"
    assert _ticket_row(ticket).consumed_at is not None and capture_emails == {}
    assert _init(client, ticket, test_email).status_code == 400   # сожжён


def test_init_resend_without_email_uses_bound_address(client, vk, test_email,
                                                      capture_emails):
    ticket = _reg_ticket(client, vk)
    assert _init(client, ticket, test_email).status_code == 200
    expires = _ticket_row(ticket).expires_at

    r = _init(client, ticket)                                   # «Отправить повторно»
    assert r.status_code == 429 and r.json()["code"] == "otp_cooldown"
    _skip_cooldown(test_email)
    assert _init(client, ticket).status_code == 200
    assert len(capture_emails[test_email]) == 2
    assert _ticket_row(ticket).expires_at == expires            # TTL не продлевается


def test_init_cooldown_does_not_rebind_ticket(client, vk, test_email, other_email,
                                              capture_emails):
    """Отказ cooldown не должен менять адрес ticket."""
    ticket = _reg_ticket(client, vk)
    assert _init(client, ticket, test_email).status_code == 200
    assert _init(client, ticket, other_email).status_code == 200   # сменили адрес
    r = _init(client, ticket, test_email)                          # обратно — под cooldown
    assert r.status_code == 429 and r.json()["code"] == "otp_cooldown"
    assert _ticket_row(ticket).email == other_email                # адрес не изменился


def test_init_smtp_failure_keeps_committed_state(client, vk, test_email, monkeypatch):
    def _smtp_down(*args, **kwargs):
        raise RuntimeError("SMTP SECRET detail")

    monkeypatch.setattr("app.services.email_service.send_email", _smtp_down)
    ticket = _reg_ticket(client, vk)
    r = _init(client, ticket, test_email)
    assert r.status_code == 500 and r.json()["code"] == "email_delivery_failed"
    assert "SECRET" not in r.text
    assert _otp(test_email) is not None and _ticket_row(ticket).email == test_email


def test_init_with_email_rate_limits(client, vk, test_email, capture_emails):
    from app.core import rate_limit

    ticket = _reg_ticket(client, vk)
    statuses = []
    for _ in range(4):
        statuses.append(_init(client, ticket, test_email).status_code)
        _skip_cooldown(test_email)
    assert statuses == [200, 200, 200, 429]                     # лимит по самому адресу
    keys = list(rate_limit._limiter._hits)
    assert f"oauth_registration_email:ticket:{_sha(ticket)}" in keys
    assert f"oauth_registration_email:email:{test_email}" in keys
    assert all(ticket not in k for k in keys)                   # raw ticket — никогда


# ── СМЕНА EMAIL ДО CONFIRM ───────────────────────────────────────────────────

def test_code_for_old_email_does_not_confirm_new_email(client, vk, test_email, other_email,
                                                      capture_emails):
    """Критический сценарий: OTP для A → адрес ticket сменили на B → код от A
    НЕ подтверждает регистрацию; код от B — подтверждает, и аккаунт создаётся на B."""
    ticket, code_a = _started(client, vk, test_email, capture_emails)
    assert _init(client, ticket, other_email).status_code == 200
    code_b = capture_emails[other_email][-1]
    assert _ticket_row(ticket).email == other_email

    if code_a != code_b:
        r = _confirm(client, ticket, code_a)
        assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
        assert _otp(other_email).attempts == 1                  # считается попыткой для B
        assert _otp(test_email).attempts == 0                   # запись A не тронута
    _assert_nothing_created(test_email, vk.subject)
    _assert_nothing_created(other_email, vk.subject)

    r = _confirm(client, ticket, code_b)
    assert r.status_code == 200, r.text
    assert _user(other_email) is not None and _user(test_email) is None
    assert _identities(vk.subject) == 1


def test_confirm_takes_email_only_from_ticket(client, vk, test_email, other_email,
                                              capture_emails):
    ticket, code = _started(client, vk, test_email, capture_emails)
    r = client.post(CONFIRM_URL, json={
        "ticket": ticket, "code": code, "consent_accepted": True, "email": other_email,
    })
    assert r.status_code == 422                                  # email на confirm запрещён
    _assert_nothing_created(test_email, vk.subject)
    _assert_nothing_created(other_email, vk.subject)
    assert _confirm(client, ticket, code).status_code == 200
    assert _user(test_email) is not None and _user(other_email) is None


def test_confirm_before_email_is_chosen_is_rejected(client, vk):
    ticket = _reg_ticket(client, vk)                            # init не вызывался
    r = _confirm(client, ticket, "123456")
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert _ticket_row(ticket).consumed_at is None              # ticket цел
    assert _identities(vk.subject) == 0


# ── CONFIRM ──────────────────────────────────────────────────────────────────

def test_confirm_creates_passwordless_student_with_vk_identity_and_session(
    client, vk, test_email, capture_emails,
):
    ticket, code = _started(client, vk, test_email, capture_emails)
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"session_token", "expires_at", "roles", "role"}
    assert body["roles"] == ["student"] and body["role"] == "student"
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == test_email).one()
        assert user.password_hash is None and user.full_name == NAME
        assert user.deleted_at is None and user.last_login is not None
        assert db.query(UserRole).filter(UserRole.user_id == user.id).count() == 1
        consents = db.query(ConsentRecord).filter(ConsentRecord.user_id == user.id).all()
        assert len(consents) == len(auth_service.REQUIRED_CONSENTS)
        assert all(c.accepted for c in consents)
        identity = db.query(UserOAuthIdentity).filter_by(user_id=user.id).one()
        assert (identity.provider, identity.provider_subject) == ("vk", vk.subject)
        assert identity.last_login_at is not None
        sessions = db.query(UserSession).filter(UserSession.user_id == user.id).all()
        assert len(sessions) == 1 and sessions[0].id == _sha(body["session_token"])
        user_id = user.id
    assert _ticket_row(ticket).consumed_at is not None and _otp(test_email) is None

    headers = {"Authorization": f"Bearer {body['session_token']}"}
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == test_email and me["has_password"] is False and me["name"] == NAME

    rows = _auth_rows(mark)
    assert [(x.event, x.auth_method, x.success) for x in rows] == [
        ("registration_succeeded", "vk", True), ("login", "vk", True),
    ]
    assert rows[0].user_id == user_id and rows[0].user_email == test_email


def test_name_falls_back_to_chosen_email_when_vk_gave_none(client, vk, test_email,
                                                          other_email, capture_emails):
    """Имя берётся по ИТОГОВОМУ адресу: локальная часть прежнего адреса в
    профиль не попадает."""
    vk.suggested_name = None
    ticket, _ = _started(client, vk, test_email, capture_emails)
    assert _init(client, ticket, other_email).status_code == 200
    assert _confirm(client, ticket, capture_emails[other_email][-1]).status_code == 200
    assert _user(other_email).full_name == other_email.split("@", 1)[0]


@pytest.mark.parametrize("consent", [False, None, "true", 1, "missing"])
def test_confirm_without_literal_consent_creates_nothing(client, vk, test_email,
                                                         capture_emails, consent):
    ticket, code = _started(client, vk, test_email, capture_emails)
    body = {"ticket": ticket, "code": code}
    if consent != "missing":
        body["consent_accepted"] = consent
    r = client.post(CONFIRM_URL, json=body)
    assert r.status_code == 422
    _assert_nothing_created(test_email, vk.subject)
    assert _otp(test_email).attempts == 0 and _ticket_row(ticket).consumed_at is None
    assert _confirm(client, ticket, code).status_code == 200


def test_confirm_replay_is_rejected(client, vk, test_email, capture_emails):
    ticket, code = _started(client, vk, test_email, capture_emails)
    assert _confirm(client, ticket, code).status_code == 200
    mark = _mark()
    r = _confirm(client, ticket, code)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert [(x.event, x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("registration_failed", "oauth_ticket_invalid", None),
    ]
    with SessionLocal() as db:
        assert db.query(User).filter(User.email == test_email).count() == 1
    assert _init(client, ticket, test_email).status_code == 400   # ticket сожжён


def test_second_callback_after_registration_is_plain_login(client, vk, test_email,
                                                          capture_emails):
    ticket, code = _started(client, vk, test_email, capture_emails)
    assert _confirm(client, ticket, code).status_code == 200
    frag = _callback_fragment(client, vk)
    assert set(frag) == {"result", "ticket"} and frag["result"] == "login"
    assert _otp(test_email) is None                             # без OTP
    assert client.post("/api/auth/oauth/complete",
                       json={"ticket": frag["ticket"]}).status_code == 200


# ── гонки состояния между init и confirm ─────────────────────────────────────

def test_email_occupied_between_init_and_confirm(client, vk, test_email, other_email,
                                                 capture_emails):
    ticket, code = _started(client, vk, test_email, capture_emails)
    existing = int(create_test_user(test_email)["id"])
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 409 and r.json() == {
        "detail": EMAIL_EXISTS, "code": "email_already_exists"}
    assert _identities(vk.subject) == 0
    with SessionLocal() as db:
        assert db.query(UserOAuthIdentity).filter_by(user_id=existing).count() == 0
        assert db.query(User).filter(User.email == test_email).count() == 1
        assert db.query(UserSession).filter(UserSession.user_id == existing).count() == 0
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("email_already_exists", "vk"),
    ]
    # Ticket цел: пользователь меняет адрес и завершает регистрацию.
    assert _ticket_row(ticket).consumed_at is None
    assert _init(client, ticket, other_email).status_code == 200
    assert _confirm(client, ticket, capture_emails[other_email][-1]).status_code == 200
    assert _identities(vk.subject) == 1


def test_domain_disabled_between_init_and_confirm_blocks_registration(
    client, vk, test_email, capture_emails, reset_email_domains,
):
    ticket, code = _started(client, vk, test_email, capture_emails)
    _disable_domain(test_email)
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 422 and r.json()["code"] == "domain_not_allowed"
    _assert_nothing_created(test_email, vk.subject)
    assert _ticket_row(ticket).consumed_at is None              # ticket и OTP целы
    otp = _otp(test_email)
    assert otp is not None and otp.attempts == 0
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("domain_not_allowed", "vk"),
    ]


def test_identity_appeared_between_init_and_confirm(client, vk, test_email,
                                                    foreign_test_email, capture_emails):
    ticket, code = _started(client, vk, test_email, capture_emails)
    other = int(create_test_user(foreign_test_email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=other, provider="vk", provider_subject=vk.subject))
        db.commit()
    mark = _mark()

    r = _confirm(client, ticket, code)

    assert r.status_code == 409 and r.json()["code"] == "oauth_identity_already_linked"
    assert _ticket_row(ticket).consumed_at is not None
    assert _user(test_email) is None and _identities(vk.subject) == 1
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows(mark)] == [
        ("oauth_identity_already_linked", "vk"),
    ]


def test_wrong_code_keeps_ticket_and_counts_attempt(client, vk, test_email, capture_emails):
    ticket, code = _started(client, vk, test_email, capture_emails)
    wrong = "000000" if code != "000000" else "111111"
    r = _confirm(client, ticket, wrong)
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    assert _otp(test_email).attempts == 1 and _ticket_row(ticket).consumed_at is None
    assert _confirm(client, ticket, code).status_code == 200


# ── failure-injection: полный откат ──────────────────────────────────────────

def _boom(*args, **kwargs):
    raise RuntimeError("injected technical failure")


@pytest.mark.parametrize("target", [
    "_new_user", "_add_consents", "_new_identity", "create_session_in_tx",
])
def test_technical_failure_rolls_back_everything(client, vk, test_email, capture_emails,
                                                 monkeypatch, target):
    ticket, code = _started(client, vk, test_email, capture_emails)
    monkeypatch.setattr(oauth_storage, target, _boom)
    with pytest.raises(RuntimeError, match="injected technical failure"):
        oauth_service.registration_confirm(ticket, code, consent_accepted=True)
    monkeypatch.undo()
    _assert_nothing_created(test_email, vk.subject)             # ни user, ни identity
    assert _ticket_row(ticket).consumed_at is None
    assert _otp(test_email).attempts == 0
    assert _confirm(client, ticket, code).status_code == 200    # повтор успешен
    assert _identities(vk.subject) == 1


# ── изоляция OTP и обычная регистрация ───────────────────────────────────────

def test_password_registration_otp_cannot_complete_vk(client, vk, test_email,
                                                     capture_emails):
    ticket, _ = _started(client, vk, test_email, capture_emails)
    _skip_cooldown(test_email)
    r = client.post("/api/auth/register/init", json={
        "name": "Обычная Регистрация", "email": test_email, "password": PASSWORD})
    assert r.status_code == 200
    password_flow_code = capture_emails[test_email][-1]

    r = _confirm(client, ticket, password_flow_code)
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    assert _otp(test_email).attempts == 0                       # чужие попытки не сожжены
    _assert_nothing_created(test_email, vk.subject)


def test_ordinary_registration_still_enforces_domain_allowlist(
    client, vk, foreign_test_email, capture_emails,
):
    r = client.post("/api/auth/register/init", json={
        "name": "Обычная Регистрация", "email": foreign_test_email, "password": PASSWORD,
    })
    assert r.status_code == 422 and capture_emails == {}


# ── регрессия Яндекса: его поток и политика не изменились ───────────────────

@pytest.fixture
def yandex(foreign_test_email):
    with registered(FakeProvider("yandex", email=foreign_test_email,
                                 suggested_name="Яндекс Студент")) as p:
        yield p


def test_yandex_flow_is_unchanged(client, yandex, foreign_test_email, test_email,
                                  capture_emails):
    frag = _callback_fragment(client, yandex, name="yandex")
    assert set(frag) == {"result", "ticket"}                    # без шага email
    ticket = frag["ticket"]

    body = _preview(client, ticket).json()
    assert body["provider"] == "yandex" and body["email_editable"] is False
    assert body["email_allowed"] is True                        # allowlist не применяется

    # Свой email Яндексу передать нельзя — ни подменой, ни «тем же» адресом.
    for email in (test_email, foreign_test_email):
        r = _init(client, ticket, email)
        assert r.status_code == 422 and r.json()["code"] == "email_not_changeable"
    assert capture_emails == {} and _ticket_row(ticket).email == foreign_test_email

    assert _init(client, ticket).status_code == 200             # автоматический init
    code = capture_emails[foreign_test_email][-1]
    assert _confirm(client, ticket, code).status_code == 200    # домен вне allowlist — ок
    assert _user(foreign_test_email).full_name == "Яндекс Студент"


def test_yandex_occupied_email_still_burns_ticket(client, yandex, foreign_test_email):
    create_test_user(foreign_test_email)
    frag = _callback_fragment(client, yandex, name="yandex")
    r = _init(client, frag["ticket"])
    assert r.status_code == 409 and r.json()["code"] == "email_already_exists"
    assert _ticket_row(frag["ticket"]).consumed_at is not None  # как и раньше


# ── секреты не попадают в логи ───────────────────────────────────────────────

def test_no_registration_secrets_in_logs(client, vk, test_email, capture_emails, caplog):
    caplog.set_level(logging.DEBUG)
    ticket, code = _started(client, vk, test_email, capture_emails)
    _preview(client, ticket)
    token = _confirm(client, ticket, code).json()["session_token"]
    app_text = "\n".join(
        rec.getMessage() for rec in caplog.records if not rec.name.startswith("httpx")
    )
    for secret in (ticket, _sha(ticket), code, token, vk.subject, NAME, test_email):
        assert secret not in app_text
