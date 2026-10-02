"""
Stage Social Auth 2B — social login core end-to-end на FakeProvider:
POST start → GET callback → POST complete → обычная user_sessions сессия.

FakeProvider регистрируется фикстурой (production-реестр пуст) под именем
`yandex`/`vk` и восстанавливается после теста. Raw state/ticket/code/verifier
и session token нигде не логируются и не хранятся — это проверяется явно.
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import func

from app.audit import service as audit_service
from app.auth import storage as auth_storage
from app.core.encryption import decrypt_text, encrypt_text
from app.db.models import (
    AuthLog, OAuthAuthRequest, OAuthPendingTicket, User, UserOAuthIdentity, UserSession,
)
from app.db.session import SessionLocal
from app.oauth import service as oauth_service
from app.oauth import storage as oauth_storage
from tests.integration.conftest import add_user_role, create_test_user, remove_all_user_roles
from tests.oauth_fakes import (
    FakeProvider, challenge_from_authorize_url, registered, state_from_authorize_url,
)

COOKIE = "mindcare_oauth_state"
FRONTEND = "http://localhost:3000/auth/callback"


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
def fake():
    with registered(FakeProvider("yandex")) as provider:
        yield provider


# ── helpers ──────────────────────────────────────────────────────────────────

def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _start(client, provider="yandex", **kw):
    r = client.post(f"/api/auth/oauth/{provider}/start", **kw)
    assert r.status_code == 200, r.text
    state = state_from_authorize_url(r.json()["authorize_url"])
    client.cookies.clear()   # cookie передаём явно, а не из общего jar
    return state, r


def _callback(client, params, cookie=None, provider="yandex"):
    headers = {"Cookie": f"{COOKIE}={cookie}"} if cookie else {}
    return client.get(
        f"/api/auth/oauth/{provider}/callback", params=params,
        headers=headers, follow_redirects=False,
    )


def _fragment(response) -> dict:
    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.query == ""                       # ничего в query
    assert f"{location.scheme}://{location.netloc}{location.path}" == FRONTEND
    return {k: v[0] for k, v in parse_qs(location.fragment).items()}


def _cookie_cleared(response) -> bool:
    return any(
        h.startswith(f"{COOKIE}=") and "max-age=0" in h.lower()
        for h in response.headers.get_list("set-cookie")
    )


def _link(email, fake, provider="yandex") -> int:
    user_id = int(create_test_user(email)["id"])
    with SessionLocal() as db:
        db.add(UserOAuthIdentity(
            user_id=user_id, provider=provider, provider_subject=fake.subject,
        ))
        db.commit()
    return user_id


def _login_ticket(client, fake) -> str:
    state, _ = _start(client)
    r = _callback(client, {"state": state, "code": fake.issue_code(state)}, cookie=state)
    frag = _fragment(r)
    assert frag.get("result") == "login", frag
    return frag["ticket"]


def _complete(client, ticket):
    return client.post("/api/auth/oauth/complete", json={"ticket": ticket})


def _request_row(state):
    with SessionLocal() as db:
        return db.get(OAuthAuthRequest, _sha(state))


def _ticket_row(ticket):
    with SessionLocal() as db:
        return db.get(OAuthPendingTicket, _sha(ticket))


def _sessions(user_id) -> int:
    with SessionLocal() as db:
        return db.query(UserSession).filter(UserSession.user_id == user_id).count()


def _auth_mark() -> int:
    with SessionLocal() as db:
        return db.query(func.coalesce(func.max(AuthLog.id), 0)).scalar()


def _auth_rows_since(mark):
    with SessionLocal() as db:
        return db.query(AuthLog).filter(AuthLog.id > mark).order_by(AuthLog.id).all()


def _failed_codes_since(mark) -> list:
    return [r.failure_reason for r in _auth_rows_since(mark) if r.event == "failed_login"]


def _failed_methods_since(mark) -> list:
    """auth_method строк failed_login (Stage Social Auth 3A)."""
    return [r.auth_method for r in _auth_rows_since(mark) if r.event == "failed_login"]


def _set(model_filter, **values):
    with SessionLocal() as db:
        model_filter(db).update(values, synchronize_session=False)
        db.commit()


# ── START ────────────────────────────────────────────────────────────────────

def test_start_unknown_provider_is_404_without_cookie(client):
    r = client.post("/api/auth/oauth/yandex/start")
    assert r.status_code == 404
    assert r.json()["code"] == "oauth_provider_unavailable"
    assert not r.headers.get_list("set-cookie")


def test_start_stores_only_hash_and_encrypted_verifier(client, fake):
    before = datetime.now(timezone.utc)
    state, r = _start(client)
    row = _request_row(state)

    assert row is not None and row.intent == "login" and row.user_id is None
    assert row.consumed_at is None
    assert row.state_hash == _sha(state) and state not in row.state_hash
    assert row.code_verifier_enc.startswith("enc:v1:")
    verifier = decrypt_text(row.code_verifier_enc)
    assert verifier not in row.code_verifier_enc
    # PKCE: challenge в URL — S256 от сохранённого verifier.
    assert challenge_from_authorize_url(r.json()["authorize_url"]) == (
        oauth_service.code_challenge_s256(verifier)
    )
    ttl = row.expires_at - before
    assert timedelta(minutes=9, seconds=50) <= ttl <= timedelta(minutes=10, seconds=10)
    assert fake.last_redirect_uri == "http://localhost:8000/api/auth/oauth/yandex/callback"


def test_start_cookie_attributes_dev(client, fake):
    state, r = _start(client)
    cookies = [h for h in r.headers.get_list("set-cookie") if h.startswith(f"{COOKIE}=")]
    assert len(cookies) == 1
    raw = cookies[0]
    attrs = raw.lower()
    assert raw.split(";")[0] == f"{COOKIE}={state}"
    assert "httponly" in attrs and "samesite=lax" in attrs
    assert "path=/api/auth/oauth" in attrs and "max-age=600" in attrs
    assert "domain=" not in attrs
    assert "secure" not in attrs
    assert r.headers["cache-control"] == "no-store"


def test_start_cookie_secure_with_https_callback_base(client, fake, monkeypatch):
    monkeypatch.setattr(oauth_service.settings, "OAUTH_CALLBACK_BASE_URL", "https://mindcare.example")
    _, r = _start(client)
    raw = next(h for h in r.headers.get_list("set-cookie") if h.startswith(f"{COOKIE}="))
    assert "secure" in raw.lower()


def test_start_ignores_intent_from_client(client, fake):
    state, _ = _start(client, json={"intent": "link", "user_id": 1})
    row = _request_row(state)
    assert row.intent == "login" and row.user_id is None


def test_start_rate_limited_by_ip(client, fake):
    for _ in range(20):
        _start(client)
    r = client.post("/api/auth/oauth/yandex/start")
    assert r.status_code == 429


# ── CALLBACK ─────────────────────────────────────────────────────────────────

def test_callback_success_issues_login_ticket_in_fragment(client, fake, test_email):
    user_id = _link(test_email, fake)
    state, _ = _start(client)
    r = _callback(client, {"state": state, "code": fake.issue_code(state)}, cookie=state)

    frag = _fragment(r)
    assert set(frag) == {"result", "ticket"} and frag["result"] == "login"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-store"
    assert _cookie_cleared(r)
    assert _request_row(state).consumed_at is not None

    ticket = frag["ticket"]
    row = _ticket_row(ticket)
    assert row is not None and row.ticket_hash == _sha(ticket) and row.ticket_hash != ticket
    assert (row.kind, row.user_id, row.provider, row.provider_subject) == (
        "login", user_id, "yandex", fake.subject,
    )
    assert row.email is None and row.consumed_at is None
    assert timedelta(minutes=1, seconds=50) <= row.expires_at - row.created_at <= timedelta(minutes=2, seconds=10)
    assert _sessions(user_id) == 0                     # сессии на callback нет
    assert "session" not in r.headers["location"].lower()


def test_callback_state_replay_rejected(client, fake, test_email):
    _link(test_email, fake)
    state, _ = _start(client)
    params = {"state": state, "code": fake.issue_code(state)}
    assert _fragment(_callback(client, params, cookie=state))["result"] == "login"

    mark = _auth_mark()
    replay = _callback(client, params, cookie=state)
    assert _fragment(replay) == {"error": "oauth_failed"}
    assert _failed_codes_since(mark) == ["oauth_state_invalid"]


def test_callback_expired_state_rejected(client, fake, test_email):
    _link(test_email, fake)
    state, _ = _start(client)
    past = datetime.now(timezone.utc) - timedelta(minutes=20)
    _set(lambda db: db.query(OAuthAuthRequest).filter_by(state_hash=_sha(state)),
         created_at=past, expires_at=past + timedelta(minutes=10))

    r = _callback(client, {"state": state, "code": fake.issue_code(state)}, cookie=state)
    assert _fragment(r) == {"error": "oauth_failed"}
    assert _cookie_cleared(r)


def test_callback_to_other_provider_does_not_consume(client, fake, test_email):
    _link(test_email, fake)
    state, _ = _start(client)
    with registered(FakeProvider("vk")):
        r = _callback(client, {"state": state, "code": "x"}, cookie=state, provider="vk")
    assert _fragment(r) == {"error": "oauth_failed"}
    assert _request_row(state).consumed_at is None


@pytest.mark.parametrize("case", ["missing_state", "missing_cookie", "mismatched_cookie"])
def test_callback_binding_failure_keeps_state_and_cookie(client, fake, case):
    state, _ = _start(client)
    code = fake.issue_code(state)
    params = {"code": code} if case == "missing_state" else {"state": state, "code": code}
    cookie = {"missing_state": state, "missing_cookie": None,
              "mismatched_cookie": secrets.token_urlsafe(32)}[case]

    mark = _auth_mark()
    r = _callback(client, params, cookie=cookie)

    assert _fragment(r) == {"error": "oauth_failed"}
    assert _request_row(state).consumed_at is None          # state не сожжён
    assert not r.headers.get_list("set-cookie")             # легитимный cookie не тронут
    assert _failed_codes_since(mark) == ["oauth_state_invalid"]
    assert fake.resolve_calls == 0


def test_callback_cancel_consumes_state_without_audit(client, fake):
    state, _ = _start(client)
    mark = _auth_mark()
    r = _callback(client, {"state": state, "error": "access_denied"}, cookie=state)

    assert _fragment(r) == {"error": "oauth_cancelled"}
    assert _cookie_cleared(r)
    assert _request_row(state).consumed_at is not None
    assert _auth_rows_since(mark) == []


def test_callback_provider_error_consumes_state_and_hides_text(client, fake):
    state, _ = _start(client)
    mark = _auth_mark()
    r = _callback(client, {
        "state": state, "error": "server_error", "error_description": "provider internals",
    }, cookie=state)

    assert _fragment(r) == {"error": "oauth_failed"}
    assert "internals" not in r.headers["location"]
    assert _request_row(state).consumed_at is not None
    assert _failed_codes_since(mark) == ["oauth_provider_error"]


def test_callback_provider_timeout_is_fail_closed(client, fake, test_email):
    _link(test_email, fake)
    fake.mode = "unavailable"
    state, _ = _start(client)
    params = {"state": state, "code": fake.issue_code(state)}
    mark = _auth_mark()

    assert _fragment(_callback(client, params, cookie=state)) == {"error": "oauth_failed"}
    fake.mode = "success"
    # state сожжён: повтор после восстановления провайдера невозможен.
    assert _fragment(_callback(client, params, cookie=state)) == {"error": "oauth_failed"}
    assert _failed_codes_since(mark) == ["oauth_provider_error", "oauth_state_invalid"]
    assert _failed_methods_since(mark) == ["yandex", "yandex"]


def test_callback_pkce_verifier_is_enforced(client, fake, test_email):
    _link(test_email, fake)
    state, _ = _start(client)
    _set(lambda db: db.query(OAuthAuthRequest).filter_by(state_hash=_sha(state)),
         code_verifier_enc=encrypt_text(secrets.token_urlsafe(64)))
    r = _callback(client, {"state": state, "code": fake.issue_code(state)}, cookie=state)
    assert _fragment(r) == {"error": "oauth_failed"}


def test_callback_unknown_identity_creates_nothing(client, fake):
    with SessionLocal() as db:
        users_before = db.query(User).count()
        identities_before = db.query(UserOAuthIdentity).count()
    state, _ = _start(client)
    mark = _auth_mark()
    r = _callback(client, {"state": state, "code": fake.issue_code(state)}, cookie=state)

    assert _fragment(r) == {"error": "social_registration_not_available"}
    assert _failed_codes_since(mark) == ["oauth_identity_unknown"]
    assert _failed_methods_since(mark) == ["yandex"]   # провайдер из реестра
    with SessionLocal() as db:
        assert db.query(User).count() == users_before
        assert db.query(UserOAuthIdentity).count() == identities_before
        assert db.query(OAuthPendingTicket).filter(
            OAuthPendingTicket.provider_subject == fake.subject).count() == 0


def _deny_disabled(user_id):
    _set(lambda db: db.query(User).filter_by(id=user_id), is_active=False)


def _deny_deleted(user_id):
    _set(lambda db: db.query(User).filter_by(id=user_id), deleted_at=datetime.now(timezone.utc))


def _deny_no_roles(user_id):
    remove_all_user_roles(user_id)


def _deny_staff(user_id):
    add_user_role(user_id, "psychologist")


_CALLBACK_DENIALS = [
    (_deny_disabled, "account_unavailable", "account_disabled"),
    (_deny_deleted, "account_unavailable", "account_disabled"),
    (_deny_no_roles, "account_unavailable", "no_active_roles"),
    (_deny_staff, "social_login_not_allowed", "social_login_not_allowed"),
]


@pytest.mark.parametrize("deny,external,audit", _CALLBACK_DENIALS)
def test_callback_denies_without_ticket(client, fake, test_email, deny, external, audit):
    user_id = _link(test_email, fake)
    deny(user_id)
    state, _ = _start(client)
    mark = _auth_mark()
    r = _callback(client, {"state": state, "code": fake.issue_code(state)}, cookie=state)

    assert _fragment(r) == {"error": external}
    assert _failed_codes_since(mark) == [audit]
    assert _failed_methods_since(mark) == ["yandex"]
    with SessionLocal() as db:
        assert db.query(OAuthPendingTicket).filter_by(user_id=user_id).count() == 0


# ── COMPLETE ─────────────────────────────────────────────────────────────────

def test_complete_creates_normal_session(client, fake, test_email):
    user_id = _link(test_email, fake)
    ticket = _login_ticket(client, fake)
    mark = _auth_mark()

    r = _complete(client, ticket)

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"session_token", "expires_at", "roles", "role"}
    assert body["roles"] == ["student"] and body["role"] == "student"
    token = body["session_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == test_email
    assert _sessions(user_id) == 1
    assert _ticket_row(ticket).consumed_at is not None
    with SessionLocal() as db:
        assert db.query(UserOAuthIdentity).filter_by(user_id=user_id).one().last_login_at is not None
        assert db.get(User, user_id).last_login is not None

    logins = [x for x in _auth_rows_since(mark) if x.event == "login"]
    assert len(logins) == 1 and logins[0].user_email == test_email
    assert logins[0].session_id == hashlib.sha256(token.encode()).hexdigest()
    assert logins[0].auth_method == "yandex"           # из списанного ticket

    logout_mark = _auth_mark()
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    logouts = [x for x in _auth_rows_since(logout_mark) if x.event == "logout"]
    assert len(logouts) == 1 and logouts[0].auth_method is None


def test_complete_ticket_is_single_use(client, fake, test_email):
    user_id = _link(test_email, fake)
    ticket = _login_ticket(client, fake)
    assert _complete(client, ticket).status_code == 200

    mark = _auth_mark()
    again = _complete(client, ticket)
    assert again.status_code == 400 and again.json()["code"] == "oauth_ticket_invalid"
    assert _failed_codes_since(mark) == ["oauth_ticket_invalid"]
    assert _failed_methods_since(mark) == [None]       # провайдер неизвестен
    assert _sessions(user_id) == 1


def test_complete_expired_ticket(client, fake, test_email):
    _link(test_email, fake)
    ticket = _login_ticket(client, fake)
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    _set(lambda db: db.query(OAuthPendingTicket).filter_by(ticket_hash=_sha(ticket)),
         created_at=past, expires_at=past + timedelta(minutes=2))
    r = _complete(client, ticket)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"


def test_complete_rejects_other_ticket_kinds_without_consuming(client):
    ticket = secrets.token_urlsafe(32)
    with SessionLocal() as db:
        db.add(OAuthPendingTicket(
            ticket_hash=_sha(ticket), kind="registration", provider="yandex",
            provider_subject=f"integ_{secrets.token_hex(6)}",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=2),
        ))
        db.commit()
    r = _complete(client, ticket)
    assert r.status_code == 400 and r.json()["code"] == "oauth_ticket_invalid"
    assert _ticket_row(ticket).consumed_at is None


@pytest.mark.parametrize("ticket", ["unknown-ticket-value", ""])
def test_complete_unknown_or_empty_ticket(client, ticket):
    r = _complete(client, ticket)
    assert r.status_code in (400, 422)
    assert r.status_code != 401


def _reassign_identity(user_id, fake, other_email):
    other = int(create_test_user(other_email)["id"])
    _set(lambda db: db.query(UserOAuthIdentity).filter_by(user_id=user_id), user_id=other)


def _remove_identity(user_id, fake, _):
    with SessionLocal() as db:
        db.query(UserOAuthIdentity).filter_by(user_id=user_id).delete()
        db.commit()


_COMPLETE_DENIALS = [
    (lambda uid, f, e: _deny_disabled(uid), 403, "account_unavailable", "account_disabled"),
    (lambda uid, f, e: _deny_deleted(uid), 403, "account_unavailable", "account_disabled"),
    (lambda uid, f, e: _deny_no_roles(uid), 403, "account_unavailable", "no_active_roles"),
    (lambda uid, f, e: _deny_staff(uid), 403, "social_login_not_allowed", "social_login_not_allowed"),
    (_remove_identity, 403, "account_unavailable", "oauth_identity_unknown"),
    (_reassign_identity, 403, "account_unavailable", "oauth_identity_unknown"),
]


@pytest.mark.parametrize("change,status,external,audit", _COMPLETE_DENIALS)
def test_complete_domain_denial_burns_ticket(
    client, fake, test_email, foreign_test_email, change, status, external, audit,
):
    user_id = _link(test_email, fake)
    ticket = _login_ticket(client, fake)          # на callback всё было разрешено
    change(user_id, fake, foreign_test_email)     # изменение между callback и complete
    mark = _auth_mark()

    r = _complete(client, ticket)

    assert r.status_code == status and r.json()["code"] == external
    assert _ticket_row(ticket).consumed_at is not None      # сожжён навсегда
    assert _sessions(user_id) == 0
    assert _failed_codes_since(mark) == [audit]
    assert _failed_methods_since(mark) == ["yandex"]   # провайдер списанного ticket
    again = _complete(client, ticket)
    assert again.status_code == 400 and again.json()["code"] == "oauth_ticket_invalid"


def test_complete_technical_failure_keeps_ticket_usable(client, fake, test_email, monkeypatch):
    user_id = _link(test_email, fake)
    ticket = _login_ticket(client, fake)

    def _boom(*args, **kwargs):
        raise RuntimeError("session insert failed")

    monkeypatch.setattr(oauth_storage, "create_session_in_tx", _boom)
    with pytest.raises(RuntimeError):
        oauth_service.complete_login(ticket)
    assert _ticket_row(ticket).consumed_at is None            # rollback
    assert _sessions(user_id) == 0

    monkeypatch.undo()
    assert _complete(client, ticket).status_code == 200      # повтор успешен
    assert _complete(client, ticket).status_code == 400      # и только один раз
    assert _sessions(user_id) == 1


def test_complete_survives_audit_storage_failure(client, fake, test_email, monkeypatch):
    user_id = _link(test_email, fake)
    ticket = _login_ticket(client, fake)

    def _no_audit_db():
        raise RuntimeError("audit db down")

    monkeypatch.setattr(audit_service, "SessionLocal", _no_audit_db)
    r = _complete(client, ticket)
    assert r.status_code == 200
    assert _sessions(user_id) == 1


def test_secrets_never_logged_or_stored_in_audit(client, fake, test_email, caplog, capsys):
    _link(test_email, fake)
    caplog.set_level(logging.DEBUG)
    mark = _auth_mark()

    state, _ = _start(client)
    verifier = decrypt_text(_request_row(state).code_verifier_enc)
    code = fake.issue_code(state)
    ticket = _fragment(_callback(client, {"state": state, "code": code}, cookie=state))["ticket"]
    token = _complete(client, ticket).json()["session_token"]
    # плюс отказ: повтор ticket
    _complete(client, ticket)

    captured = capsys.readouterr()
    # Логгер httpx — это клиент теста (роль браузера), не сервер: он пишет URL
    # своих запросов. Проверяем всё, что пишет приложение.
    server_log = "\n".join(
        r.getMessage() for r in caplog.records if not r.name.startswith("httpx")
    )
    haystack = server_log + captured.out + captured.err
    audit_text = " ".join(
        f"{r.event}|{r.user_email}|{r.failure_reason}|{r.session_id}|{r.user_agent}"
        for r in _auth_rows_since(mark)
    )
    for secret in (state, verifier, code, ticket, token):
        assert secret not in haystack
        assert secret not in audit_text


# ── get_current_user hardening ───────────────────────────────────────────────

def _password_login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": "SecurePass42!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_active_session_still_works(client, test_email):
    create_test_user(test_email)
    headers = _password_login(client, test_email)
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_session_of_disabled_user_is_rejected_and_revoked(client, test_email):
    user_id = int(create_test_user(test_email)["id"])
    headers = _password_login(client, test_email)
    # Обход штатной деактивации (она отзывает сессии сама): моделирует сессию,
    # созданную в окне гонки с деактивацией.
    _set(lambda db: db.query(User).filter_by(id=user_id), is_active=False)

    assert client.get("/api/auth/me", headers=headers).status_code == 401
    with SessionLocal() as db:
        assert db.query(UserSession).filter_by(user_id=user_id).one().is_revoked is True

    _set(lambda db: db.query(User).filter_by(id=user_id), is_active=True)
    assert client.get("/api/auth/me", headers=headers).status_code == 401   # не оживает


# ── create_session_in_tx ─────────────────────────────────────────────────────

def test_create_session_in_tx_does_not_commit(client, test_email):
    user_id = int(create_test_user(test_email)["id"])
    with SessionLocal() as db:
        token, _ = auth_storage.create_session_in_tx(db, user_id)
        db.rollback()
    assert token and _sessions(user_id) == 0


def test_create_session_wrapper_still_commits(client, test_email):
    user_id = int(create_test_user(test_email)["id"])
    token, expires_at = auth_storage.create_session(str(user_id))
    assert _sessions(user_id) == 1 and expires_at > datetime.now(timezone.utc)
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {token}"},
    ).status_code == 200
