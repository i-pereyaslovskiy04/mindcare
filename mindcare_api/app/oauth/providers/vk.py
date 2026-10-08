"""
Адаптер VK ID (Stage Social Auth VK-1A): OAuth 2.1 Authorization Code + PKCE S256.

Протокол сверен с официальной документацией VK ID «Авторизация без SDK для
Web» (id.vk.ru) и исходниками официального vkid-web-sdk (src/auth/auth.ts):

  authorize  GET  https://id.vk.ru/authorize
             response_type=code, client_id, redirect_uri, state,
             code_challenge, code_challenge_method=S256, scope (через пробел)
  callback   code, state, device_id, type=code_v2 — отдельными query-параметрами
             либо JSON-объектом в параметре `payload` (документация описывает
             оба вида; адаптер принимает оба)
  token      POST https://id.vk.ru/oauth2/auth (form)
             grant_type=authorization_code, code, code_verifier, client_id,
             device_id, redirect_uri, state
  user_info  POST https://id.vk.ru/oauth2/user_info (form)
             client_id, access_token → {"user": {user_id, first_name,
             last_name, email, phone, avatar, sex, verified, birthday}}

Публичный клиент: client_secret («защищённый ключ») и сервисный ключ НЕ
используются — ни документация, ни SDK не передают их в этом потоке.

Субъект — `user.user_id` (стабильный идентификатор пользователя VK) строкой.
Из профиля читаются ТОЛЬКО user_id, email и first_name + last_name. Телефон,
аватар, пол, дата рождения, признак verified, id_token и refresh_token не
читаются и нигде не сохраняются.

device_id приходит в callback и нужен только для обмена кода в том же запросе:
ядро передаёт его через ProviderCallback.extra → resolve_identity(extra=…). Он
не сохраняется в БД и не логируется.

Безопасность (как у адаптера Яндекса):
  * адреса VK — константы модуля, не настройки;
  * токены живут только внутри resolve_identity; access_token уходит только в
    теле POST, никогда в query;
  * исключения httpx (несут request с телом/заголовками) не логируются и не
    попадают в цепочку: наружу — новая ProviderError, поднятая вне except;
  * тела ответов, error_description и текст провайдера не логируются; WARNING
    содержит стадию, класс исхода, HTTP-статус и код ошибки из allowlist;
  * ответ ограничен MAX_RESPONSE_BYTES; редиректы не выполняются; повторов нет.
"""
import json
import logging
from typing import Mapping, Optional
from urllib.parse import urlencode

import httpx

from app.oauth.providers.base import (
    CANCELLED_ERROR, ProviderCallback, ProviderIdentity, ProviderRejected,
    ProviderUnavailable,
)
# Провайдер-нейтральные чистые валидаторы; живут в модуле Яндекса исторически
# (вынос в общий модуль — отдельный рефакторинг, чтобы не трогать Яндекс здесь).
from app.oauth.providers.yandex import (
    _clean_name, _printable_ascii, _valid_email, _valid_subject,
)

log = logging.getLogger(__name__)

PROVIDER_NAME = "vk"

AUTHORIZE_URL = "https://id.vk.ru/authorize"
TOKEN_URL = "https://id.vk.ru/oauth2/auth"
USERINFO_URL = "https://id.vk.ru/oauth2/user_info"

# Базовый профиль (имя, фамилия) + email. Телефон не запрашивается.
SCOPE = "vkid.personal_info email"

# Любая ошибка VK, кроме отмены, нормализуется к этому коду.
PROVIDER_ERROR = "provider_error"

TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
MAX_RESPONSE_BYTES = 64 * 1024
USER_AGENT = "MindCare-OAuth/1"

_CODE_MAX = 4096            # code VK ID («vk2.a.…») заметно длиннее яндексового
_STATE_MAX = 1024
_DEVICE_ID_MAX = 512
_ACCESS_TOKEN_MAX = 8192
_PAYLOAD_MAX = 8192         # JSON из параметра `payload`

# Коды ошибок OAuth, которые можно писать в лог как есть; прочее — "other".
_LOGGABLE_ERRORS = frozenset({
    "invalid_grant", "invalid_client", "invalid_request", "invalid_scope",
    "unauthorized_client", "unsupported_grant_type", "access_denied",
    "invalid_token", "slow_down", "server_error", "temporarily_unavailable",
})


