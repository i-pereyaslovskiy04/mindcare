"""
Продолжение регистрации через Яндекс/VK из письма (/register/social).

Callback новой identity кладёт raw registration-ticket в HttpOnly
SameSite=Strict cookie с путём /api/auth/oauth/registration. Письмо содержит
только ссылку {FRONTEND_PUBLIC_URL}/register/social (без ticket, email, кода).
resume (только cookie) восстанавливает шаг без отправки кода; init/confirm
берут ticket из тела или cookie (оба — только совпадающие, иначе 409).
Другой браузер (без cookie) ни продолжить, ни сменить email не может —
в том числе в сценарии VK pre-hijacking.

Обычная регистрация email + пароль (registration_reference,
/register/confirm#r=...) не меняется — регрессии в конце файла.
"""
import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from starlette.responses import Response

from app.db.models import (
    AuthLog, OAuthAuthRequest, OAuthPendingTicket, OtpVerification, User,
    UserOAuthIdentity,
)
from app.db.session import SessionLocal
from app.oauth import routes as oauth_routes
from app.oauth import service as oauth_service
from tests.oauth_fakes import FakeProvider, registered, state_from_authorize_url

STATE_COOKIE = "mindcare_oauth_state"
REG_COOKIE = "mindcare_oauth_registration"
REG_PATH = "/api/auth/oauth/registration"
RESUME_URL = f"{REG_PATH}/resume"
PREVIEW_URL = f"{REG_PATH}/preview"
INIT_URL = f"{REG_PATH}/init"
CONFIRM_URL = f"{REG_PATH}/confirm"
NAME = "Интеграционный Студент"
NOT_FOUND = "oauth_registration_not_found"


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
def letters():
    """Письма регистрации: {recipient: [(code, html, body), ...]}."""
    sent = {}

    def _fake(to, subject, body, html=None):
        m = re.search(r"Ваш код: (\d{6})", body)
        if m:
            sent.setdefault(to, []).append((m.group(1), html or "", body))

    with patch("app.services.email_service.send_email", side_effect=_fake):
        yield sent


@pytest.fixture
def yandex(test_email):
    with registered(FakeProvider("yandex", email=test_email, suggested_name=NAME)) as p:
        yield p


@pytest.fixture
def vk():
    with registered(FakeProvider("vk", email=None, suggested_name=NAME)) as p:
        yield p


def _sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def _callback(client, provider):
    """OAuth до callback; ответ callback (Set-Cookie + redirect) и fragment."""
    name = provider.name
    r = client.post(f"/api/auth/oauth/{name}/start")
    assert r.status_code == 200, r.text
    state = state_from_authorize_url(r.json()["authorize_url"])
    client.cookies.clear()
    r = client.get(
        f"/api/auth/oauth/{name}/callback",
        params={"state": state, "code": provider.issue_code(state)},
        headers={"Cookie": f"{STATE_COOKIE}={state}"}, follow_redirects=False,
    )
    assert r.status_code == 302
    fragment = dict(p.split("=", 1) for p in r.headers["location"].split("#", 1)[1].split("&"))
    return r, fragment


def _reg_cookie_headers(response):
    return [h for h in response.headers.get_list("set-cookie") if h.startswith(f"{REG_COOKIE}=")]


def _cookie_deleted(response):
    headers = _reg_cookie_headers(response)
    return bool(headers) and any(
        re.search(r"max-age=0\b", h, re.I) or 'expires=thu, 01 jan 1970' in h.lower()
        for h in headers
    )


def _ticket_row(ticket):
    with SessionLocal() as db:
        row = db.get(OAuthPendingTicket, _sha(ticket))
        if row is not None:
            db.expunge(row)
        return row


def _otp(email):
    with SessionLocal() as db:
        row = db.query(OtpVerification).filter(OtpVerification.email == email).one_or_none()
        if row is not None:
            db.expunge(row)
        return row


def _users(email):
    with SessionLocal() as db:
        return db.query(User).filter(User.email == email).count()


def _identities(provider):
    with SessionLocal() as db:
        return db.query(UserOAuthIdentity).filter(
            UserOAuthIdentity.provider == provider.name,
            UserOAuthIdentity.provider_subject == provider.subject,
        ).count()


def _skip_cooldown(email):
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == email).update(
            {"last_sent_at": datetime.utcnow() - timedelta(seconds=120)})
        db.commit()


def _started_yandex(client, yandex, letters):
    """Яндекс: callback (cookie) + init по cookie → (ticket, code)."""
    _, frag = _callback(client, yandex)
    r = client.post(INIT_URL, json={})
    assert r.status_code == 200, r.text
    return frag["ticket"], letters[yandex.email][-1][0]


def _confirm(client, code, **extra):
    return client.post(CONFIRM_URL, json={"code": code, "consent_accepted": True, **extra})


