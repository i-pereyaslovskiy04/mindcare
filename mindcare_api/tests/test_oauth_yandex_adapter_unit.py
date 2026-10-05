"""
Stage Social Auth 3A — unit-тесты YandexProvider без сети (httpx.MockTransport).

Проверяется точная форма запросов к Яндекс ID (authorize / token / user-info),
отсутствие client_secret и токена в URL, валидация профиля (`id`, `client_id`),
классификация ошибок (ProviderUnavailable / ProviderRejected) и то, что ни
code, ни verifier, ни токены, ни тела ответов не попадают в логи и исключения.
"""
import json
import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.oauth.providers.base import (
    CANCELLED_ERROR, ProviderError, ProviderRejected, ProviderUnavailable,
)
from app.oauth.providers.yandex import (
    AUTHORIZE_URL, MAX_RESPONSE_BYTES, PROVIDER_ERROR, SCOPE, TOKEN_URL, USERINFO_URL,
    YandexProvider,
)
from app.oauth.security import code_challenge_s256, generate_code_verifier

CLIENT_ID = "synthetic0client0id0000000000001"
REDIRECT_URI = "http://localhost:8000/api/auth/oauth/yandex/callback"
CODE = "SYNTH_CODE_7f3a91"
VERIFIER = generate_code_verifier()
ACCESS_TOKEN = "SYNTH_ACCESS_TOKEN_y0_AgAAAA"
REFRESH_TOKEN = "SYNTH_REFRESH_TOKEN_1:abc"
DESCRIPTION = "SYNTH_ERROR_DESCRIPTION_do_not_log"
BODY_MARKER = "SYNTH_BODY_MARKER_9c1e"


# ── фейковый Яндекс ──────────────────────────────────────────────────────────

class FakeYandex:
    """Обработчик MockTransport: отвечает на token и user-info, пишет запросы."""

    def __init__(self, *, token=None, userinfo=None):
        self.requests: list[httpx.Request] = []
        self.token = token or self.json(200, {
            "token_type": "bearer", "access_token": ACCESS_TOKEN,
            "expires_in": 31536000, "refresh_token": REFRESH_TOKEN,
            "scope": "login:email",
        })
        self.userinfo = userinfo or self.json(200, profile())

    @staticmethod
    def json(status, payload, headers=None):
        return lambda request: httpx.Response(status, json=payload, headers=headers)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = _base(request)
        if url == TOKEN_URL:
            return self.token(request)
        if url == USERINFO_URL:
            return self.userinfo(request)
        return httpx.Response(404)

    def calls(self, url):
        return [r for r in self.requests if _base(r) == url]


def _base(request: httpx.Request) -> str:
    return f"{request.url.scheme}://{request.url.host}{request.url.path}"


def profile(**overrides):
    data = {
        "id": "1000034426",
        "login": "synthetic.login",
        "client_id": CLIENT_ID,
        "psuid": "1.AAceCw.synthetic-psuid.qPWSRC5v2t2IaksPJgnge",
        "default_email": "synthetic@yandex.ru",
        "emails": ["synthetic@yandex.ru"],
        "first_name": "Синтетический",
        "last_name": "Пользователь",
        "display_name": "synthetic",
        "real_name": "Синтетический Пользователь",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not _MISSING}


_MISSING = object()


def provider(fake: FakeYandex) -> YandexProvider:
    return YandexProvider(CLIENT_ID, transport=httpx.MockTransport(fake))


def resolve(fake: FakeYandex):
    return provider(fake).resolve_identity(
        code=CODE, code_verifier=VERIFIER, redirect_uri=REDIRECT_URI, extra={},
    )


def raw(status, body: bytes, headers=None):
    return lambda request: httpx.Response(status, content=body, headers=headers)


def raises(exc_type):
    def _handler(request):
        raise exc_type("synthetic transport failure", request=request)
    return _handler


def assert_sanitized(exc: ProviderError):
    """Исключение без цепочки (request httpx с заголовками) и без секретов."""
    assert exc.__cause__ is None and exc.__context__ is None
    text = f"{exc!s} {exc!r}"
    for secret in (CODE, VERIFIER, ACCESS_TOKEN, REFRESH_TOKEN, DESCRIPTION, BODY_MARKER):
        assert secret not in text