def _payload_object(raw: object) -> dict:
    """Параметр `payload` (JSON-объект) → dict; иное → {}. Не бросает."""
    if not isinstance(raw, str) or not 0 < len(raw) <= _PAYLOAD_MAX:
        return {}
    try:
        value = json.loads(raw)
    except (ValueError, RecursionError):
        return {}
    return value if isinstance(value, dict) else {}


def _subject_of(value: object) -> Optional[str]:
    """user_id: строка как есть либо целое → строка. bool и прочее — None."""
    if type(value) is int:
        value = str(value)
    return _valid_subject(value)


def _suggested_name(user: dict) -> Optional[str]:
    """first_name + last_name (годится и одна из частей); иначе None."""
    parts = [
        part for part in (
            _clean_name(user.get("first_name"), min_len=1),
            _clean_name(user.get("last_name"), min_len=1),
        ) if part
    ]
    return _clean_name(" ".join(parts)) if parts else None


class VKProvider:
    """OAuthProvider для VK ID. Хранит только client_id и (в тестах)
    подменённый транспорт httpx — никакого состояния между запросами."""

    name = PROVIDER_NAME

    def __init__(
        self, client_id: str, *, transport: Optional[httpx.BaseTransport] = None,
    ):
        if not isinstance(client_id, str) or not client_id:
            raise ValueError("client_id required")
        self._client_id = client_id
        self._transport = transport

    # ── OAuthProvider ────────────────────────────────────────────────────────

    def build_authorize_url(
        self, *, state: str, code_challenge: str, redirect_uri: str,
    ) -> str:
        return AUTHORIZE_URL + "?" + urlencode({
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": SCOPE,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })

    def parse_callback(self, query: Mapping[str, str]) -> ProviderCallback:
        # Отдельные query-параметры имеют приоритет; `payload` — запасной вид.
        payload = _payload_object(query.get("payload"))

        def pick(key: str) -> object:
            value = query.get(key)
            return value if value not in (None, "") else payload.get(key)

        raw_error = pick("error")
        if raw_error is None or raw_error == "":
            error = None
        elif raw_error == CANCELLED_ERROR:
            error = CANCELLED_ERROR
        else:
            error = PROVIDER_ERROR
        # error_description намеренно не читается.

        state = _printable_ascii(pick("state"), _STATE_MAX)
        code = _printable_ascii(pick("code"), _CODE_MAX)
        device_id = _printable_ascii(pick("device_id"), _DEVICE_ID_MAX)
        if device_id is None:
            code = None   # без device_id обмен невозможен — не пытаемся
        extra = {}
        if code is not None and state is not None:
            extra = {"device_id": device_id, "state": state}
        return ProviderCallback(state=state, code=code, error=error, extra=extra)

    def resolve_identity(
        self, *, code: str, code_verifier: str, redirect_uri: str,
        extra: Mapping[str, str],
    ) -> ProviderIdentity:
        device_id = _printable_ascii(extra.get("device_id"), _DEVICE_ID_MAX)
        state = _printable_ascii(extra.get("state"), _STATE_MAX)
        if device_id is None or state is None:
            _warn("token", "rejected", None, "missing_device_id")
            raise ProviderRejected()

        with self._client() as client:
            access_token, token_subject = self._exchange_code(
                client, code, code_verifier, redirect_uri, device_id, state,
            )
            user = self._fetch_user(client, access_token)

        subject = _subject_of(user.get("user_id"))
        if subject is None:
            _warn("userinfo", "rejected", None, "invalid_user_id")
            raise ProviderRejected()
        # Токен выдан этому пользователю: расхождение = подмена ответа.
        if token_subject is not None and token_subject != subject:
            _warn("userinfo", "rejected", None, "user_id_mismatch")
            raise ProviderRejected()

        # Из профиля — только id, email и имя; остальные поля отбрасываются
        # вместе с dict и нигде не сохраняются.
        return ProviderIdentity(
            provider=PROVIDER_NAME,
            subject=subject,
            email=_valid_email(user.get("email")),
            suggested_name=_suggested_name(user),
        )

    # ── HTTP ─────────────────────────────────────────────────────────────────

    def _client(self) -> httpx.Client:
        return httpx.Client(
            transport=self._transport,
            timeout=TIMEOUT,
            follow_redirects=False,
            verify=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    @staticmethod
    def _post(client: httpx.Client, stage: str, url: str, data: dict):
        """(status, body | None). body=None — ответ больше MAX_RESPONSE_BYTES.

        Сетевые/TLS/таймаут-ошибки → ProviderUnavailable, поднятая ВНЕ блока
        except: исключение httpx (с request и телом формы) не попадает ни в
        __cause__, ни в __context__.
        """
        status: Optional[int] = None
        body: Optional[bytes] = None
        try:
            with client.stream("POST", url, data=data) as response:
                status = response.status_code
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > MAX_RESPONSE_BYTES:
                        break
                    chunks.append(chunk)
                else:
                    body = b"".join(chunks)
        except httpx.HTTPError:
            status = None
        if status is None:
            _warn(stage, "network", None, None)
            raise ProviderUnavailable()
        return status, body

    def _exchange_code(
        self, client: httpx.Client, code: str, verifier: str, redirect_uri: str,
        device_id: str, state: str,
    ):
        status, body = self._post(client, "token", TOKEN_URL, {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": self._client_id,
            "device_id": device_id,
            "redirect_uri": redirect_uri,
            "state": state,
        })
        _raise_for_status("token", status, body)
        payload = _json_object("token", body)
        _raise_for_error_field("token", status, payload)

        # VK возвращает state обмена; если он есть — обязан совпасть.
        returned_state = payload.get("state")
        if returned_state not in (None, "") and returned_state != state:
            _warn("token", "rejected", status, "state_mismatch")
            raise ProviderRejected()

        token = payload.get("access_token")
        if _printable_ascii(token, _ACCESS_TOKEN_MAX) is None:
            _warn("token", "rejected", status, "missing_access_token")
            raise ProviderRejected()
        # refresh_token / id_token намеренно не читаются.
        return token, _subject_of(payload.get("user_id"))

    def _fetch_user(self, client: httpx.Client, access_token: str) -> dict:
        status, body = self._post(client, "userinfo", USERINFO_URL, {
            "client_id": self._client_id,
            "access_token": access_token,
        })
        _raise_for_status("userinfo", status, body)
        payload = _json_object("userinfo", body)
        _raise_for_error_field("userinfo", status, payload)
        user = payload.get("user")
        if not isinstance(user, dict):
            _warn("userinfo", "rejected", status, "missing_user")
            raise ProviderRejected()
        return user


# ── разбор ответа ────────────────────────────────────────────────────────────

def _raise_for_status(stage: str, status: int, body: Optional[bytes]) -> None:
    if 200 <= status < 300:
        return
    if status == 429 or status >= 500 or status < 200 or 300 <= status < 400:
        # перегрузка / сбой VK / неожиданный редирект — инфраструктура
        _warn(stage, "unavailable", status, None)
        raise ProviderUnavailable()
    # Прочие 4xx: VK отклонил обмен или токен.
    _warn(stage, "rejected", status, _error_code(body))
    raise ProviderRejected()


def _raise_for_error_field(stage: str, status: int, payload: dict) -> None:
    """VK может вернуть ошибку телом 2xx: {"error": "...", ...}."""
    if "error" not in payload:
        return
    _warn(stage, "rejected", status, _loggable(payload.get("error")))
    raise ProviderRejected()


def _json_object(stage: str, body: Optional[bytes]) -> dict:
    """Тело 2xx → dict. Слишком большое / не JSON / не объект — сбой ответа
    провайдера (ProviderUnavailable), без текста тела в логах и исключении."""
    payload = None
    if body is not None:
        try:
            payload = json.loads(body)
        except (ValueError, RecursionError):
            payload = None
    if not isinstance(payload, dict):
        _warn(stage, "unavailable", None, "malformed_response")
        raise ProviderUnavailable()
    return payload


def _error_code(body: Optional[bytes]) -> str:
    """Код OAuth-ошибки для лога — только из allowlist, иначе "other"."""
    try:
        payload = json.loads(body) if body else None
    except (ValueError, RecursionError):
        return "other"
    return _loggable(payload.get("error") if isinstance(payload, dict) else None)


def _loggable(code: object) -> str:
    return code if isinstance(code, str) and code in _LOGGABLE_ERRORS else "other"


def _warn(stage: str, kind: str, status: Optional[int], detail: Optional[str]) -> None:
    log.warning(
        "VK ID %s failed: %s (status=%s, detail=%s)",
        stage, kind, status if status is not None else "-", detail or "-",
    )
