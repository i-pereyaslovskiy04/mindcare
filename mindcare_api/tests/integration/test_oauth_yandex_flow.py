"""
Stage Social Auth 3A — НАСТОЯЩИЙ YandexProvider через generic pipeline Stage 2B.

Сеть не используется: Яндекс ID подменён httpx.MockTransport, который ведёт себя
честно — выдаёт code, привязанный к PKCE challenge из authorize URL, и при
обмене проверяет S256(code_verifier), client_id и одноразовость code; user-info
отдаёт профиль только по заголовку `Authorization: OAuth <token>`.

start → authorize URL Яндекса → callback → token → user-info → identity →
(неизвестна: social_registration_not_available | привязана: ticket → complete →
обычная сессия → /me → logout). auth_log пишет auth_method=yandex.
"""
import logging
import secrets
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.db.models import (
    AuthLog, OAuthAuthRequest, OAuthPendingTicket, User, UserOAuthIdentity, UserSession,
)
from app.db.session import SessionLocal
from app.oauth.providers.yandex import AUTHORIZE_URL, TOKEN_URL, USERINFO_URL, YandexProvider
from app.oauth.security import code_challenge_s256
from tests.integration.conftest import add_user_role, create_test_user
from tests.oauth_fakes import registered

COOKIE = "mindcare_oauth_state"
FRONTEND = "http://localhost:3000/auth/callback"
REDIRECT_URI = "http://localhost:8000/api/auth/oauth/yandex/callback"
CLIENT_ID = "synthetic0client0id0000000000001"


class MockYandex:
    """Минимальная честная модель Яндекс ID для MockTransport."""

    def __init__(self, subject: str):
        self.subject = subject
        self.client_id_in_profile = CLIENT_ID
        self.token_status = None             # принудительный статус token-ответа
        self._challenge_by_code: dict[str, str] = {}
        self._tokens: set[str] = set()
        self.token_requests: list[dict] = []
        self.userinfo_auth: list[str] = []
        self.issued_tokens: list[str] = []

    def issue_code(self, challenge: str) -> str:
        code = "ycode_" + secrets.token_hex(8)
        self._challenge_by_code[code] = challenge
        return code

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = f"{request.url.scheme}://{request.url.host}{request.url.path}"
        if url == TOKEN_URL and request.method == "POST":
            return self._token(request)
        if url == USERINFO_URL and request.method == "GET":
            return self._userinfo(request)
        return httpx.Response(404)

    def _token(self, request):
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_requests.append(form)
        if self.token_status is not None:
            return httpx.Response(self.token_status, json={
                "error": "invalid_grant", "error_description": "synthetic details",
            })
        challenge = self._challenge_by_code.pop(form.get("code"), None)   # одноразовый
        if (
            form.get("grant_type") != "authorization_code"
            or form.get("client_id") != CLIENT_ID
            or challenge is None
            or code_challenge_s256(form.get("code_verifier", "")) != challenge
        ):
            return httpx.Response(400, json={"error": "invalid_grant"})
        token = "ytoken_" + secrets.token_hex(12)
        self._tokens.add(token)
        self.issued_tokens.append(token)
        return httpx.Response(200, json={
            "token_type": "bearer", "access_token": token, "expires_in": 3600,
            "refresh_token": "yrefresh_" + secrets.token_hex(8), "scope": "login:email",
        })

    def _userinfo(self, request):
        auth = request.headers.get("authorization", "")
        self.userinfo_auth.append(auth)
        if not auth.startswith("OAuth ") or auth[6:] not in self._tokens:
            return httpx.Response(401)
        return httpx.Response(200, json={
            "id": self.subject, "login": "synthetic.login",
            "client_id": self.client_id_in_profile,
            "psuid": "1.synthetic." + secrets.token_hex(6),
            "default_email": "synthetic-yandex@yandex.ru",
        })


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
def yandex():
    mock = MockYandex(subject=str(10**12 + secrets.randbelow(10**11)))
    with registered(YandexProvider(CLIENT_ID, transport=httpx.MockTransport(mock))):
        yield mock


def _start(client):
    r = client.post("/api/auth/oauth/yandex/start")
    assert r.status_code == 200, r.text
    url = r.json()["authorize_url"]
    params = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    client.cookies.clear()
    return url, params


def _callback(client, params, cookie):
    return client.get(
        "/api/auth/oauth/yandex/callback", params=params,
        headers={"Cookie": f"{COOKIE}={cookie}"}, follow_redirects=False,
    )


