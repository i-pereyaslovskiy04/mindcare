"""
Stage Social Auth VK-1A — НАСТОЯЩИЙ VKProvider через generic pipeline Stage 2B.

Сеть не используется: VK ID подменён httpx.MockTransport, который ведёт себя
честно — выдаёт code, привязанный к PKCE challenge, state и device_id, и при
обмене проверяет S256(code_verifier), client_id, device_id, state и
одноразовость code; user_info отдаёт профиль только по access_token в теле.

start → authorize URL VK → callback (code, state, device_id) → token →
user_info → identity →
  привязана:  ticket → complete → обычная сессия (auth_method=vk), без OTP;
  неизвестна: registration-ticket + шаг email (Stage VK-1B) → preview → init
              (выбор email, allowlist, занятость) → OTP MindCare → confirm.
Профиль «VK» содержит и лишние поля (телефон, аватар, пол, дата рождения) —
они не должны никуда попасть.
"""
import logging
import secrets
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.db.models import (
    AuthLog, OAuthAuthRequest, OAuthPendingTicket, OtpVerification, User,
    UserOAuthIdentity, UserSession,
)
from app.db.session import SessionLocal
from app.oauth.providers.vk import AUTHORIZE_URL, TOKEN_URL, USERINFO_URL, VKProvider
from app.oauth.security import code_challenge_s256
from tests.integration.conftest import create_test_user
from tests.oauth_fakes import registered

COOKIE = "mindcare_oauth_state"
FRONTEND = "http://localhost:3000/auth/callback"
REDIRECT_URI = "http://localhost:8000/api/auth/oauth/vk/callback"
CLIENT_ID = "54000001"
SENSITIVE_PHONE = "79990001122"
SENSITIVE_BIRTHDAY = "31.12.1999"
AVATAR = "https://pp.userapi.example/synthetic-avatar.jpg"


