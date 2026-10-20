"""
Stage Social Auth VK-1A — unit-тесты VKProvider без сети (httpx.MockTransport).

Проверяется точная форма запросов к VK ID (authorize / token / user_info) по
официальной документации и vkid-web-sdk, отсутствие client_secret, обработка
device_id, разбор callback (отдельные параметры и `payload`), валидация
профиля, классификация ошибок и то, что ни code, ни verifier, ни device_id, ни
токены, ни профиль не попадают в логи и исключения.
"""
import json
import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app.oauth.providers.base import (
    CANCELLED_ERROR, ProviderError, ProviderRejected, ProviderUnavailable,
)
from app.oauth.providers.vk import (
    AUTHORIZE_URL, MAX_RESPONSE_BYTES, PROVIDER_ERROR, SCOPE, TOKEN_URL, USERINFO_URL,
    VKProvider,
)
from app.oauth.security import code_challenge_s256, generate_code_verifier, generate_state

CLIENT_ID = "54000001"
REDIRECT_URI = "http://localhost/api/auth/oauth/vk/callback"
CODE = "vk2.a.SYNTH_CODE_7f3a91"
STATE = generate_state()
DEVICE_ID = "SYNTH_DEVICE_ID_P7UVuD_G7mw"
VERIFIER = generate_code_verifier()
ACCESS_TOKEN = "vk2.a.SYNTH_ACCESS_TOKEN_AgAAAA"
REFRESH_TOKEN = "vk2.a.SYNTH_REFRESH_TOKEN_abc"
ID_TOKEN = "SYNTH_ID_TOKEN_eyJhbGciOi"
DESCRIPTION = "SYNTH_ERROR_DESCRIPTION_do_not_log"
BODY_MARKER = "SYNTH_BODY_MARKER_9c1e"
USER_ID = "1234567890"
EMAIL = "synthetic.user@vk.ru"
PHONE = "79990001122"


# ── фейковый VK ID ───────────────────────────────────────────────────────────

def token_payload(**overrides):
    data = {
        "access_token": ACCESS_TOKEN, "refresh_token": REFRESH_TOKEN,
        "id_token": ID_TOKEN, "token_type": "Bearer", "expires_in": 3600,
        "user_id": int(USER_ID), "state": STATE, "scope": "vkid.personal_info email",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not _MISSING}


def user(**overrides):
    data = {
        "user_id": USER_ID, "first_name": "Синтетик", "last_name": "Вконтактов",
        "phone": PHONE, "avatar": "https://pp.userapi.example/synthetic-avatar.jpg",
        "email": EMAIL, "sex": 2, "verified": True, "birthday": "31.12.1999",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not _MISSING}


_MISSING = object()


class FakeVK:
    """Обработчик MockTransport: отвечает на token и user_info, пишет запросы."""

    def __init__(self, *, token=None, userinfo=None):
        self.requests: list[httpx.Request] = []
        self.token = token or self.json(200, token_payload())
        self.userinfo = userinfo or self.json(200, {"user": user()})

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


def _form(request: httpx.Request) -> dict:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


def provider(fake: FakeVK) -> VKProvider:
    return VKProvider(CLIENT_ID, transport=httpx.MockTransport(fake))


EXTRA = {"device_id": DEVICE_ID, "state": STATE}


def resolve(fake: FakeVK, extra=None):
    return provider(fake).resolve_identity(
        code=CODE, code_verifier=VERIFIER, redirect_uri=REDIRECT_URI,
        extra=EXTRA if extra is None else extra,
    )


def raw(status, body: bytes, headers=None):
    return lambda request: httpx.Response(status, content=body, headers=headers)


def raises(exc_type):
    def _handler(request):
        raise exc_type("synthetic transport failure", request=request)
    return _handler


_SECRETS = (CODE, VERIFIER, DEVICE_ID, ACCESS_TOKEN, REFRESH_TOKEN, ID_TOKEN,
            DESCRIPTION, BODY_MARKER, EMAIL, USER_ID, PHONE, STATE)


def assert_sanitized(exc: ProviderError):
    """Исключение без цепочки (request httpx с телом формы) и без секретов."""
    assert exc.__cause__ is None and exc.__context__ is None
    text = f"{exc!s} {exc!r}"
    for secret in _SECRETS:
        assert secret not in text


# ── конструктор ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", None, 54000001])
def test_client_id_required(bad):
    with pytest.raises(ValueError):
        VKProvider(bad)


def test_provider_name_is_db_allowed():
    from app.db.models.oauth import OAUTH_PROVIDERS
    assert VKProvider(CLIENT_ID).name == "vk" and "vk" in OAUTH_PROVIDERS