def _yandex_round_trip(client, yandex):
    """start → «пользователь разрешил доступ» → callback. Возвращает ответ."""
    _, params = _start(client)
    code = yandex.issue_code(params["code_challenge"])
    return _callback(client, {"state": params["state"], "code": code}, params["state"])


def _fragment(response) -> dict:
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.query == ""
    assert f"{location.scheme}://{location.netloc}{location.path}" == FRONTEND
    return {k: v[0] for k, v in parse_qs(location.fragment).items()}


def _link(email, subject) -> int:
    user_id = int(create_test_user(email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(user_id=user_id, provider="yandex", provider_subject=subject))
        db.commit()
    return user_id


def _auth_mark() -> int:
    with SessionLocal() as db:
        return db.query(AuthLog.id).order_by(AuthLog.id.desc()).limit(1).scalar() or 0


def _auth_rows_since(mark):
    with SessionLocal() as db:
        return db.query(AuthLog).filter(AuthLog.id > mark).order_by(AuthLog.id).all()


# ── start ────────────────────────────────────────────────────────────────────

def test_start_returns_real_yandex_authorize_url(client, yandex):
    url, params = _start(client)
    parsed = urlparse(url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTHORIZE_URL
    assert set(params) == {
        "response_type", "client_id", "redirect_uri", "scope", "state",
        "code_challenge", "code_challenge_method",
    }
    assert params["client_id"] == CLIENT_ID
    assert params["redirect_uri"] == REDIRECT_URI
    assert params["scope"] == "login:email"
    assert params["code_challenge_method"] == "S256"
    assert "client_secret" not in url


def test_unconfigured_yandex_and_vk_are_unavailable(client):
    for provider in ("yandex", "vk"):
        r = client.post(f"/api/auth/oauth/{provider}/start")
        assert r.status_code == 404
        assert r.json()["code"] == "oauth_provider_unavailable"


# ── неизвестная identity: адаптер отработал, регистрации нет ─────────────────

def test_unknown_yandex_id_gives_registration_not_available(client, yandex):
    with SessionLocal() as db:
        users_before = db.query(User).count()
        identities_before = db.query(UserOAuthIdentity).count()
    mark = _auth_mark()

    frag = _fragment(_yandex_round_trip(client, yandex))

    assert frag == {"error": "social_registration_not_available"}
    # Реальный обмен: verifier прошёл S256-проверку «Яндекса», токен — в заголовке.
    assert len(yandex.token_requests) == 1 and len(yandex.issued_tokens) == 1
    assert yandex.userinfo_auth == [f"OAuth {yandex.issued_tokens[0]}"]
    rows = _auth_rows_since(mark)
    assert [(r.event, r.failure_reason, r.auth_method) for r in rows] == [
        ("failed_login", "oauth_identity_unknown", "yandex"),
    ]
    assert rows[0].user_email is None and rows[0].user_id is None
    with SessionLocal() as db:
        assert db.query(User).count() == users_before            # без auto-регистрации
        assert db.query(UserOAuthIdentity).count() == identities_before
        assert db.query(OAuthPendingTicket).filter(
            OAuthPendingTicket.provider_subject == yandex.subject).count() == 0
        # email Яндекса не использован для поиска/связывания
        assert db.query(User).filter(User.email == "synthetic-yandex@yandex.ru").count() == 0


# ── привязанная identity: полный вход ────────────────────────────────────────

@pytest.mark.parametrize("subject_kind", ["numeric", "non_numeric"])
def test_linked_identity_full_login(client, yandex, test_email, subject_kind):
    if subject_kind == "non_numeric":
        yandex.subject = "yid-" + secrets.token_hex(6) + ".A_b"
    user_id = _link(test_email, yandex.subject)
    mark = _auth_mark()

    frag = _fragment(_yandex_round_trip(client, yandex))
    assert frag.get("result") == "login", frag

    r = client.post("/api/auth/oauth/complete", json={"ticket": frag["ticket"]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"session_token", "expires_at", "roles", "role"}
    headers = {"Authorization": f"Bearer {body['session_token']}"}

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == test_email
    with SessionLocal() as db:
        assert db.query(UserSession).filter(UserSession.user_id == user_id).count() == 1

    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401

    rows = [(r.event, r.auth_method) for r in _auth_rows_since(mark)]
    assert rows == [("login", "yandex"), ("logout", None)]


def test_staff_with_yandex_identity_not_allowed(client, yandex, test_email):
    user_id = _link(test_email, yandex.subject)
    add_user_role(user_id, "psychologist")
    mark = _auth_mark()

    frag = _fragment(_yandex_round_trip(client, yandex))

    assert frag == {"error": "social_login_not_allowed"}
    assert [(r.failure_reason, r.auth_method) for r in _auth_rows_since(mark)] == [
        ("social_login_not_allowed", "yandex"),
    ]


# ── отказ Яндекса ────────────────────────────────────────────────────────────

def test_yandex_token_rejection_is_fail_closed(client, yandex, test_email):
    _link(test_email, yandex.subject)
    yandex.token_status = 400
    _, params = _start(client)
    code = yandex.issue_code(params["code_challenge"])
    mark = _auth_mark()

    r = _callback(client, {"state": params["state"], "code": code}, params["state"])

    assert _fragment(r) == {"error": "oauth_failed"}
    assert "synthetic details" not in r.headers["location"]
    assert yandex.userinfo_auth == []
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows_since(mark)] == [
        ("oauth_provider_error", "yandex"),
    ]


def test_tampered_verifier_rejected_by_yandex(client, yandex, test_email):
    """Code, выданный под чужой challenge, «Яндекс» не обменяет: PKCE реально
    связывает code с браузерной сессией, начавшей вход."""
    _link(test_email, yandex.subject)
    _, params = _start(client)
    foreign_code = yandex.issue_code(code_challenge_s256("x" * 64))
    r = _callback(client, {"state": params["state"], "code": foreign_code}, params["state"])
    assert _fragment(r) == {"error": "oauth_failed"}
    assert yandex.issued_tokens == []


def test_profile_client_id_mismatch_rejected(client, yandex, test_email):
    _link(test_email, yandex.subject)
    yandex.client_id_in_profile = "another-application"
    mark = _auth_mark()
    assert _fragment(_yandex_round_trip(client, yandex)) == {"error": "oauth_failed"}
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows_since(mark)] == [
        ("oauth_provider_error", "yandex"),
    ]


def test_user_cancel_on_yandex_page(client, yandex):
    _, params = _start(client)
    mark = _auth_mark()
    r = _callback(client, {
        "state": params["state"], "error": "access_denied",
        "error_description": "synthetic details",
    }, params["state"])
    assert _fragment(r) == {"error": "oauth_cancelled"}
    assert _auth_rows_since(mark) == []              # отмена не аудируется
    assert yandex.token_requests == []


def test_invalid_ticket_audit_has_no_method(client, yandex):
    mark = _auth_mark()
    r = client.post("/api/auth/oauth/complete", json={"ticket": "t" * 43})
    assert r.status_code == 400
    assert [(x.failure_reason, x.auth_method) for x in _auth_rows_since(mark)] == [
        ("oauth_ticket_invalid", None),
    ]


# ── секреты не попадают в логи приложения ────────────────────────────────────

def test_no_provider_secrets_in_logs(client, yandex, test_email, caplog):
    caplog.set_level(logging.DEBUG)
    _link(test_email, yandex.subject)
    _, params = _start(client)
    code = yandex.issue_code(params["code_challenge"])
    r = _callback(client, {"state": params["state"], "code": code}, params["state"])
    ticket = _fragment(r)["ticket"]
    session = client.post("/api/auth/oauth/complete", json={"ticket": ticket}).json()

    # Строки TestClient (роль браузера) содержат URL callback — их исключаем;
    # всё остальное (приложение, адаптер и его httpx-клиент) проверяется.
    app_text = "\n".join(
        rec.getMessage() for rec in caplog.records
        if "http://testserver" not in rec.getMessage()
    )
    for secret in (code, ticket, session["session_token"], *yandex.issued_tokens,
                   yandex.subject, "synthetic-yandex@yandex.ru"):
        assert secret not in app_text
    assert "OAuth " + yandex.issued_tokens[0] not in caplog.text
    assert all(rec.exc_info is None for rec in caplog.records
               if rec.name.startswith("app.oauth"))


# ── публичный список провайдеров (Stage Social Auth 3B) ──────────────────────

def test_public_config_lists_registered_yandex_only(client, yandex):
    r = client.get("/api/public/config")
    assert r.status_code == 200
    assert r.json()["social_providers"] == ["yandex"]
    assert CLIENT_ID not in r.text and "oauth.yandex.ru" not in r.text
    assert "callback" not in r.text


def test_public_config_without_provider_is_empty(client):
    r = client.get("/api/public/config")
    assert r.status_code == 200
    assert r.json()["social_providers"] == []
