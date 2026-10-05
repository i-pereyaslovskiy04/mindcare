"""
Social login core (Stage Social Auth 2B/4) — бизнес-логика, без FastAPI/HTTP.

Один и тот же OAuth-поток для «Входа» и «Регистрации» — что делать дальше,
решает callback по факту:
  * identity (provider, subject) уже привязана → login-ticket → complete →
    обычная сессия (только чистый студент);
  * identity неизвестна → registration-ticket с email и именем из профиля
    провайдера → init (OTP на этот email) → confirm (код + согласие MindCare)
    → аккаунт без пароля + identity + сессия.
Пользователь не вводит ни имя, ни email, ни пароль. Callback сам не создаёт ни
пользователя, ни identity, ни сессию. Привязки к существующему аккаунту по
совпадению email нет; email провайдера подтверждает OTP MindCare. Обычный
allowlist доменов к регистрации через провайдера НЕ применяется (ADR-027) —
регистрация по паролю его по-прежнему соблюдает.

Поток: start (state + PKCE + browser binding) → callback (state проверен и
списан ДО разбора исхода провайдера) → одноразовый ticket.
"""
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Mapping, Optional

from app.auth import service as auth_service
from app.auth.roles import is_pure_student
from app.core.config import settings
from app.core.encryption import decrypt_text, encrypt_text
from app.core.normalization import mask_email, normalize_email
from app.oauth import storage
from app.oauth.errors import (
    OAuthLoginDenied, OAuthProviderUnavailableError, OAuthRegistrationError,
    OAuthTicketInvalidError,
)
from app.oauth.providers import get_provider
from app.oauth.providers.base import CANCELLED_ERROR, ProviderError
from app.oauth.security import (
    code_challenge_s256, constant_time_equals, generate_code_verifier,
    generate_state, generate_ticket, sha256_hex,
)

log = logging.getLogger(__name__)

STATE_TTL = timedelta(minutes=10)     # = время жизни code у Яндекса
TICKET_TTL = timedelta(minutes=2)
# Registration-ticket живёт дольше: письмо, ввод кода. Срок фиксирован —
# повторная отправка кода его НЕ продлевает; истёк → вход через провайдера заново.
REGISTRATION_TICKET_TTL = timedelta(minutes=30)

STATE_COOKIE_NAME = "mindcare_oauth_state"
STATE_COOKIE_PATH = "/api/auth/oauth"
STATE_COOKIE_MAX_AGE = int(STATE_TTL.total_seconds())

# Фиксированные внешние коды callback (fragment). Текст провайдера наружу
# никогда не попадает.
RESULT_LOGIN = "login"
RESULT_REGISTRATION = "registration"
ERROR_FAILED = "oauth_failed"
ERROR_CANCELLED = "oauth_cancelled"
# Новая identity без пригодного email у провайдера: регистрации нет (fail closed).
ERROR_EMAIL_REQUIRED = "oauth_email_required"


@dataclass(frozen=True)
class StartResult:
    authorize_url: str
    state: str          # raw state — только для HttpOnly cookie, не логируется


@dataclass(frozen=True)
class CallbackOutcome:
    fragment: Mapping[str, str]
    clear_cookie: bool
    audit_code: Optional[str] = None   # failure_reason_code для failed_login
    # Имя ЗАРЕГИСТРИРОВАННОГО адаптера, обработавшего callback (для
    # auth_log.auth_method). None — провайдер не разрешён реестром; сырой
    # path-параметр сюда не попадает.
    provider: Optional[str] = None


@dataclass(frozen=True)
class CompleteResult:
    session_token: str
    expires_at: datetime
    user: dict = field(repr=False)
    provider: Optional[str] = None   # из списанного ticket (auth_log.auth_method)


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

def _failed(
    audit_code: Optional[str], *, clear_cookie: bool, provider: Optional[str] = None,
) -> CallbackOutcome:
    return CallbackOutcome({"error": ERROR_FAILED}, clear_cookie, audit_code, provider)