# ── authorize URL ────────────────────────────────────────────────────────────

def test_authorize_url_exact_params():
    challenge = code_challenge_s256(VERIFIER)
    url = VKProvider(CLIENT_ID).build_authorize_url(
        state=STATE, code_challenge=challenge, redirect_uri=REDIRECT_URI,
    )
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == AUTHORIZE_URL
    assert AUTHORIZE_URL == "https://id.vk.ru/authorize"
    assert parts.fragment == ""
    params = parse_qs(parts.query, keep_blank_values=True)
    assert params == {
        "response_type": ["code"],
        "client_id": [CLIENT_ID],
        "redirect_uri": [REDIRECT_URI],
        "scope": [SCOPE],
        "state": [STATE],
        "code_challenge": [challenge],
        "code_challenge_method": ["S256"],
    }
    assert SCOPE.split() == ["vkid.personal_info", "email"]     # без phone
    assert len(STATE) >= 32                                     # требование VK ID


def test_authorize_url_has_no_secret_or_verifier():
    url = VKProvider(CLIENT_ID).build_authorize_url(
        state=STATE, code_challenge=code_challenge_s256(VERIFIER), redirect_uri=REDIRECT_URI,
    )
    for forbidden in ("client_secret", "service_token", "code_verifier", VERIFIER,
                      "phone", "code_challenge_method=plain", "device_id"):
        assert forbidden not in url


# ── callback ─────────────────────────────────────────────────────────────────

def test_callback_success_carries_device_id_in_extra():
    cb = VKProvider(CLIENT_ID).parse_callback({
        "code": CODE, "state": STATE, "device_id": DEVICE_ID,
        "type": "code_v2", "expires_in": "600", "ext_id": "ignored",
    })
    assert (cb.state, cb.code, cb.error) == (STATE, CODE, None)
    assert dict(cb.extra) == {"device_id": DEVICE_ID, "state": STATE}


def test_callback_payload_json_is_accepted():
    """Документация VK описывает и возврат одним параметром `payload`."""
    cb = VKProvider(CLIENT_ID).parse_callback({"payload": json.dumps({
        "code": CODE, "state": STATE, "device_id": DEVICE_ID, "type": "code_v2",
    })})
    assert (cb.state, cb.code, cb.error) == (STATE, CODE, None)
    assert dict(cb.extra) == {"device_id": DEVICE_ID, "state": STATE}


def test_callback_query_params_take_priority_over_payload():
    cb = VKProvider(CLIENT_ID).parse_callback({
        "code": CODE, "state": STATE, "device_id": DEVICE_ID,
        "payload": json.dumps({"code": "other", "state": "x" * 43, "device_id": "other"}),
    })
    assert (cb.code, cb.state) == (CODE, STATE)
    assert cb.extra["device_id"] == DEVICE_ID


@pytest.mark.parametrize("payload", [
    "not json", "[1,2]", '"str"', "null", "", "{" * 9000, json.dumps({"code": 5}),
])
def test_callback_malformed_payload_never_raises(payload):
    cb = VKProvider(CLIENT_ID).parse_callback({"state": STATE, "payload": payload})
    assert cb.code is None and dict(cb.extra) == {}


@pytest.mark.parametrize("device_id", [None, "", "has space", "line\nbreak", "x" * 513])
def test_callback_without_valid_device_id_has_no_code(device_id):
    query = {"code": CODE, "state": STATE}
    if device_id is not None:
        query["device_id"] = device_id
    cb = VKProvider(CLIENT_ID).parse_callback(query)
    assert cb.state == STATE          # state остаётся — ядро сверит и спишет его
    assert cb.code is None and dict(cb.extra) == {}


def test_callback_access_denied_is_cancellation():
    cb = VKProvider(CLIENT_ID).parse_callback({
        "state": STATE, "error": "access_denied", "error_description": DESCRIPTION,
    })
    assert cb.error == CANCELLED_ERROR and cb.code is None
    assert DESCRIPTION not in repr(cb)


@pytest.mark.parametrize("error", ["server_error", "invalid_request", "ANYTHING", "x" * 500])
def test_callback_other_errors_normalized(error):
    cb = VKProvider(CLIENT_ID).parse_callback({"state": STATE, "error": error})
    assert cb.error == PROVIDER_ERROR
    assert error not in repr(cb) or error == PROVIDER_ERROR


def test_callback_error_inside_payload():
    cb = VKProvider(CLIENT_ID).parse_callback({"payload": json.dumps({
        "state": STATE, "error": "access_denied",
    })})
    assert cb.error == CANCELLED_ERROR and cb.state == STATE


