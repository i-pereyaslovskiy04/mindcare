"""
Адаптер Яндекс ID (Stage Social Auth 3A): Authorization Code + PKCE S256.

Публичный клиент: client_secret НЕ используется — по документации Яндекс ID при
переданном `code_verifier` секретный ключ не требуется. Обмен идёт формой
grant_type / code / code_verifier / client_id; redirect_uri в запрос токена не
входит (Яндекс его не документирует для этого запроса).

Субъект — `id` профиля (глобальный идентификатор пользователя Яндекса), НЕ
`psuid`: тот формируется из пары client_id + пользователь и меняется при смене
приложения (отдельные DEV/PROD-приложения, перерегистрация), а ClientID изменить
нельзя. `id` хранится как есть — строкой, без приведения к int и без
нормализации; формат (только цифры) намеренно не требуется.

Права (Stage Social Auth 4): `login:email login:info`. Из профиля читаются
ТОЛЬКО три значения:
  * `id`            → subject;
  * `default_email` → ProviderIdentity.email (нормализованный; невалидный или
                      отсутствующий → None — вход по привязанной identity от
                      него не зависит, а регистрация без email закрыта
                      сервисом);
  * имя             → ProviderIdentity.suggested_name: `first_name` +
                      `last_name` → `real_name` → `display_name` → `login`.
Пол, телефон, дата рождения, аватар, `psuid` и прочие поля не читаются и
нигде не сохраняются. Email провайдера — не доказательство владения: его
подтверждает OTP MindCare, и он никогда не используется для привязки к
существующему аккаунту.

Безопасность:
  * адреса Яндекса — константы модуля, не настройки;
  * токены провайдера живут только внутри resolve_identity и нигде не
    сохраняются и не логируются; токен user-info — только в заголовке
    `Authorization: OAuth`, никогда в query;
  * исключения httpx хранят request вместе с заголовками — наружу уходит только
    новая ProviderError без __cause__/__context__ (raise вне блока except), сами
    исключения httpx не логируются;
  * тела ответов, error_description и текст провайдера не логируются; WARNING
    содержит лишь стадию, класс исхода, HTTP-статус и код ошибки из allowlist;
  * ответ провайдера ограничен MAX_RESPONSE_BYTES; редиректы не выполняются;
    повторов нет (authorization code одноразовый).
"""
import json
import logging
import unicodedata
from typing import Mapping, Optional
from urllib.parse import urlencode

import httpx
from email_validator import EmailNotValidError, validate_email

from app.core.normalization import normalize_email
from app.oauth.providers.base import (
    CANCELLED_ERROR, ProviderCallback, ProviderIdentity, ProviderRejected,
    ProviderUnavailable,
)

log = logging.getLogger(__name__)

PROVIDER_NAME = "yandex"

AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
TOKEN_URL = "https://oauth.yandex.ru/token"
USERINFO_URL = "https://login.yandex.ru/info"

# email — адрес для OTP регистрации; info — имя для профиля (Stage 4).
SCOPE = "login:email login:info"

# Любая ошибка Яндекса, кроме отмены, нормализуется к этому коду: generic core
# сравнивает error только с CANCELLED_ERROR, остальное → oauth_provider_error.
PROVIDER_ERROR = "provider_error"

TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)
MAX_RESPONSE_BYTES = 64 * 1024
USER_AGENT = "MindCare-OAuth/1"

_CALLBACK_VALUE_MAX = 1024     # state/code из query (state у Яндекса ≤ 1024)
_ACCESS_TOKEN_MAX = 4096
_SUBJECT_MAX = 255             # = user_oauth_identities.provider_subject
_EMAIL_MAX = 255               # = users.email / oauth_pending_tickets.email
_NAME_MIN = 2                  # как у регистрации по паролю
_NAME_MAX = 255                # = users.full_name
# Порядок выбора имени; first_name + last_name проверяются раньше всех.
_NAME_FALLBACK_FIELDS = ("real_name", "display_name", "login")

# Коды ошибок токен-эндпоинта (документация Яндекс ID), которые можно писать в
# лог как есть. Всё прочее — "other"; error_description не читается вовсе.
_LOGGABLE_TOKEN_ERRORS = frozenset({
    "invalid_grant", "invalid_client", "invalid_request", "invalid_scope",
    "unauthorized_client", "unsupported_grant_type",
})


def _printable_ascii(value: object, max_len: int) -> Optional[str]:
    """Значение из query: непустая печатная ASCII-строка без пробелов, иначе None."""
    if not isinstance(value, str) or not 0 < len(value) <= max_len:
        return None
    if not all("\x21" <= ch <= "\x7e" for ch in value):
        return None
    return value


def _valid_subject(value: object) -> Optional[str]:
    """`id` профиля: str, 1..255 символов, не только пробелы, без управляющих/
    служебных символов Unicode (категории C*). Возвращается без изменений."""
    if type(value) is not str or not 0 < len(value) <= _SUBJECT_MAX:
        return None
    if not value.strip():
        return None
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        return None
    return value


def _has_control_chars(value: str) -> bool:
    return any(unicodedata.category(ch).startswith("C") for ch in value)


def _valid_email(value: object) -> Optional[str]:
    """`default_email`: синтаксически валидный адрес ≤ 255 символов →
    нормализованный (lower/trim), иначе None. Доставляемость не проверяется:
    владение адресом подтверждает OTP MindCare."""
    if type(value) is not str or _has_control_chars(value):
        return None
    candidate = normalize_email(value)
    if not 0 < len(candidate) <= _EMAIL_MAX:
        return None
    try:
        validate_email(candidate, check_deliverability=False)
    except EmailNotValidError:
        return None
    return candidate