def handle_callback(
    provider_name: str,
    query: Mapping[str, str],
    cookie_state: Optional[str],
) -> CallbackOutcome:
    """
    Утверждённый порядок: provider → parse → browser binding (state == cookie)
    → атомарное списание state (commit) → ТОЛЬКО затем исход провайдера →
    verifier → resolve_identity (вне транзакции) → identity → известна: проверки
    и login-ticket; неизвестна: registration-ticket.

    Несовпадение state/cookie: state в БД НЕ списывается, cookie НЕ очищается —
    подложенная чужая ссылка не ломает легитимный вход. После списания cookie
    очищается на любом исходе. Отмена пользователем сжигает state и не
    аудируется.
    """
    provider = get_provider(provider_name)
    if provider is None:
        return _failed(None, clear_cookie=False)

    name = provider.name   # авторитетное имя адаптера из реестра

    try:
        callback = provider.parse_callback(query)
    except Exception:   # noqa: BLE001 — некорректный callback = невалидный state
        return _failed("oauth_state_invalid", clear_cookie=False, provider=name)

    state = callback.state
    if not state or not cookie_state or not constant_time_equals(state, cookie_state):
        return _failed("oauth_state_invalid", clear_cookie=False, provider=name)

    request = storage.consume_auth_request(
        state_hash=sha256_hex(state), provider=name,
    )
    if request is None or request["intent"] != "login":
        return _failed("oauth_state_invalid", clear_cookie=True, provider=name)

    # ── state сожжён; дальше каждый исход очищает cookie ──
    if callback.error:
        if callback.error == CANCELLED_ERROR:
            return CallbackOutcome({"error": ERROR_CANCELLED}, True, None, name)
        return _failed("oauth_provider_error", clear_cookie=True, provider=name)
    if not callback.code:
        return _failed("oauth_provider_error", clear_cookie=True, provider=name)

    try:
        verifier = decrypt_text(request["code_verifier_enc"])
    except Exception:   # noqa: BLE001 — ключ/данные; без деталей наружу
        return _failed("internal_error", clear_cookie=True, provider=name)

    try:
        identity = provider.resolve_identity(
            code=callback.code,
            code_verifier=verifier,
            redirect_uri=callback_redirect_uri(name),
            extra=callback.extra,
        )
    except ProviderError:
        return _failed("oauth_provider_error", clear_cookie=True, provider=name)
    except Exception:   # noqa: BLE001 — дефект адаптера: fail closed
        return _failed("oauth_provider_error", clear_cookie=True, provider=name)

    if identity.provider != name or not identity.subject:
        return _failed("oauth_provider_error", clear_cookie=True, provider=name)

    found = storage.find_identity_user(provider=name, subject=identity.subject)
    if found is None:
        # Новая identity — штатное начало регистрации (Stage 4), не отказ входа:
        # аудит не пишется. Здесь НЕ создаются ни пользователь, ни identity, ни
        # сессия — только одноразовый registration-ticket с email и именем
        # провайдера. Автосвязывания по email нет.
        email = _provider_email(identity.email)
        if email is None:
            return CallbackOutcome({"error": ERROR_EMAIL_REQUIRED}, True, None, name)
        ticket = generate_ticket()
        storage.create_registration_ticket(
            ticket_hash=sha256_hex(ticket),
            provider=name,
            subject=identity.subject,
            email=email,
            suggested_name=_initial_name(identity.suggested_name, email),
            expires_at=_now() + REGISTRATION_TICKET_TTL,
        )
        return CallbackOutcome(
            {"result": RESULT_REGISTRATION, "ticket": ticket}, True, None, name,
        )

    user = found["user"]
    try:
        if user is None:
            raise OAuthLoginDenied("account_disabled")
        assert_social_login_allowed(user)   # ранняя проверка; complete — авторитетно
    except OAuthLoginDenied as denial:
        return CallbackOutcome(
            {"error": denial.external_code}, True, denial.audit_code, name,
        )

    ticket = generate_ticket()
    storage.create_login_ticket(
        ticket_hash=sha256_hex(ticket),
        provider=name,
        subject=identity.subject,
        user_id=int(found["user_id"]),
        expires_at=_now() + TICKET_TTL,
    )
    return CallbackOutcome({"result": RESULT_LOGIN, "ticket": ticket}, True, None, name)


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
        provider=result["provider"],
    )