# ── конструктор ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", None, 123])
def test_client_id_required(bad):
    with pytest.raises(ValueError):
        YandexProvider(bad)


def test_provider_name_is_db_allowed():
    assert YandexProvider(CLIENT_ID).name == "yandex"


# ── authorize URL ────────────────────────────────────────────────────────────

def test_authorize_url_exact_params():
    verifier = generate_code_verifier()
    challenge = code_challenge_s256(verifier)
    url = YandexProvider(CLIENT_ID).build_authorize_url(
        state="SYNTH_state_abc", code_challenge=challenge, redirect_uri=REDIRECT_URI,
    )
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == AUTHORIZE_URL
    assert parts.fragment == ""
    params = parse_qs(parts.query, keep_blank_values=True)
    assert params == {
        "response_type": ["code"],
        "client_id": [CLIENT_ID],
        "redirect_uri": [REDIRECT_URI],
        "scope": [SCOPE],
        "state": ["SYNTH_state_abc"],
        "code_challenge": [challenge],
        "code_challenge_method": ["S256"],
    }
    assert SCOPE == "login:email login:info"
    assert params["scope"][0].split() == ["login:email", "login:info"]


def test_authorize_url_has_no_secret_or_extra_params():
    url = YandexProvider(CLIENT_ID).build_authorize_url(
        state="s", code_challenge="c", redirect_uri=REDIRECT_URI,
    )
    for forbidden in ("client_secret", "device_id", "device_name", "login_hint",
                      "force_confirm", "optional_scope", "code_challenge_method=plain"):
        assert forbidden not in url


# ── callback ─────────────────────────────────────────────────────────────────

def test_callback_success():
    cb = YandexProvider(CLIENT_ID).parse_callback({"state": "st_1", "code": "cd_1"})
    assert (cb.state, cb.code, cb.error) == ("st_1", "cd_1", None)
    assert dict(cb.extra) == {}


def test_callback_access_denied_is_cancellation():
    cb = YandexProvider(CLIENT_ID).parse_callback({
        "state": "st_1", "error": "access_denied", "error_description": DESCRIPTION,
    })
    assert cb.error == CANCELLED_ERROR == "access_denied"
    assert DESCRIPTION not in repr(cb)


@pytest.mark.parametrize("error", [
    "unauthorized_client", "invalid_request", "server_error", "x" * 5000, "ACCESS_DENIED",
])
def test_callback_other_errors_normalized(error):
    cb = YandexProvider(CLIENT_ID).parse_callback({
        "state": "st_1", "error": error, "error_description": DESCRIPTION,
    })
    assert cb.error == PROVIDER_ERROR
    assert DESCRIPTION not in repr(cb)


def test_callback_missing_state():
    cb = YandexProvider(CLIENT_ID).parse_callback({"code": "cd_1"})
    assert cb.state is None and cb.code == "cd_1"


@pytest.mark.parametrize("value", [
    "", "a b", "tab\tx", "nl\nx", "кириллица", "x" * 1025, "\x00", 123, None,
])
def test_callback_malformed_values_become_none(value):
    cb = YandexProvider(CLIENT_ID).parse_callback({"state": value, "code": value})
    assert cb.state is None and cb.code is None


def test_callback_max_length_accepted():
    cb = YandexProvider(CLIENT_ID).parse_callback({"state": "s" * 1024, "code": "c" * 1024})
    assert cb.state == "s" * 1024 and cb.code == "c" * 1024


def test_callback_empty_error_is_no_error():
    cb = YandexProvider(CLIENT_ID).parse_callback({"state": "s", "code": "c", "error": ""})
    assert cb.error is None


# ── token exchange ───────────────────────────────────────────────────────────