def _clean_name(value: object, min_len: int = _NAME_MIN) -> Optional[str]:
    """Кандидат в имя: str без управляющих символов, пробелы схлопнуты,
    min_len..255 символов после trim. Иначе None (берётся следующий fallback)."""
    if type(value) is not str or _has_control_chars(value):
        return None
    cleaned = " ".join(value.split())
    if not min_len <= len(cleaned) <= _NAME_MAX:
        return None
    return cleaned


def _suggested_name(profile: dict) -> Optional[str]:
    """first_name + last_name → real_name → display_name → login. Отдельно
    имя или фамилия тоже годятся (полезная часть пары)."""
    parts = [
        part for part in (
            _clean_name(profile.get("first_name"), min_len=1),
            _clean_name(profile.get("last_name"), min_len=1),
        ) if part
    ]
    full = _clean_name(" ".join(parts)) if parts else None
    if full:
        return full
    for field_name in _NAME_FALLBACK_FIELDS:
        name = _clean_name(profile.get(field_name))
        if name:
            return name
    return None


class YandexProvider:
    """OAuthProvider для Яндекс ID. Хранит только client_id и (в тестах)
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
        raw_error = query.get("error")
        if raw_error is None or raw_error == "":
            error = None
        elif raw_error == CANCELLED_ERROR:
            error = CANCELLED_ERROR
        else:
            error = PROVIDER_ERROR
        # error_description намеренно не читается.
        return ProviderCallback(
            state=_printable_ascii(query.get("state"), _CALLBACK_VALUE_MAX),
            code=_printable_ascii(query.get("code"), _CALLBACK_VALUE_MAX),
            error=error,
            extra={},
        )

    def resolve_identity(
        self, *, code: str, code_verifier: str, redirect_uri: str,
        extra: Mapping[str, str],
    ) -> ProviderIdentity:
        # redirect_uri и extra у Яндекса в обмене не участвуют.
        with self._client() as client:
            access_token = self._exchange_code(client, code, code_verifier)
            profile = self._fetch_profile(client, access_token)
        # Из профиля — только id, email и имя; остальные поля отбрасываются
        # вместе с dict и нигде не сохраняются.
        return ProviderIdentity(
            provider=PROVIDER_NAME,
            subject=self._subject(profile),
            email=_valid_email(profile.get("default_email")),
            suggested_name=_suggested_name(profile),
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
    def _send(client: httpx.Client, stage: str, method: str, url: str, **kwargs):
        """(status, body | None). body=None — ответ больше MAX_RESPONSE_BYTES.

        Сетевые/TLS/таймаут-ошибки → ProviderUnavailable, поднятая ВНЕ блока
        except: исключение httpx (с request и заголовками) не попадает ни в
        __cause__, ни в __context__.
        """
        status: Optional[int] = None
        body: Optional[bytes] = None
        try:
            with client.stream(method, url, **kwargs) as response:
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

    def _exchange_code(self, client: httpx.Client, code: str, verifier: str) -> str:
        status, body = self._send(
            client, "token", "POST", TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": self._client_id,
            },
        )
        _raise_for_status("token", status, body)
        payload = _json_object("token", body)
        token = payload.get("access_token")
        if _printable_ascii(token, _ACCESS_TOKEN_MAX) is None:
            _warn("token", "rejected", status, "missing_access_token")
            raise ProviderRejected()
        return token

    def _fetch_profile(self, client: httpx.Client, access_token: str) -> dict:
        status, body = self._send(
            client, "userinfo", "GET", USERINFO_URL,
            headers={"Authorization": f"OAuth {access_token}"},
        )
        _raise_for_status("userinfo", status, body)
        profile = _json_object("userinfo", body)
        # Токен выдан нашему приложению — Яндекс возвращает client_id, для
        # которого он выпущен; отсутствие/несовпадение = подмена токена.
        if profile.get("client_id") != self._client_id:
            _warn("userinfo", "rejected", status, "client_id_mismatch")
            raise ProviderRejected()
        return profile

    @staticmethod
    def _subject(profile: dict) -> str:
        subject = _valid_subject(profile.get("id"))
        if subject is None:
            _warn("userinfo", "rejected", None, "invalid_id")
            raise ProviderRejected()
        return subject


# ── разбор ответа ────────────────────────────────────────────────────────────

def _raise_for_status(stage: str, status: int, body: Optional[bytes]) -> None:
    if 200 <= status < 300:
        return
    if status == 429 or status >= 500 or status < 200 or 300 <= status < 400:
        # перегрузка / сбой Яндекса / неожиданный редирект — инфраструктура
        _warn(stage, "unavailable", status, None)
        raise ProviderUnavailable()
    # Прочие 4xx: Яндекс отклонил обмен (invalid_grant, invalid_client, …) или
    # токен (401/403 на user-info).
    _warn(stage, "rejected", status, _error_code(body) if stage == "token" else None)
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
    code = payload.get("error") if isinstance(payload, dict) else None
    return code if code in _LOGGABLE_TOKEN_ERRORS else "other"


def _warn(stage: str, kind: str, status: Optional[int], detail: Optional[str]) -> None:
    log.warning(
        "Yandex ID %s failed: %s (status=%s, detail=%s)",
        stage, kind, status if status is not None else "-", detail or "-",
    )