# ── регистрация через провайдера (Stage Social Auth 4) ───────────────────────

_NAME_MIN = 2
_NAME_MAX = 255
_EMAIL_MAX = 255
_EMAIL_DELIVERY_FAILED_MESSAGE = "Не удалось отправить письмо. Попробуйте позже."
_CONSENT_REQUIRED_MESSAGE = "Необходимо принять политику персональных данных"


def _provider_email(email: object) -> Optional[str]:
    """Email провайдера для ticket: нормализованный, ≤ 255, с одним «@»;
    иначе None (регистрация закрыта). Синтаксис уже проверил адаптер — здесь
    защита ядра от чужого/дефектного адаптера и от CHECK нормализации."""
    if not isinstance(email, str):
        return None
    value = normalize_email(email)
    if not 0 < len(value) <= _EMAIL_MAX or value.count("@") != 1:
        return None
    local, _, domain = value.partition("@")
    if not local or not domain or any(ch.isspace() for ch in value):
        return None
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        return None
    return value


def _clean_name(name: object) -> Optional[str]:
    """Имя для профиля: без управляющих символов, пробелы схлопнуты, 2..255
    символов (минимум — как у регистрации по паролю). Иначе None."""
    if not isinstance(name, str):
        return None
    if any(unicodedata.category(ch).startswith("C") for ch in name):
        return None
    value = " ".join(name.split())
    return value if _NAME_MIN <= len(value) <= _NAME_MAX else None


def _initial_name(suggested: Optional[str], email: str) -> str:
    """Начальное имя профиля: имя провайдера, иначе локальная часть email,
    иначе сам email (≥ 3 символов всегда). Заглушка «Пользователь» не нужна;
    имя затем меняется в профиле."""
    return (
        _clean_name(suggested)
        or _clean_name(email.partition("@")[0])
        or email
    )


def registration_init(ticket: str) -> str:
    """
    Отправка (и повторная отправка) кода регистрации. Клиент передаёт ТОЛЬКО
    ticket: email и имя берутся из ticket (их записал callback из профиля
    провайдера). Повтор с тем же ticket — новый код под cooldown 60 с.

    Письмо уходит ПОСЛЕ commit; его сбой состояние в БД не откатывает.
    Возвращает маскированный email (для экрана «Отправили код на …»).
    """
    if not ticket:
        raise OAuthTicketInvalidError()
    code, email = storage.issue_registration_otp(sha256_hex(ticket))

    from app.services.email_service import send_registration_otp
    delivered = True
    try:
        send_registration_otp(email, code)
    except Exception as exc:   # noqa: BLE001 — без текста SMTP и без кода в логах
        delivered = False
        log.warning(
            "[oauth registration_init] failed to send email to %s (%s)",
            mask_email(email), type(exc).__name__,
        )
    if not delivered:
        raise OAuthRegistrationError(
            "email_delivery_failed", _EMAIL_DELIVERY_FAILED_MESSAGE, 500,
        )
    return mask_email(email)


def registration_confirm(
    ticket: str, code: str, *, consent_accepted: bool,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> CompleteResult:
    """
    ticket + OTP + согласие MindCare → аккаунт без пароля, роль student,
    согласия, identity провайдера и обычная сессия MindCare одним commit
    (storage). Затем — те же post-commit действия, что у регистрации по
    паролю (soft-fail).

    Consent gate: без буквального True не создаётся ничего (ни аккаунт, ни
    consent_records, ни сессия) и OTP не проверяется. Согласие провайдера
    согласие MindCare не заменяет.
    """
    if consent_accepted is not True:
        raise OAuthRegistrationError(
            "consent_required", _CONSENT_REQUIRED_MESSAGE, 422,
        )
    if not ticket:
        raise OAuthTicketInvalidError()
    result = storage.complete_registration_atomic(
        sha256_hex(ticket), code,
        required_consent_types=auth_service.REQUIRED_CONSENTS,
        ip=ip, user_agent=user_agent,
    )
    auth_service.run_post_registration_actions(
        result["user"], ip=ip, user_agent=user_agent,
    )
    return CompleteResult(
        session_token=result["session_token"],
        expires_at=result["expires_at"],
        user=result["user"],
        provider=result["provider"],
    )