@pytest.mark.parametrize("value", ["", "has space", "ctrl\x00", "кириллица", "x" * 5000])
def test_callback_malformed_values_become_none(value):
    cb = VKProvider(CLIENT_ID).parse_callback({
        "code": value, "state": value, "device_id": DEVICE_ID,
    })
    assert cb.code is None and cb.state is None and dict(cb.extra) == {}


def test_callback_empty_error_is_no_error():
    cb = VKProvider(CLIENT_ID).parse_callback({
        "code": CODE, "state": STATE, "device_id": DEVICE_ID, "error": "",
    })
    assert cb.error is None and cb.code == CODE


# ── token exchange ───────────────────────────────────────────────────────────

def test_success_identity_and_request_shapes():
    fake = FakeVK()
    identity = resolve(fake)
    assert identity.provider == "vk"
    assert identity.subject == USER_ID
    assert identity.email == EMAIL
    assert identity.suggested_name == "Синтетик Вконтактов"

    token_req, = fake.calls(TOKEN_URL)
    assert token_req.method == "POST"
    assert token_req.url.query == b""                       # ничего секретного в URL
    assert token_req.headers["content-type"] == "application/x-www-form-urlencoded"
    assert _form(token_req) == {
        "grant_type": "authorization_code",
        "code": CODE,
        "code_verifier": VERIFIER,
        "client_id": CLIENT_ID,
        "device_id": DEVICE_ID,
        "redirect_uri": REDIRECT_URI,
        "state": STATE,
    }

    info_req, = fake.calls(USERINFO_URL)
    assert info_req.method == "POST"
    assert info_req.url.query == b""                        # токен не в query
    assert _form(info_req) == {"client_id": CLIENT_ID, "access_token": ACCESS_TOKEN}
    assert "authorization" not in info_req.headers


def test_no_client_secret_or_service_token_anywhere():
    fake = FakeVK()
    resolve(fake)
    for request in fake.requests:
        blob = str(request.url) + request.content.decode() + repr(dict(request.headers))
        for forbidden in ("client_secret", "service_token", "secret"):
            assert forbidden not in blob.lower()


@pytest.mark.parametrize("extra", [
    {}, {"device_id": DEVICE_ID}, {"state": STATE},
    {"device_id": "", "state": STATE}, {"device_id": "has space", "state": STATE},
])
def test_missing_device_id_or_state_rejected_without_network(extra):
    fake = FakeVK()
    with pytest.raises(ProviderRejected) as ei:
        resolve(fake, extra=extra)
    assert_sanitized(ei.value)
    assert fake.requests == []


@pytest.mark.parametrize("status,error", [
    (400, "invalid_grant"), (400, "invalid_request"), (401, "invalid_client"),
    (403, "something_new"),
])
def test_token_4xx_rejected(status, error):
    fake = FakeVK(token=FakeVK.json(status, {"error": error, "error_description": DESCRIPTION}))
    with pytest.raises(ProviderRejected) as ei:
        resolve(fake)
    assert_sanitized(ei.value)
    assert fake.calls(USERINFO_URL) == []


@pytest.mark.parametrize("error", ["invalid_grant", "slow_down", "weird_new_code", 42, None])
def test_token_error_in_200_body_rejected(error):
    """VK может вернуть ошибку телом 2xx (так её проверяет и официальный SDK)."""
    fake = FakeVK(token=FakeVK.json(200, {"error": error, "error_description": DESCRIPTION}))
    with pytest.raises(ProviderRejected) as ei:
        resolve(fake)
    assert_sanitized(ei.value)
    assert fake.calls(USERINFO_URL) == []


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_token_429_and_5xx_unavailable(status):
    fake = FakeVK(token=FakeVK.json(status, {"error": "x"}))
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(fake)
    assert_sanitized(ei.value)
    assert fake.calls(USERINFO_URL) == []


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_token_redirect_not_followed(status):
    fake = FakeVK(token=raw(status, b"", {"Location": "https://evil.example/steal"}))
    with pytest.raises(ProviderUnavailable):
        resolve(fake)
    assert [str(r.url) for r in fake.requests] == [TOKEN_URL]


@pytest.mark.parametrize("exc_type", [
    httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
    httpx.PoolTimeout, httpx.ReadError, httpx.RemoteProtocolError,
])
def test_token_transport_errors_unavailable(exc_type):
    fake = FakeVK(token=raises(exc_type))
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(fake)
    assert_sanitized(ei.value)


