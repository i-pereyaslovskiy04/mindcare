"""
Social login core (Stage Social Auth 2B) — бизнес-логика, без FastAPI/HTTP.

Поддерживается ТОЛЬКО вход по уже привязанной identity (user_oauth_identities)
чистого студента. Неизвестная identity не создаёт ни пользователя, ни identity,
ни ticket — регистрации через провайдера нет.

Поток: start (state + PKCE + browser binding) → callback (state проверен и
списан ДО разбора исхода провайдера) → одноразовый login-ticket → complete
(ticket → обычная user_sessions сессия одним commit).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

from app.auth import service as auth_service
from app.auth.roles import is_pure_student
from app.core.config import settings
from app.core.encryption import decrypt_text, encrypt_text
from app.oauth import storage
from app.oauth.errors import (
    OAuthLoginDenied, OAuthProviderUnavailableError, OAuthTicketInvalidError,
)
from app.oauth.providers import get_provider
from app.oauth.providers.base import CANCELLED_ERROR, ProviderError
from app.oauth.security import (
    code_challenge_s256, constant_time_equals, generate_code_verifier,
    generate_state, generate_ticket, sha256_hex,
)

STATE_TTL = timedelta(minutes=10)     # = время жизни code у Яндекса
TICKET_TTL = timedelta(minutes=2)

STATE_COOKIE_NAME = "mindcare_oauth_state"
STATE_COOKIE_PATH = "/api/auth/oauth"
STATE_COOKIE_MAX_AGE = int(STATE_TTL.total_seconds())

# Фиксированные внешние коды callback (fragment). Текст провайдера наружу
# никогда не попадает.
RESULT_LOGIN = "login"
ERROR_FAILED = "oauth_failed"
ERROR_CANCELLED = "oauth_cancelled"
ERROR_REGISTRATION_NOT_AVAILABLE = "social_registration_not_available"


@dataclass(frozen=True)
class StartResult:
    authorize_url: str
    state: str          # raw state — только для HttpOnly cookie, не логируется


@dataclass(frozen=True)
class CallbackOutcome:
    fragment: Mapping[str, str]
    clear_cookie: bool
    audit_code: Optional[str] = None   # failure_reason_code для failed_login


@dataclass(frozen=True)
class CompleteResult:
    session_token: str
    expires_at: datetime
    user: dict = field(repr=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def callback_redirect_uri(provider_name: str) -> str:
    base = settings.OAUTH_CALLBACK_BASE_URL.rstrip("/")
    return f"{base}/api/auth/oauth/{provider_name}/callback"


def state_cookie_secure() -> bool:
    """Secure — по схеме настроенного callback base, а не входящего запроса:
    за TLS-прокси без proxy-headers запрос выглядит как http."""
    return settings.OAUTH_CALLBACK_BASE_URL.lower().startswith("https://")


def assert_social_login_allowed(user: dict) -> None:
    """Те же инварианты, что у входа по паролю, плюс правило «чистый студент».
    Бросает OAuthLoginDenied со стабильным audit-кодом."""
    try:
        auth_service.ensure_user_can_start_session(user)
    except auth_service.AuthError as exc:
        raise OAuthLoginDenied(exc.audit_code or "account_disabled") from None
    if not is_pure_student(user.get("roles") or []):
        raise OAuthLoginDenied("social_login_not_allowed")


# ── start ────────────────────────────────────────────────────────────────────

def start_login(provider_name: str) -> StartResult:
    """Создаёт login-запрос: в БД hash state и зашифрованный verifier."""
    provider = get_provider(provider_name)
    if provider is None:
        raise OAuthProviderUnavailableError()

    state = generate_state()
    verifier = generate_code_verifier()
    storage.create_login_request(
        state_hash=sha256_hex(state),
        provider=provider.name,
        code_verifier_enc=encrypt_text(verifier),
        expires_at=_now() + STATE_TTL,
    )
    authorize_url = provider.build_authorize_url(
        state=state,
        code_challenge=code_challenge_s256(verifier),
        redirect_uri=callback_redirect_uri(provider.name),
    )
    return StartResult(authorize_url=authorize_url, state=state)


# ── callback ─────────────────────────────────────────────────────────────────

def _failed(audit_code: Optional[str], *, clear_cookie: bool) -> CallbackOutcome:
    return CallbackOutcome({"error": ERROR_FAILED}, clear_cookie, audit_code)


def handle_callback(
    provider_name: str,
    query: Mapping[str, str],
    cookie_state: Optional[str],
) -> CallbackOutcome:
    """
    Утверждённый порядок: provider → parse → browser binding (state == cookie)
    → атомарное списание state (commit) → ТОЛЬКО затем исход провайдера →
    verifier → resolve_identity (вне транзакции) → identity → проверки →
    login-ticket.

    Несовпадение state/cookie: state в БД НЕ списывается, cookie НЕ очищается —
    подложенная чужая ссылка не ломает легитимный вход. После списания cookie
    очищается на любом исходе. Отмена пользователем сжигает state и не
    аудируется.
    """
    provider = get_provider(provider_name)
    if provider is None:
        return _failed(None, clear_cookie=False)

    try:
        callback = provider.parse_callback(query)
    except Exception:   # noqa: BLE001 — некорректный callback = невалидный state
        return _failed("oauth_state_invalid", clear_cookie=False)

    state = callback.state
    if not state or not cookie_state or not constant_time_equals(state, cookie_state):
        return _failed("oauth_state_invalid", clear_cookie=False)

    request = storage.consume_auth_request(
        state_hash=sha256_hex(state), provider=provider.name,
    )
    if request is None or request["intent"] != "login":
        return _failed("oauth_state_invalid", clear_cookie=True)

    # ── state сожжён; дальше каждый исход очищает cookie ──
    if callback.error:
        if callback.error == CANCELLED_ERROR:
            return CallbackOutcome({"error": ERROR_CANCELLED}, True, None)
        return _failed("oauth_provider_error", clear_cookie=True)
    if not callback.code:
        return _failed("oauth_provider_error", clear_cookie=True)

    try:
        verifier = decrypt_text(request["code_verifier_enc"])
    except Exception:   # noqa: BLE001 — ключ/данные; без деталей наружу
        return _failed("internal_error", clear_cookie=True)

    try:
        identity = provider.resolve_identity(
            code=callback.code,
            code_verifier=verifier,
            redirect_uri=callback_redirect_uri(provider.name),
            extra=callback.extra,
        )
    except ProviderError:
        return _failed("oauth_provider_error", clear_cookie=True)
    except Exception:   # noqa: BLE001 — дефект адаптера: fail closed
        return _failed("oauth_provider_error", clear_cookie=True)

    if identity.provider != provider.name or not identity.subject:
        return _failed("oauth_provider_error", clear_cookie=True)

    found = storage.find_identity_user(provider=provider.name, subject=identity.subject)
    if found is None:
        # Регистрации через провайдера нет: ни пользователя, ни identity, ни
        # ticket, никакого автосвязывания по email.
        return CallbackOutcome(
            {"error": ERROR_REGISTRATION_NOT_AVAILABLE}, True, "oauth_identity_unknown",
        )

    user = found["user"]
    try:
        if user is None:
            raise OAuthLoginDenied("account_disabled")
        assert_social_login_allowed(user)   # ранняя проверка; complete — авторитетно
    except OAuthLoginDenied as denial:
        return CallbackOutcome({"error": denial.external_code}, True, denial.audit_code)

    ticket = generate_ticket()
    storage.create_login_ticket(
        ticket_hash=sha256_hex(ticket),
        provider=provider.name,
        subject=identity.subject,
        user_id=int(found["user_id"]),
        expires_at=_now() + TICKET_TTL,
    )
    return CallbackOutcome({"result": RESULT_LOGIN, "ticket": ticket}, True, None)


# ── complete ─────────────────────────────────────────────────────────────────

def complete_login(
    ticket: str, *, ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> CompleteResult:
    """login-ticket → обычная сессия. Бросает OAuthTicketInvalidError или
    OAuthLoginDenied (ticket при этом сожжён); технический сбой — как есть
    (ticket остаётся годным)."""
    if not ticket:
        raise OAuthTicketInvalidError()
    result = storage.complete_login_atomic(
        sha256_hex(ticket),
        check_user=assert_social_login_allowed,
        ip=ip,
        user_agent=user_agent,
    )
    return CompleteResult(
        session_token=result["session_token"],
        expires_at=result["expires_at"],
        user=result["user"],
    )