# ── cookie на callback ───────────────────────────────────────────────────────

def test_callback_sets_registration_cookie_with_strict_attributes(client, yandex):
    r, frag = _callback(client, yandex)
    (header,) = _reg_cookie_headers(r)
    attrs = [a.strip().lower() for a in header.split(";")]
    assert header.startswith(f"{REG_COOKIE}={frag['ticket']};")
    assert "httponly" in attrs
    assert "samesite=strict" in attrs
    assert f"path={REG_PATH}" in attrs
    max_age = int(next(a for a in attrs if a.startswith("max-age=")).split("=")[1])
    ttl = int(oauth_service.REGISTRATION_TICKET_TTL.total_seconds())
    assert ttl - 60 <= max_age <= ttl
    # Тестовое окружение — http (callback base не https): Secure не ставится.
    assert "secure" not in attrs
    # Cookie — это именно ticket этой регистрации.
    assert _ticket_row(frag["ticket"]).kind == "registration"


def test_registration_cookie_is_secure_with_https_callback_base():
    response = Response()
    expires = oauth_service._now() + oauth_service.REGISTRATION_TICKET_TTL
    with patch.object(oauth_service, "state_cookie_secure", return_value=True):
        oauth_routes._set_registration_cookie(response, "t" * 43, expires)
    header = response.headers["set-cookie"].lower()
    assert "secure" in header and "httponly" in header and "samesite=strict" in header


def test_login_callback_does_not_set_registration_cookie(client, yandex, letters):
    # Сначала зарегистрировать identity, затем обычный вход через провайдера.
    _, code = _started_yandex(client, yandex, letters)
    assert _confirm(client, code).status_code == 200
    r, frag = _callback(client, yandex)
    assert frag.get("result") == "login"
    assert _reg_cookie_headers(r) == []


# ── письмо ───────────────────────────────────────────────────────────────────

def test_social_letter_links_to_register_social_without_secrets(client, yandex, letters):
    ticket, code = _started_yandex(client, yandex, letters)
    _, html, body = letters[yandex.email][-1]
    hrefs = re.findall(r'href="([^"]+)"', html)
    assert hrefs == ["http://localhost:3000/register/social"]
    assert "http://localhost:3000/register/social\n" in body
    for text in (html, body):
        assert ticket not in text and _sha(ticket) not in text
    for href in hrefs:
        assert yandex.email not in href and code not in href
        assert "?" not in href and "#" not in href
        assert "yandex" not in href


# ── resume ───────────────────────────────────────────────────────────────────