def test_success_identity_and_request_shapes():
    fake = FakeYandex()
    identity = resolve(fake)
    assert identity.provider == "yandex"
    assert identity.subject == "1000034426"
    assert identity.email == "synthetic@yandex.ru"
    assert identity.suggested_name == "Синтетический Пользователь"

    token_req, = fake.calls(TOKEN_URL)
    assert token_req.method == "POST"
    assert token_req.url.query == b""                       # code/verifier не в URL
    assert token_req.headers["content-type"] == "application/x-www-form-urlencoded"
    assert "authorization" not in token_req.headers         # без Basic
    form = parse_qs(token_req.content.decode(), keep_blank_values=True)
    assert form == {
        "grant_type": ["authorization_code"],
        "code": [CODE],
        "code_verifier": [VERIFIER],
        "client_id": [CLIENT_ID],
    }
    assert CODE not in str(token_req.url) and VERIFIER not in str(token_req.url)

    info_req, = fake.calls(USERINFO_URL)
    assert info_req.method == "GET"
    assert info_req.url.query == b""                        # без ?oauth_token / format
    assert info_req.headers["authorization"] == f"OAuth {ACCESS_TOKEN}"
    assert ACCESS_TOKEN not in str(info_req.url)
    assert info_req.headers["user-agent"] == "MindCare-OAuth/1"
    assert len(fake.requests) == 2                          # без повторов


@pytest.mark.parametrize("status,error", [
    (400, "invalid_grant"), (400, "invalid_request"), (400, "unauthorized_client"),
    (401, "invalid_client"), (400, "invalid_scope"), (403, "something_new"),
])
def test_token_4xx_rejected(status, error):
    fake = FakeYandex(token=FakeYandex.json(
        status, {"error": error, "error_description": DESCRIPTION}))
    with pytest.raises(ProviderRejected) as ei:
        resolve(fake)
    assert_sanitized(ei.value)
    assert fake.calls(USERINFO_URL) == []


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_token_429_and_5xx_unavailable(status):
    fake = FakeYandex(token=FakeYandex.json(status, {"error": "x"}))
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(fake)
    assert_sanitized(ei.value)
    assert fake.calls(USERINFO_URL) == []


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_token_redirect_not_followed(status):
    fake = FakeYandex(token=raw(status, b"", {"Location": "https://evil.example/steal"}))
    with pytest.raises(ProviderUnavailable):
        resolve(fake)
    assert [str(r.url) for r in fake.requests] == [TOKEN_URL]


@pytest.mark.parametrize("exc_type", [
    httpx.ConnectError,       # DNS / отказ соединения / TLS-handshake
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
])
def test_token_transport_errors_unavailable(exc_type):
    fake = FakeYandex(token=raises(exc_type))
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(fake)
    assert_sanitized(ei.value)


def test_tls_failure_unavailable():
    def _tls(request):
        raise httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] synthetic", request=request)
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(FakeYandex(token=_tls))
    assert_sanitized(ei.value)


@pytest.mark.parametrize("body", [
    b"not json " + BODY_MARKER.encode(), b"[1, 2]", b'"str"', b"", b"null",
    b"[" * 5000 + b"]" * 5000,
])
def test_token_malformed_body_unavailable(body):
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(FakeYandex(token=raw(200, body)))
    assert_sanitized(ei.value)


def test_token_oversized_body_unavailable():
    big = json.dumps({"access_token": ACCESS_TOKEN, "pad": "x" * MAX_RESPONSE_BYTES})
    with pytest.raises(ProviderUnavailable):
        resolve(FakeYandex(token=raw(200, big.encode())))


@pytest.mark.parametrize("payload", [
    {"token_type": "bearer"},
    {"access_token": ""},
    {"access_token": None},
    {"access_token": 12345},
    {"access_token": "has space"},
    {"access_token": "line\nbreak"},
    {"access_token": "x" * 4097},
])
def test_token_missing_or_invalid_access_token_rejected(payload):
    fake = FakeYandex(token=FakeYandex.json(200, payload))
    with pytest.raises(ProviderRejected):
        resolve(fake)
    assert fake.calls(USERINFO_URL) == []