@pytest.mark.parametrize("body", [
    b"not json " + BODY_MARKER.encode(), b"[1, 2]", b'"str"', b"", b"null",
    b"[" * 5000 + b"]" * 5000,
])
def test_token_malformed_body_unavailable(body):
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(FakeVK(token=raw(200, body)))
    assert_sanitized(ei.value)


def test_token_oversized_body_unavailable():
    big = json.dumps(token_payload(pad="x" * MAX_RESPONSE_BYTES))
    with pytest.raises(ProviderUnavailable):
        resolve(FakeVK(token=raw(200, big.encode())))


@pytest.mark.parametrize("token", [
    _MISSING, "", None, 12345, "has space", "line\nbreak", "x" * 8193,
])
def test_token_missing_or_invalid_access_token_rejected(token):
    fake = FakeVK(token=FakeVK.json(200, token_payload(access_token=token)))
    with pytest.raises(ProviderRejected):
        resolve(fake)
    assert fake.calls(USERINFO_URL) == []


def test_token_state_mismatch_rejected():
    fake = FakeVK(token=FakeVK.json(200, token_payload(state="another-state-value")))
    with pytest.raises(ProviderRejected):
        resolve(fake)
    assert fake.calls(USERINFO_URL) == []


@pytest.mark.parametrize("state", [_MISSING, "", None])
def test_token_without_state_echo_is_accepted(state):
    assert resolve(FakeVK(token=FakeVK.json(200, token_payload(state=state)))).subject == USER_ID


# ── user_info ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", [401, 403, 400])
def test_userinfo_4xx_rejected(status):
    fake = FakeVK(userinfo=FakeVK.json(status, {"error": BODY_MARKER}))
    with pytest.raises(ProviderRejected) as ei:
        resolve(fake)
    assert_sanitized(ei.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_userinfo_429_and_5xx_unavailable(status):
    with pytest.raises(ProviderUnavailable):
        resolve(FakeVK(userinfo=FakeVK.json(status, {})))


def test_userinfo_transport_error_unavailable():
    with pytest.raises(ProviderUnavailable) as ei:
        resolve(FakeVK(userinfo=raises(httpx.ReadTimeout)))
    assert_sanitized(ei.value)


@pytest.mark.parametrize("body", [b"<html>" + BODY_MARKER.encode(), b"[]", b"", b"7"])
def test_userinfo_malformed_unavailable(body):
    with pytest.raises(ProviderUnavailable):
        resolve(FakeVK(userinfo=raw(200, body)))


def test_userinfo_oversized_unavailable():
    big = json.dumps({"user": user(pad="x" * MAX_RESPONSE_BYTES)})
    with pytest.raises(ProviderUnavailable):
        resolve(FakeVK(userinfo=raw(200, big.encode())))


@pytest.mark.parametrize("payload", [
    {}, {"user": None}, {"user": []}, {"user": "x"}, {"response": {"user": user()}},
    {"error": "invalid_token"}, {"error": "access_denied", "user": user()},
])
def test_userinfo_without_user_object_or_with_error_rejected(payload):
    with pytest.raises(ProviderRejected) as ei:
        resolve(FakeVK(userinfo=FakeVK.json(200, payload)))
    assert_sanitized(ei.value)


# ── субъект ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (USER_ID, USER_ID), (int(USER_ID), USER_ID), ("id-with-letters", "id-with-letters"),
])
def test_subject_is_user_id_as_string(value, expected):
    fake = FakeVK(
        token=FakeVK.json(200, token_payload(user_id=_MISSING)),
        userinfo=FakeVK.json(200, {"user": user(user_id=value)}),
    )
    assert resolve(fake).subject == expected


@pytest.mark.parametrize("value", [
    _MISSING, None, "", "   ", True, 1.5, ["1"], {"id": 1}, "x" * 256, "ctrl\x00id",
])
def test_invalid_user_id_rejected(value):
    fake = FakeVK(
        token=FakeVK.json(200, token_payload(user_id=_MISSING)),
        userinfo=FakeVK.json(200, {"user": user(user_id=value)}),
    )
    with pytest.raises(ProviderRejected):
        resolve(fake)


def test_user_id_mismatch_between_token_and_profile_rejected():
    fake = FakeVK(userinfo=FakeVK.json(200, {"user": user(user_id="9999999999")}))
    with pytest.raises(ProviderRejected):
        resolve(fake)


def test_subject_stable_regardless_of_other_fields():
    first = resolve(FakeVK()).subject
    changed = resolve(FakeVK(userinfo=FakeVK.json(200, {"user": user(
        email="other@vk.ru", first_name="Другое", last_name="Имя", phone="70000000000",
    )}))).subject
    assert first == changed == USER_ID


# ── email и имя ──────────────────────────────────────────────────────────────