def test_resume_is_read_only_and_sends_nothing(client, yandex, letters):
    ticket, _ = _started_yandex(client, yandex, letters)
    before_ticket = _ticket_row(ticket)
    before_otp = _otp(yandex.email)
    sent_before = len(letters[yandex.email])

    for _ in range(2):   # F5 — повторный resume
        r = client.post(RESUME_URL, json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["provider"] == "yandex"
        assert data["email_masked"] and data["email_masked"] != yandex.email
        assert data["email_editable"] is False and data["code_active"] is True
        assert 0 < data["resend_in_seconds"] <= 60
        assert ticket not in r.text and yandex.email not in r.text
        assert r.headers["cache-control"] == "no-store"

    after_ticket = _ticket_row(ticket)
    after_otp = _otp(yandex.email)
    assert len(letters[yandex.email]) == sent_before                  # код не отправлен
    assert (after_ticket.expires_at, after_ticket.email, after_ticket.consumed_at) == (
        before_ticket.expires_at, before_ticket.email, before_ticket.consumed_at)
    assert (after_otp.code, after_otp.expires_at, after_otp.last_sent_at, after_otp.attempts) == (
        before_otp.code, before_otp.expires_at, before_otp.last_sent_at, before_otp.attempts)


def test_resume_without_cookie_reveals_nothing(client, yandex, letters):
    _started_yandex(client, yandex, letters)
    client.cookies.clear()
    r = client.post(RESUME_URL, json={})
    assert r.status_code == 400
    assert set(r.json()) == {"detail", "code"} and r.json()["code"] == NOT_FOUND
    assert yandex.email not in r.text


def test_resume_rejects_body_ticket(client, yandex):
    _, frag = _callback(client, yandex)
    assert client.post(RESUME_URL, json={"ticket": frag["ticket"]}).status_code == 422


# ── confirm по cookie ────────────────────────────────────────────────────────

def test_confirm_by_cookie_creates_account_identity_session_and_clears_cookie(
    client, yandex, letters,
):
    _, code = _started_yandex(client, yandex, letters)
    r = _confirm(client, code)
    assert r.status_code == 200, r.text
    assert r.json()["session_token"] and r.json()["roles"] == ["student"]
    assert _cookie_deleted(r)
    assert _users(yandex.email) == 1 and _identities(yandex) == 1
    # Cookie удалена — продолжение из письма больше не находит регистрацию.
    assert client.post(RESUME_URL, json={}).json()["code"] == NOT_FOUND


def test_audit_and_logs_without_ticket_or_code(client, yandex, letters, caplog):
    caplog.set_level(logging.DEBUG)
    with SessionLocal() as db:
        mark = db.query(AuthLog.id).order_by(AuthLog.id.desc()).limit(1).scalar() or 0
    ticket, code = _started_yandex(client, yandex, letters)
    client.post(RESUME_URL, json={})
    assert _confirm(client, code).status_code == 200
    with SessionLocal() as db:
        rows = db.query(AuthLog).filter(AuthLog.id > mark).all()
        events = {(r.event, r.auth_method) for r in rows}
        dumped = repr([{c.name: getattr(r, c.name) for c in AuthLog.__table__.columns} for r in rows])
    assert ("registration_succeeded", "yandex") in events and ("login", "yandex") in events
    assert ticket not in dumped and code not in dumped
    assert ticket not in caplog.text and code not in caplog.text


# ── другой браузер и VK pre-hijacking ────────────────────────────────────────

def test_other_browser_without_cookie_cannot_continue(client, yandex, letters):
    ticket, code = _started_yandex(client, yandex, letters)
    client.cookies.clear()          # другой браузер: есть только письмо с кодом
    assert _confirm(client, code).json()["code"] == NOT_FOUND
    assert client.post(INIT_URL, json={}).json()["code"] == NOT_FOUND
    assert client.post(PREVIEW_URL, json={}).json()["code"] == NOT_FOUND
    assert _users(yandex.email) == 0 and _identities(yandex) == 0
    assert _ticket_row(ticket).consumed_at is None


def test_vk_prehijack_victim_browser_cannot_bind_attacker_identity(client, vk, letters, test_email):
    # Злоумышленник: свой VK, в браузере злоумышленника — cookie; адрес жертвы.
    _, frag = _callback(client, vk)
    r = client.post(INIT_URL, json={"email": test_email})
    assert r.status_code == 200, r.text
    code, html, _ = letters[test_email][-1]
    assert "/register/social" in html                                  # ссылка — без секретов

    # Жертва открывает письмо в своём браузере: cookie нет.
    client.cookies.clear()
    assert client.post(RESUME_URL, json={}).json()["code"] == NOT_FOUND
    assert _confirm(client, code).json()["code"] == NOT_FOUND
    assert client.post(INIT_URL, json={"email": "integ_other_x@donnu.ru"}).json()["code"] == NOT_FOUND
    assert _users(test_email) == 0 and _identities(vk) == 0
    assert _ticket_row(frag["ticket"]).email == test_email                # адрес не изменён


def test_vk_editable_email_by_cookie_in_same_browser(client, vk, letters, test_email):
    other = "integ_other_" + test_email.split("_", 1)[1]
    _callback(client, vk)
    r = client.post(RESUME_URL, json={})
    assert r.status_code == 200
    assert r.json()["email_editable"] is True and r.json()["email_masked"] is None
    assert r.json()["code_active"] is False
    assert client.post(INIT_URL, json={"email": test_email}).status_code == 200
    _skip_cooldown(test_email)
    assert client.post(INIT_URL, json={"email": other}).status_code == 200
    data = client.post(RESUME_URL, json={}).json()
    assert data["code_active"] is True and data["email_masked"].endswith(other.split("@")[1])
    code = letters[other][-1][0]
    r = _confirm(client, code)
    assert r.status_code == 200, r.text
    assert _users(other) == 1 and _users(test_email) == 0


def test_yandex_email_not_changeable_by_cookie(client, yandex, letters):
    _callback(client, yandex)
    r = client.post(INIT_URL, json={"email": "integ_other_x@donnu.ru"})
    assert r.status_code == 422 and r.json()["code"] == "email_not_changeable"


# ── resend и сроки ───────────────────────────────────────────────────────────

def test_resend_by_cookie_invalidates_old_code_and_keeps_ticket_ttl(client, yandex, letters):
    ticket, old_code = _started_yandex(client, yandex, letters)
    expires = _ticket_row(ticket).expires_at
    _skip_cooldown(yandex.email)
    assert client.post(INIT_URL, json={}).status_code == 200
    new_code = letters[yandex.email][-1][0]
    assert _ticket_row(ticket).expires_at == expires                     # ticket не продлён
    if new_code != old_code:
        r = _confirm(client, old_code)
        assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    assert _confirm(client, new_code).status_code == 200


def test_expired_code_then_resend(client, yandex, letters):
    _started_yandex(client, yandex, letters)
    with SessionLocal() as db:
        db.query(OtpVerification).filter(OtpVerification.email == yandex.email).update({
            "expires_at": datetime.utcnow() - timedelta(seconds=1),
            "last_sent_at": datetime.utcnow() - timedelta(seconds=120),
        })
        db.commit()
    data = client.post(RESUME_URL, json={}).json()
    assert data["code_active"] is False and data["resend_in_seconds"] == 0
    assert client.post(INIT_URL, json={}).status_code == 200
    assert _confirm(client, letters[yandex.email][-1][0]).status_code == 200


def test_expired_ticket_clears_cookie(client, yandex, letters):
    ticket, code = _started_yandex(client, yandex, letters)
    with SessionLocal() as db:
        db.query(OAuthPendingTicket).filter(OAuthPendingTicket.ticket_hash == _sha(ticket)).update(
            {"created_at": datetime.now(timezone.utc) - timedelta(hours=1),
             "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
    r = client.post(RESUME_URL, json={})
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert _cookie_deleted(r)


def test_wrong_code_keeps_cookie_for_live_ticket(client, yandex, letters):
    _, code = _started_yandex(client, yandex, letters)
    wrong = f"{(int(code) + 1) % 1_000_000:06d}"
    r = _confirm(client, wrong)
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    assert _reg_cookie_headers(r) == []
    assert client.post(RESUME_URL, json={}).status_code == 200


# ── источник ticket: тело (legacy) и конфликт ────────────────────────────────

def test_body_ticket_legacy_flow_without_cookie(client, yandex, letters):
    _, frag = _callback(client, yandex)
    client.cookies.clear()          # браузер без cookie: поток в памяти вкладки
    ticket = frag["ticket"]
    assert client.post(INIT_URL, json={"ticket": ticket}).status_code == 200
    code = letters[yandex.email][-1][0]
    r = _confirm(client, code, ticket=ticket)
    assert r.status_code == 200, r.text


def test_body_and_same_cookie_ticket_are_accepted(client, yandex, letters):
    _, frag = _callback(client, yandex)
    assert client.post(INIT_URL, json={"ticket": frag["ticket"]}).status_code == 200
    code = letters[yandex.email][-1][0]
    assert _confirm(client, code, ticket=frag["ticket"]).status_code == 200


def test_body_and_different_cookie_ticket_fail_closed(client, yandex, letters):
    _, first = _callback(client, yandex)          # вкладка A
    _, second = _callback(client, yandex)         # вкладка B: cookie = второй ticket
    assert first["ticket"] != second["ticket"]
    for url, body in (
        (INIT_URL, {"ticket": first["ticket"]}),
        (PREVIEW_URL, {"ticket": first["ticket"]}),
        (CONFIRM_URL, {"ticket": first["ticket"], "code": "123456", "consent_accepted": True}),
    ):
        r = client.post(url, json=body)
        assert r.status_code == 409, (url, r.text)
        assert r.json()["code"] == "oauth_registration_ticket_conflict"
    assert letters.get(yandex.email) is None                               # кода не было
    assert _users(yandex.email) == 0


# ── обычная регистрация не изменилась ────────────────────────────────────────

def test_ordinary_registration_unaffected_by_social_cookie(client, yandex, letters, foreign_test_email):
    # В браузере есть cookie social-регистрации; обычная регистрация — своя.
    _callback(client, yandex)
    email = yandex.email.replace("integ_", "integ_ord_", 1)
    r = client.post("/api/auth/register/init", json={
        "name": "Обычный Студент", "email": email, "password": "SecurePass42!",
    })
    assert r.status_code == 200, r.text
    code, html, _ = letters[email][-1]
    ref = re.search(r"/register/confirm#r=([0-9a-f-]{36})", html).group(1)
    assert "/register/social" not in html
    r = client.post("/api/auth/register/confirm", json={"registration_reference": ref, "code": code})
    assert r.status_code == 201 and r.json() == {"message": "Регистрация завершена", "email": email}


def test_ordinary_reference_is_not_a_social_ticket(client, yandex, letters):
    email = yandex.email.replace("integ_", "integ_ord_", 1)
    client.post("/api/auth/register/init", json={
        "name": "Обычный Студент", "email": email, "password": "SecurePass42!",
    })
    code, html, _ = letters[email][-1]
    ref = re.search(r"/register/confirm#r=([0-9a-f-]{36})", html).group(1)
    r = _confirm(client, code, ticket=ref)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert _users(email) == 0


def test_social_code_not_usable_by_ordinary_confirm(client, yandex, letters):
    ticket, code = _started_yandex(client, yandex, letters)
    r = client.post("/api/auth/register/confirm", json={"email": yandex.email, "code": code})
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"
    r = client.post("/api/auth/register/confirm", json={"registration_reference": ticket, "code": code})
    assert r.status_code == 422
    assert _users(yandex.email) == 0
    assert _otp(yandex.email).attempts == 0                              # попытки не потрачены