class MockVK:
    """Минимальная честная модель VK ID для MockTransport."""

    def __init__(self, subject: str):
        self.subject = subject
        # integ_* — адрес убирается cleanup'ом, если тест создаст аккаунт.
        self.email = f"integ_vk{subject}@vk.ru"
        self.first_name = "Синтетик"
        self.last_name = "Вконтактов"
        self._grants: dict[str, dict] = {}
        self._tokens: set[str] = set()
        self.token_requests: list[dict] = []
        self.userinfo_requests: list[dict] = []
        self.issued_tokens: list[str] = []
        self.issued_device_ids: list[str] = []

    def issue_callback(self, params: dict) -> dict:
        """«Пользователь разрешил доступ»: параметры, с которыми VK вернёт его."""
        code = "vk2.a." + secrets.token_hex(12)
        device_id = "dev_" + secrets.token_hex(10)
        self._grants[code] = {
            "challenge": params["code_challenge"], "state": params["state"],
            "device_id": device_id, "redirect_uri": params["redirect_uri"],
        }
        self.issued_device_ids.append(device_id)
        return {
            "code": code, "state": params["state"], "device_id": device_id,
            "type": "code_v2", "expires_in": "600",
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if url == TOKEN_URL and request.method == "POST":
            return self._token(form)
        if url == USERINFO_URL and request.method == "POST":
            return self._userinfo(form)
        return httpx.Response(404)

    def _token(self, form):
        self.token_requests.append(form)
        grant = self._grants.pop(form.get("code"), None)        # одноразовый
        if (
            grant is None
            or form.get("grant_type") != "authorization_code"
            or form.get("client_id") != CLIENT_ID
            or form.get("device_id") != grant["device_id"]
            or form.get("state") != grant["state"]
            or form.get("redirect_uri") != grant["redirect_uri"]
            or code_challenge_s256(form.get("code_verifier", "")) != grant["challenge"]
        ):
            return httpx.Response(400, json={"error": "invalid_grant"})
        token = "vk2.a." + secrets.token_hex(16)
        self._tokens.add(token)
        self.issued_tokens.append(token)
        return httpx.Response(200, json={
            "access_token": token, "refresh_token": "vk2.r." + secrets.token_hex(8),
            "id_token": "idt." + secrets.token_hex(8), "expires_in": 3600,
            "user_id": int(self.subject), "state": grant["state"],
            "scope": "vkid.personal_info email",
        })

    def _userinfo(self, form):
        self.userinfo_requests.append(form)
        if form.get("client_id") != CLIENT_ID or form.get("access_token") not in self._tokens:
            return httpx.Response(200, json={"error": "invalid_token"})
        user = {
            "user_id": self.subject, "first_name": self.first_name,
            "last_name": self.last_name, "phone": SENSITIVE_PHONE, "avatar": AVATAR,
            "sex": 2, "verified": True, "birthday": SENSITIVE_BIRTHDAY,
        }
        if self.email is not None:
            user["email"] = self.email
        return httpx.Response(200, json={"user": user})


# ── fixtures / helpers ───────────────────────────────────────────────────────

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
    mock = MockVK(subject=str(10**9 + secrets.randbelow(10**9)))
    with registered(VKProvider(CLIENT_ID, transport=httpx.MockTransport(mock))):
        yield mock


def _start(client):
    r = client.post("/api/auth/oauth/vk/start")
    assert r.status_code == 200, r.text
    url = r.json()["authorize_url"]
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    client.cookies.clear()
    return url, params


def _callback(client, params, cookie):
    return client.get(
        "/api/auth/oauth/vk/callback", params=params,
        headers={"Cookie": f"{COOKIE}={cookie}"}, follow_redirects=False,
    )


def _round_trip(client, vk):
    """start → «пользователь разрешил доступ» → callback. Возвращает ответ."""
    _, params = _start(client)
    return _callback(client, vk.issue_callback(params), params["state"])


def _fragment(response) -> dict:
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.query == ""
    assert f"{location.scheme}://{location.netloc}{location.path}" == FRONTEND
    return {k: v[0] for k, v in parse_qs(location.fragment).items()}


def _link(email, subject) -> int:
    user_id = int(create_test_user(email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=user_id, provider="vk", provider_subject=subject))
        db.commit()
    return user_id


def _auth_mark() -> int:
    with SessionLocal() as db:
        return db.query(AuthLog.id).order_by(AuthLog.id.desc()).limit(1).scalar() or 0


def _auth_rows_since(mark):
    with SessionLocal() as db:
        return db.query(AuthLog).filter(AuthLog.id > mark).order_by(AuthLog.id).all()


# ── start ────────────────────────────────────────────────────────────────────

def test_start_returns_real_vk_authorize_url(client, vk):
    url, params = _start(client)
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTHORIZE_URL
    assert set(params) == {
        "response_type", "client_id", "redirect_uri", "scope", "state",
        "code_challenge", "code_challenge_method",
    }
    assert params["client_id"] == CLIENT_ID
    assert params["redirect_uri"] == REDIRECT_URI
    assert params["scope"] == "vkid.personal_info email"
    assert params["code_challenge_method"] == "S256"
    assert len(params["state"]) >= 32
    assert "client_secret" not in url and "code_verifier" not in url


def test_public_config_lists_registered_vk(client, vk):
    r = client.get("/api/public/config")
    assert r.status_code == 200
    assert r.json()["social_providers"] == ["vk"]
    assert CLIENT_ID not in r.text


def test_vk_start_unavailable_without_adapter(client):
    r = client.post("/api/auth/oauth/vk/start")
    assert r.status_code == 404 and r.json()["code"] == "oauth_provider_unavailable"


# ── неизвестная identity: регистрация с шагом email (Stage VK-1B) ───────────

PREVIEW_URL = "/api/auth/oauth/registration/preview"
INIT_URL = "/api/auth/oauth/registration/init"
CONFIRM_URL = "/api/auth/oauth/registration/confirm"


def _registration_ticket(client, vk) -> str:
    frag = _fragment(_round_trip(client, vk))
    assert frag.get("result") == "registration" and frag.get("step") == "email", frag
    assert set(frag) == {"result", "ticket", "step"}
    return frag["ticket"]


def test_unknown_vk_id_starts_registration_and_creates_nothing_yet(client, vk, caplog):
    with SessionLocal() as db:
        users_before = db.query(User).count()
        identities_before = db.query(UserOAuthIdentity).count()
        otps_before = db.query(OtpVerification).count()
    caplog.set_level(logging.INFO)
    mark = _auth_mark()

    response = _round_trip(client, vk)
    ticket = _registration_ticket_from(response)

    # Реальный обмен состоялся: device_id и state дошли до token, токен — в теле.
    token_req, = vk.token_requests
    assert token_req["device_id"] == vk.issued_device_ids[0]
    assert token_req["redirect_uri"] == REDIRECT_URI
    assert "client_secret" not in token_req
    assert vk.userinfo_requests == [{"client_id": CLIENT_ID, "access_token": vk.issued_tokens[0]}]
    # Email VK не попадает в URL — только в ticket.
    assert vk.email not in response.headers["location"]

    with SessionLocal() as db:
        assert db.query(User).count() == users_before             # callback не регистрирует
        assert db.query(UserOAuthIdentity).count() == identities_before
        assert db.query(OtpVerification).count() == otps_before  # код ещё не отправлялся
        row = db.query(OAuthPendingTicket).filter(
            OAuthPendingTicket.provider_subject == vk.subject).one()
        assert (row.kind, row.provider, row.user_id) == ("registration", "vk", None)
        assert (row.email, row.suggested_name) == (vk.email, "Синтетик Вконтактов")
        assert row.ticket_hash != ticket
        row_text = " ".join(str(v) for v in (
            row.ticket_hash, row.provider_subject, row.email, row.suggested_name))
        for value in (SENSITIVE_PHONE, SENSITIVE_BIRTHDAY, AVATAR, *vk.issued_tokens,
                      *vk.issued_device_ids):
            assert value not in row_text

    assert _auth_rows_since(mark) == []                 # штатное начало регистрации
    assert "[oauth probe]" not in caplog.text            # временная диагностика убрана
    app_text = "\n".join(
        r.getMessage() for r in caplog.records if "http://testserver" not in r.getMessage()
    )
    for secret in (vk.subject, vk.email, "Синтетик", SENSITIVE_PHONE, AVATAR,
                   *vk.issued_tokens, *vk.issued_device_ids, ticket):
        assert secret not in app_text


def _registration_ticket_from(response) -> str:
    frag = _fragment(response)
    assert frag.get("result") == "registration" and frag.get("step") == "email", frag
    return frag["ticket"]


def test_unknown_vk_id_without_email_gets_ticket_with_empty_email(client, vk):
    """Живой smoke VK-1A: VK не вернул email — адрес пользователь укажет сам."""
    vk.email = None
    ticket = _registration_ticket(client, vk)
    with SessionLocal() as db:
        row = db.query(OAuthPendingTicket).filter(
            OAuthPendingTicket.provider_subject == vk.subject).one()
        assert row.email is None and row.suggested_name == "Синтетик Вконтактов"
    r = client.post(PREVIEW_URL, json={"ticket": ticket})
    assert r.status_code == 200
    assert r.json() == {
        "provider": "vk", "email_masked": None, "email_allowed": False,
        "email_editable": True,
    }


def test_vk_registration_end_to_end_with_manual_email_then_direct_login(
    client, vk, test_email, capture_emails,
):
    """Полный сценарий на настоящем адаптере: VK без email → пользователь
    вводит адрес → OTP MindCare → согласие → аккаунт; второй вход — без OTP."""
    vk.email = None
    ticket = _registration_ticket(client, vk)

    r = client.post(INIT_URL, json={"ticket": ticket, "email": test_email.upper()})
    assert r.status_code == 200, r.text
    assert test_email not in r.text and "***@" in r.json()["email_masked"]
    mark = _auth_mark()
    r = client.post(CONFIRM_URL, json={
        "ticket": ticket, "code": capture_emails[test_email][-1], "consent_accepted": True,
    })
    assert r.status_code == 200, r.text
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["email"] == test_email and me["has_password"] is False
    assert me["name"] == "Синтетик Вконтактов" and me["roles"] == ["student"]
    assert [(x.event, x.auth_method) for x in _auth_rows_since(mark)] == [
        ("registration_succeeded", "vk"), ("login", "vk"),
    ]
    with SessionLocal() as db:
        identity = db.query(UserOAuthIdentity).filter_by(provider_subject=vk.subject).one()
        assert identity.provider == "vk"
    assert client.post("/api/auth/logout", headers=headers).status_code == 200

    # Повторный вход тем же VK id: обычный login-ticket, без email и без OTP.
    frag = _fragment(_round_trip(client, vk))
    assert set(frag) == {"result", "ticket"} and frag["result"] == "login"
    with SessionLocal() as db:
        assert db.query(OtpVerification).filter(
            OtpVerification.email == test_email).count() == 0
    r = client.post("/api/auth/oauth/complete", json={"ticket": frag["ticket"]})
    assert r.status_code == 200
    headers = {"Authorization": f"Bearer {r.json()['session_token']}"}
    assert client.get("/api/auth/me", headers=headers).json()["email"] == test_email


def test_vk_registration_with_provider_email_on_allowed_domain(
    client, vk, test_email, capture_emails,
):
    vk.email = test_email                                # адрес VK на разрешённом домене
    ticket = _registration_ticket(client, vk)
    r = client.post(PREVIEW_URL, json={"ticket": ticket})
    assert r.json()["email_allowed"] is True and test_email not in r.text

    assert client.post(INIT_URL, json={"ticket": ticket}).status_code == 200   # «Продолжить»
    r = client.post(CONFIRM_URL, json={
        "ticket": ticket, "code": capture_emails[test_email][-1], "consent_accepted": True,
    })
    assert r.status_code == 200, r.text


def test_vk_provider_email_on_foreign_domain_cannot_be_used(client, vk, capture_emails):
    """Адрес VK по умолчанию — @vk.ru, вне allowlist: продолжить с ним нельзя."""
    ticket = _registration_ticket(client, vk)
    r = client.post(PREVIEW_URL, json={"ticket": ticket})
    assert r.json()["email_allowed"] is False and r.json()["email_masked"] is not None
    r = client.post(INIT_URL, json={"ticket": ticket})
    assert r.status_code == 422 and r.json()["code"] == "domain_not_allowed"
    assert capture_emails == {}


# ── привязанная identity: полный вход ────────────────────────────────────────

def test_linked_vk_identity_full_login(client, vk, test_email):
    user_id = _link(test_email, vk.subject)
    mark = _auth_mark()

    frag = _fragment(_round_trip(client, vk))
    assert set(frag) == {"result", "ticket"} and frag["result"] == "login"

    r = client.post("/api/auth/oauth/complete", json={"ticket": frag["ticket"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"session_token", "expires_at", "roles", "role"}
    headers = {"Authorization": f"Bearer {body['session_token']}"}

    me = client.get("/api/auth/me", headers=headers)
    # Вход не синхронизирует профиль: email и имя — прежние MindCare.
    assert me.status_code == 200 and me.json()["email"] == test_email
    with SessionLocal() as db:
        assert db.query(UserSession).filter(UserSession.user_id == user_id).count() == 1
        assert db.query(OtpVerification).filter(
            OtpVerification.email.in_([test_email, vk.email])).count() == 0   # без OTP

    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    rows = [(r.event, r.auth_method) for r in _auth_rows_since(mark)]
    assert rows == [("login", "vk"), ("logout", None)]


def test_linked_vk_identity_logs_in_without_email(client, vk, test_email):
    _link(test_email, vk.subject)
    vk.email = None
    assert _fragment(_round_trip(client, vk)).get("result") == "login"


def test_disabled_linked_vk_account_is_denied(client, vk, test_email):
    user_id = _link(test_email, vk.subject)
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update({"is_active": False})
        db.commit()
    mark = _auth_mark()
    assert _fragment(_round_trip(client, vk)) == {"error": "account_unavailable"}
    assert [(r.event, r.failure_reason, r.auth_method) for r in _auth_rows_since(mark)] == [
        ("failed_login", "account_disabled", "vk"),
    ]


def test_vk_identity_is_not_yandex_identity(client, vk, test_email):
    """Ключ identity — (provider, subject): тот же subject у Яндекса вход через VK не даёт."""
    user_id = int(create_test_user(test_email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=user_id, provider="yandex",
                                 provider_subject=vk.subject))
        db.commit()
    # Не вход: начинается регистрация новой VK identity.
    frag = _fragment(_round_trip(client, vk))
    assert frag.get("result") == "registration" and frag.get("step") == "email"


# ── callback: device_id, отмена, повтор ──────────────────────────────────────

def test_callback_without_device_id_fails_closed_without_exchange(client, vk):
    _, params = _start(client)
    answer = vk.issue_callback(params)
    del answer["device_id"]
    mark = _auth_mark()
    frag = _fragment(_callback(client, answer, params["state"]))
    assert frag == {"error": "oauth_failed"}
    assert vk.token_requests == []
    assert [(r.failure_reason, r.auth_method) for r in _auth_rows_since(mark)] == [
        ("oauth_provider_error", "vk"),
    ]


def test_callback_with_foreign_device_id_is_rejected_by_provider(client, vk, test_email):
    _link(test_email, vk.subject)
    _, params = _start(client)
    answer = vk.issue_callback(params)
    answer["device_id"] = "dev_foreign_device"
    assert _fragment(_callback(client, answer, params["state"])) == {"error": "oauth_failed"}
    assert vk.issued_tokens == []


def test_callback_as_payload_json_works(client, vk, test_email):
    """Второй документированный вид возврата — один параметр `payload`."""
    import json
    _link(test_email, vk.subject)
    _, params = _start(client)
    answer = vk.issue_callback(params)
    # state дублируется отдельным параметром не будет: ядро берёт его из адаптера.
    frag = _fragment(_callback(client, {"payload": json.dumps(answer)}, params["state"]))
    assert frag.get("result") == "login", frag


def test_cancel_is_not_audited(client, vk):
    _, params = _start(client)
    mark = _auth_mark()
    frag = _fragment(_callback(
        client, {"state": params["state"], "error": "access_denied",
                 "error_description": "RAW provider text"}, params["state"]))
    assert frag == {"error": "oauth_cancelled"}
    assert _auth_rows_since(mark) == [] and vk.token_requests == []


def test_callback_replay_is_rejected(client, vk, test_email):
    _link(test_email, vk.subject)
    _, params = _start(client)
    answer = vk.issue_callback(params)
    assert _fragment(_callback(client, answer, params["state"])).get("result") == "login"
    assert _fragment(_callback(client, answer, params["state"])) == {"error": "oauth_failed"}
    assert len(vk.token_requests) == 1          # повтор не дошёл до провайдера


# ── секреты не попадают в логи приложения ────────────────────────────────────

def test_no_provider_secrets_in_logs(client, vk, test_email, caplog):
    caplog.set_level(logging.DEBUG)
    _link(test_email, vk.subject)
    _, params = _start(client)
    answer = vk.issue_callback(params)
    ticket = _fragment(_callback(client, answer, params["state"]))["ticket"]
    session = client.post("/api/auth/oauth/complete", json={"ticket": ticket}).json()

    # Строки TestClient (роль браузера) содержат URL callback — их исключаем.
    app_text = "\n".join(
        rec.getMessage() for rec in caplog.records
        if "http://testserver" not in rec.getMessage()
    )
    for secret in (answer["code"], answer["device_id"], ticket, session["session_token"],
                   *vk.issued_tokens, vk.subject, vk.email, SENSITIVE_PHONE, AVATAR):
        assert secret not in app_text
    assert all(rec.exc_info is None for rec in caplog.records
               if rec.name.startswith("app.oauth"))