def _identity_with(**overrides):
    return resolve(FakeVK(userinfo=FakeVK.json(200, {"user": user(**overrides)})))


@pytest.mark.parametrize("raw_email,expected", [
    (EMAIL, EMAIL), ("  Synthetic.User@VK.RU ", "synthetic.user@vk.ru"),
])
def test_email_present_is_normalized(raw_email, expected):
    assert _identity_with(email=raw_email).email == expected


@pytest.mark.parametrize("bad", [
    _MISSING, None, "", "   ", "no-at-sign", "a@@vk.ru", "user@", 42, ["x@vk.ru"],
    "iv***@vk.ru"[:0] + "user\x00@vk.ru", "a" * 250 + "@vk.ru",
])
def test_email_absent_or_malformed_is_none_not_failure(bad):
    """VK может не отдать email: вход по привязанной identity от него не зависит."""
    identity = _identity_with(email=bad)
    assert identity.email is None and identity.subject == USER_ID


@pytest.mark.parametrize("overrides,expected", [
    ({}, "Синтетик Вконтактов"),
    ({"first_name": "  Иван ", "last_name": " Петров  "}, "Иван Петров"),
    ({"last_name": _MISSING}, "Синтетик"),
    ({"first_name": _MISSING}, "Вконтактов"),
    ({"first_name": "", "last_name": "  "}, None),
    ({"first_name": _MISSING, "last_name": _MISSING}, None),
    ({"first_name": "Ив\x00ан", "last_name": _MISSING}, None),
    ({"first_name": 42, "last_name": ["x"]}, None),
    ({"first_name": "я", "last_name": _MISSING}, None),          # короче 2 символов
])
def test_suggested_name_from_first_and_last_name(overrides, expected):
    identity = _identity_with(**overrides)
    assert identity.suggested_name == expected
    assert identity.subject == USER_ID


def test_only_id_email_and_name_leave_the_adapter():
    """Телефон, аватар, пол, дата рождения, verified и токены не попадают в identity."""
    identity = resolve(FakeVK())
    assert set(vars(identity)) == {"provider", "subject", "email", "suggested_name"}
    text = repr(identity)
    for value in (PHONE, "synthetic-avatar", "31.12.1999", ACCESS_TOKEN, REFRESH_TOKEN,
                  ID_TOKEN, DEVICE_ID):
        assert value not in text


# ── логи ─────────────────────────────────────────────────────────────────────

def _flows():
    yield FakeVK()
    yield FakeVK(token=FakeVK.json(
        400, {"error": "invalid_grant", "error_description": DESCRIPTION}))
    yield FakeVK(token=FakeVK.json(200, {"error": DESCRIPTION}))
    yield FakeVK(token=raw(200, ("broken " + BODY_MARKER).encode()))
    yield FakeVK(userinfo=FakeVK.json(401, {"error": BODY_MARKER}))
    yield FakeVK(userinfo=FakeVK.json(200, {"user": user(user_id="9999999999")}))
    yield FakeVK(userinfo=raises(httpx.ReadTimeout))
    yield FakeVK(token=raises(httpx.ConnectError))


def test_no_secrets_in_logs_even_at_debug(caplog):
    caplog.set_level(logging.DEBUG)
    for name in ("httpx", "httpcore", "app.oauth.providers.vk"):
        caplog.set_level(logging.DEBUG, logger=name)
    for fake in _flows():
        try:
            resolve(fake)
        except ProviderError:
            pass
    assert caplog.records, "ожидались хотя бы предупреждения адаптера"
    text = caplog.text + "\n".join(r.getMessage() for r in caplog.records)
    for secret in _SECRETS + ("9999999999",):
        assert secret not in text, secret
    for record in caplog.records:
        assert record.exc_info is None


def test_failure_warning_has_only_safe_fields(caplog):
    caplog.set_level(logging.WARNING, logger="app.oauth.providers.vk")
    with pytest.raises(ProviderRejected):
        resolve(FakeVK(token=FakeVK.json(
            400, {"error": "invalid_grant", "error_description": DESCRIPTION})))
    record, = [r for r in caplog.records if r.name == "app.oauth.providers.vk"]
    assert record.getMessage() == (
        "VK ID token failed: rejected (status=400, detail=invalid_grant)"
    )


def test_unknown_error_code_logged_as_other(caplog):
    caplog.set_level(logging.WARNING, logger="app.oauth.providers.vk")
    with pytest.raises(ProviderRejected):
        resolve(FakeVK(token=FakeVK.json(400, {"error": BODY_MARKER})))
    assert "detail=other" in caplog.text and BODY_MARKER not in caplog.text