# ── user-info ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [401, 403, 400])
def test_userinfo_4xx_rejected(status):
    with pytest.raises(ProviderRejected) as ei:
        resolve(FakeYandex(userinfo=FakeYandex.json(status, {"error": BODY_MARKER})))
    assert_sanitized(ei.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_userinfo_429_and_5xx_unavailable(status):
    with pytest.raises(ProviderUnavailable):
        resolve(FakeYandex(userinfo=FakeYandex.json(status, {})))


def test_userinfo_transport_error_unavailable():
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(FakeYandex(userinfo=raises(httpx.ReadTimeout)))
    assert_sanitized(ei.value)


@pytest.mark.parametrize("body", [b"<xml/>", b"[]", b"{", b""])
def test_userinfo_malformed_unavailable(body):
    with pytest.raises(ProviderUnavailable):
        resolve(FakeYandex(userinfo=raw(200, body)))


def test_userinfo_oversized_unavailable():
    payload = profile(pad="x" * MAX_RESPONSE_BYTES)
    with pytest.raises(ProviderUnavailable):
        resolve(FakeYandex(userinfo=FakeYandex.json(200, payload)))


@pytest.mark.parametrize("client_id", [_MISSING, "other-client-id", "", None, 1, CLIENT_ID.upper()])
def test_userinfo_client_id_missing_or_mismatch_rejected(client_id):
    with pytest.raises(ProviderRejected):
        resolve(FakeYandex(userinfo=FakeYandex.json(200, profile(client_id=client_id))))


@pytest.mark.parametrize("subject", [
    "1000034426",
    "abc-DEF_123.x",               # не только цифры — допустимо
    "иван",                        # не ASCII — допустимо
    " 1000034426",                 # хранится как есть, без trim
    "y" * 255,
])
def test_valid_subject_preserved_verbatim(subject):
    identity = resolve(FakeYandex(userinfo=FakeYandex.json(200, profile(id=subject))))
    assert identity.subject == subject
    assert type(identity.subject) is str


@pytest.mark.parametrize("subject", [
    _MISSING, None, "", "   ", "y" * 256, "12\x0034", "12\n34", "12​34",
    1000034426, 10.5, True, ["1"], {"id": "1"},
])
def test_invalid_subject_rejected(subject):
    with pytest.raises(ProviderRejected):
        resolve(FakeYandex(userinfo=FakeYandex.json(200, profile(id=subject))))


def test_psuid_never_used_as_subject():
    with pytest.raises(ProviderRejected):
        resolve(FakeYandex(userinfo=FakeYandex.json(200, profile(id=_MISSING))))
    identity = resolve(FakeYandex())
    assert identity.subject == "1000034426"
    assert "psuid" not in identity.subject


def _identity_with(**overrides):
    return resolve(FakeYandex(userinfo=FakeYandex.json(200, profile(**overrides))))


@pytest.mark.parametrize("raw_email,expected", [
    ("synthetic@yandex.ru", "synthetic@yandex.ru"),
    ("  Synthetic.User@Yandex.RU ", "synthetic.user@yandex.ru"),
])
def test_default_email_extracted_and_normalized(raw_email, expected):
    assert _identity_with(default_email=raw_email).email == expected


@pytest.mark.parametrize("bad", [
    _MISSING, None, "", "   ", "no-at-sign", "a@@yandex.ru", "user@", 42,
    ["synthetic@yandex.ru"], {"email": "synthetic@yandex.ru"},
    "user\x00@yandex.ru", "a" * 250 + "@yandex.ru",
])
def test_missing_or_malformed_email_is_none_not_failure(bad):
    """Вход по привязанной identity от email не зависит — адаптер не падает,
    а регистрацию без email закрывает сервис (oauth_email_required)."""
    identity = _identity_with(default_email=bad)
    assert identity.email is None
    assert identity.subject == "1000034426"


def test_email_from_emails_list_is_not_used():
    """Только default_email: список `emails` не читается."""
    assert _identity_with(default_email=_MISSING).email is None


@pytest.mark.parametrize("overrides,expected", [
    ({}, "Синтетический Пользователь"),
    ({"first_name": "  Иван ", "last_name": " Петров  "}, "Иван Петров"),
    ({"last_name": _MISSING}, "Синтетический"),
    ({"first_name": _MISSING}, "Пользователь"),
    ({"first_name": _MISSING, "last_name": _MISSING}, "Синтетический Пользователь"),
    ({"first_name": "", "last_name": "  ", "real_name": "Реальное  Имя"}, "Реальное Имя"),
    ({"first_name": None, "last_name": None, "real_name": None}, "synthetic"),
    ({"first_name": _MISSING, "last_name": _MISSING, "real_name": _MISSING,
      "display_name": _MISSING}, "synthetic.login"),
    ({"first_name": "Ив\x00ан", "last_name": _MISSING, "real_name": _MISSING},
     "synthetic"),
    ({"first_name": 42, "last_name": ["x"], "real_name": "я"}, "synthetic"),
    ({"first_name": "x" * 300}, "Пользователь"),          # слишком длинная часть
    ({"first_name": "x" * 300, "last_name": _MISSING}, "Синтетический Пользователь"),
])
def test_suggested_name_fallback_chain(overrides, expected):
    assert _identity_with(**overrides).suggested_name == expected


def test_no_usable_name_is_none():
    identity = _identity_with(first_name=_MISSING, last_name=_MISSING,
                              real_name=_MISSING, display_name=_MISSING, login=_MISSING)
    assert identity.suggested_name is None
    assert identity.subject == "1000034426"            # вход от имени не зависит


def test_only_id_email_and_name_leave_the_adapter():
    """Пол, телефон, дата рождения, аватар и psuid не попадают в identity."""
    sensitive = {
        "sex": "female", "birthday": "1999-12-31",
        "default_phone": {"id": 1, "number": "+79990001122"},
        "default_avatar_id": "synthetic-avatar", "is_avatar_empty": False,
    }
    identity = _identity_with(**sensitive)
    assert set(vars(identity)) == {"provider", "subject", "email", "suggested_name"}
    text = repr(identity)
    for value in ("female", "1999-12-31", "+79990001122", "synthetic-avatar",
                  "synthetic-psuid", ACCESS_TOKEN, REFRESH_TOKEN):
        assert value not in text


# ── логи ─────────────────────────────────────────────────────────────────────

_SECRETS = (CODE, VERIFIER, ACCESS_TOKEN, REFRESH_TOKEN, DESCRIPTION, BODY_MARKER,
            "OAuth " + ACCESS_TOKEN, "synthetic@yandex.ru", "1000034426")


def _flows():
    yield FakeYandex()
    yield FakeYandex(token=FakeYandex.json(
        400, {"error": "invalid_grant", "error_description": DESCRIPTION}))
    yield FakeYandex(token=raw(200, ("broken " + BODY_MARKER).encode()))
    yield FakeYandex(userinfo=FakeYandex.json(401, {"error": BODY_MARKER}))
    yield FakeYandex(userinfo=FakeYandex.json(200, profile(client_id="other")))
    yield FakeYandex(userinfo=raises(httpx.ReadTimeout))
    yield FakeYandex(token=raises(httpx.ConnectError))


def test_no_secrets_in_logs_even_at_debug(caplog):
    caplog.set_level(logging.DEBUG)
    for name in ("httpx", "httpcore", "app.oauth.providers.yandex"):
        caplog.set_level(logging.DEBUG, logger=name)
    for fake in _flows():
        try:
            resolve(fake)
        except ProviderError:
            pass
    assert caplog.records, "ожидались хотя бы предупреждения адаптера"
    text = caplog.text + "\n".join(r.getMessage() for r in caplog.records)
    for secret in _SECRETS:
        assert secret not in text, secret
    for record in caplog.records:
        assert record.exc_info is None


def test_failure_warning_has_only_safe_fields(caplog):
    caplog.set_level(logging.WARNING, logger="app.oauth.providers.yandex")
    with pytest.raises(ProviderRejected):
        resolve(FakeYandex(token=FakeYandex.json(
            400, {"error": "invalid_grant", "error_description": DESCRIPTION})))
    messages = [r.getMessage() for r in caplog.records
                if r.name == "app.oauth.providers.yandex"]
    assert messages == [
        "Yandex ID token failed: rejected (status=400, detail=invalid_grant)"
    ]


def test_unknown_token_error_code_logged_as_other(caplog):
    caplog.set_level(logging.WARNING, logger="app.oauth.providers.yandex")
    with pytest.raises(ProviderRejected):
        resolve(FakeYandex(token=FakeYandex.json(400, {"error": BODY_MARKER})))
    assert "detail=other" in caplog.text and BODY_MARKER not in caplog.text
