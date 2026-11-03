"""
/api/auth/oauth/* — social login core (Stage Social Auth 2B).

  POST /{provider}/start    → {authorize_url} + HttpOnly state-cookie
  GET  /{provider}/callback → 302 на OAUTH_FRONTEND_CALLBACK_URL#...
  POST /complete            → SessionResponse (тот же, что у входа по паролю)
  POST /registration/preview → что показать на шаге email (VK-1B), без изменений
  POST /registration/init    → OTP на email ticket (Stage 4); для VK — с выбором email
  POST /registration/confirm → SessionResponse: аккаунт + identity + сессия
  POST /registration/resume  → состояние для продолжения из письма (read-only)

Продолжение регистрации из письма (/register/social): callback новой identity
кладёт raw registration-ticket в HttpOnly SameSite=Strict cookie с путём
/api/auth/oauth/registration. Endpoint'ы регистрации берут ticket из тела
(поток в памяти вкладки) или из cookie; оба сразу — только если совпадают
(иначе 409, fail closed). Без cookie и без тела продолжить нельзя: письмо с
кодом в другом браузере регистрацию не завершит и email не изменит.

Ошибки OAuth-потока — 400/403/404/429, НЕ 401: frontend client.js трактует
любой 401 как истёкшую сессию. Callback всегда отвечает redirect (это
навигация браузера), результат — во fragment: он не уходит на сервер, в access
log и Referer. Session token в URL не попадает никогда.
"""
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.audit import Actor, AuthMethod, Outcome, record_event
from app.audit.request_context import build_request_context
from app.auth.schemas import SessionResponse
from app.auth.security import hash_session_token
from app.core.config import settings
from app.core.rate_limit import RateLimitExceeded, enforce as enforce_rate_limit
from app.oauth import service
from app.oauth.errors import (
    OAuthLoginDenied, OAuthProviderUnavailableError, OAuthRegistrationError,
    OAuthTicketInvalidError,
)
from app.oauth.schemas import (
    OAuthCompleteRequest, OAuthRegistrationConfirmRequest,
    OAuthRegistrationInitRequest, OAuthRegistrationInitResponse,
    OAuthRegistrationPreviewRequest, OAuthRegistrationPreviewResponse,
    OAuthRegistrationResumeRequest, OAuthRegistrationResumeResponse,
    OAuthStartResponse,
)
from app.oauth.security import constant_time_equals, sha256_hex

router = APIRouter(prefix="/auth/oauth", tags=["auth"])

_RATE_LIMIT_MESSAGE = "Слишком много попыток. Попробуйте позже."
_PROVIDER_UNAVAILABLE_MESSAGE = "Вход через этот сервис недоступен."
_TICKET_INVALID_MESSAGE = (
    "Ссылка для входа недействительна или устарела. Начните вход заново."
)
_REGISTRATION_NOT_FOUND_MESSAGE = (
    "Продолжить регистрацию можно только в браузере, где вы начинали вход "
    "через Яндекс или VK. Начните заново."
)
_REGISTRATION_CONFLICT_MESSAGE = (
    "Регистрация через Яндекс или VK уже начата заново в другой вкладке. "
    "Продолжите её там или начните заново."
)
_DENIED_MESSAGES = {
    "account_unavailable":
        "Доступ к системе не активирован. Обратитесь к администратору.",
    "social_login_not_allowed":
        "Для этого аккаунта вход через внешний сервис недоступен. "
        "Войдите по email и паролю.",
}


def _client_ip(request: Request):
    return request.client.host if request.client else None


def _context(request: Request, *, session_id_hash=None):
    return build_request_context(
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        session_id_hash=session_id_hash,
    )


def _auth_method(provider: Optional[str]) -> Optional[AuthMethod]:
    """Имя провайдера → AuthMethod. provider приходит ТОЛЬКО из сервиса (имя
    зарегистрированного адаптера или провайдер списанного ticket), никогда из
    сырого path-параметра. None — способ авторитетно не установлен."""
    return AuthMethod(provider) if provider is not None else None


def _audit_failed_login(
    request: Request, audit_code: str, provider: Optional[str],
) -> None:
    """failed_login (AUTH_LOG, INDEPENDENT/SOFT). Без email, state, ticket,
    code, токенов и текста провайдера."""
    record_event(
        event="failed_login",
        actor=Actor.anonymous(),
        outcome=Outcome.FAILURE,
        failure_reason_code=audit_code,
        auth_method=_auth_method(provider),
        context=_context(request),
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _delete_state_cookie(response: Response) -> None:
    response.delete_cookie(
        service.STATE_COOKIE_NAME,
        path=service.STATE_COOKIE_PATH,
        secure=service.state_cookie_secure(),
        httponly=True,
        samesite="lax",
    )


def _set_registration_cookie(response: Response, ticket: str, expires_at) -> None:
    """Raw registration-ticket в HttpOnly cookie продолжения регистрации.
    Max-Age — не больше оставшегося срока ticket; путь — только API
    регистрации через провайдера; SameSite=Strict — межсайтовые запросы
    cookie не получают."""
    remaining = int((expires_at - service._now()).total_seconds())
    if remaining <= 0:
        return
    response.set_cookie(
        service.REGISTRATION_COOKIE_NAME,
        ticket,
        max_age=remaining,
        path=service.REGISTRATION_COOKIE_PATH,
        secure=service.state_cookie_secure(),
        httponly=True,
        samesite="strict",
    )


def _delete_registration_cookie(response: Response) -> None:
    response.delete_cookie(
        service.REGISTRATION_COOKIE_NAME,
        path=service.REGISTRATION_COOKIE_PATH,
        secure=service.state_cookie_secure(),
        httponly=True,
        samesite="strict",
    )


def _frontend_redirect(
    fragment, *, clear_cookie: bool, registration_ticket=None, registration_expires_at=None,
) -> RedirectResponse:
    """Только фиксированный адрес из конфига + фиксированные коды во fragment."""
    url = f"{settings.OAUTH_FRONTEND_CALLBACK_URL}#{urlencode(dict(fragment))}"
    response = RedirectResponse(url, status_code=302)
    response.headers["Referrer-Policy"] = "no-referrer"
    _no_store(response)
    if clear_cookie:
        _delete_state_cookie(response)
    if registration_ticket is not None and registration_expires_at is not None:
        _set_registration_cookie(response, registration_ticket, registration_expires_at)
    return response


@router.post("/{provider}/start", response_model=OAuthStartResponse)
def oauth_start(provider: str, request: Request, response: Response):
    # intent не принимается: Stage 2B создаёт только login-запрос (link — отдельный
    # будущий путь с проверкой сессии).
    try:
        enforce_rate_limit("oauth_start", ip=_client_ip(request))
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail=_RATE_LIMIT_MESSAGE)
    try:
        result = service.start_login(provider)
    except OAuthProviderUnavailableError:
        return JSONResponse(
            status_code=404,
            content={
                "detail": _PROVIDER_UNAVAILABLE_MESSAGE,
                "code": "oauth_provider_unavailable",
            },
        )
    response.set_cookie(
        service.STATE_COOKIE_NAME,
        result.state,
        max_age=service.STATE_COOKIE_MAX_AGE,
        path=service.STATE_COOKIE_PATH,
        secure=service.state_cookie_secure(),
        httponly=True,
        samesite="lax",
    )
    _no_store(response)
    return {"authorize_url": result.authorize_url}


@router.get("/{provider}/callback")
def oauth_callback(provider: str, request: Request):
    try:
        enforce_rate_limit("oauth_callback", ip=_client_ip(request))
    except RateLimitExceeded:
        return _frontend_redirect({"error": service.ERROR_FAILED}, clear_cookie=False)

    outcome = service.handle_callback(
        provider,
        dict(request.query_params),
        request.cookies.get(service.STATE_COOKIE_NAME),
    )
    if outcome.audit_code:
        _audit_failed_login(request, outcome.audit_code, outcome.provider)
    return _frontend_redirect(
        outcome.fragment, clear_cookie=outcome.clear_cookie,
        registration_ticket=outcome.registration_ticket,
        registration_expires_at=outcome.registration_expires_at,
    )


@router.post("/complete", response_model=SessionResponse)
def oauth_complete(body: OAuthCompleteRequest, request: Request, response: Response):
    try:
        enforce_rate_limit("oauth_complete", ip=_client_ip(request))
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail=_RATE_LIMIT_MESSAGE)

    try:
        result = service.complete_login(
            body.ticket,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except OAuthTicketInvalidError as exc:
        # Ticket не найден/списан/истёк — провайдер не установлен → NULL.
        _audit_failed_login(request, exc.audit_code, None)
        return JSONResponse(
            status_code=400,
            content={"detail": _TICKET_INVALID_MESSAGE, "code": "oauth_ticket_invalid"},
        )
    except OAuthLoginDenied as denial:
        _audit_failed_login(request, denial.audit_code, denial.provider)
        code = denial.external_code
        return JSONResponse(
            status_code=403, content={"detail": _DENIED_MESSAGES[code], "code": code},
        )

    user = result.user
    # Существующее событие login (как у входа по паролю), после commit сессии.
    record_event(
        event="login",
        actor=Actor.user(int(user["id"]), user["role"]),
        outcome=Outcome.SUCCESS,
        user_email=user["email"],
        auth_method=_auth_method(result.provider),
        context=_context(
            request, session_id_hash=hash_session_token(result.session_token),
        ),
    )
    _no_store(response)
    return {
        "session_token": result.session_token,
        "expires_at": result.expires_at,
        "roles": user["roles"],
        "role": user["role"],
    }


# ── регистрация через провайдера (Stage Social Auth 4) ───────────────────────

def _registration_error_response(exc: OAuthRegistrationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


def _ticket_invalid_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": _TICKET_INVALID_MESSAGE, "code": "oauth_ticket_invalid"},
    )


def _rate_limited_response() -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": _RATE_LIMIT_MESSAGE, "code": "rate_limited"},
    )


class _TicketSourceConflict(Exception):
    """ticket в теле и в cookie продолжения различаются."""


def _cookie_ticket(request: Request) -> Optional[str]:
    raw = request.cookies.get(service.REGISTRATION_COOKIE_NAME)
    if not raw or len(raw) > 128:
        return None
    return raw


def _registration_ticket(request: Request, body_ticket: Optional[str]):
    """(ticket, from_cookie). Источник — тело (поток в памяти вкладки) или
    HttpOnly cookie продолжения из письма. Оба сразу допустимы, только если
    это один и тот же ticket (браузер шлёт cookie и вкладке, начавшей
    регистрацию); различаются — _TicketSourceConflict (fail closed: какой из
    двух потоков актуален, сервер не угадывает)."""
    cookie = _cookie_ticket(request)
    if body_ticket is not None and cookie is not None:
        if not constant_time_equals(body_ticket, cookie):
            raise _TicketSourceConflict()
        return body_ticket, True
    if body_ticket is not None:
        return body_ticket, False
    if cookie is not None:
        return cookie, True
    return None, False


def _not_found_response() -> JSONResponse:
    """Ни тела, ни cookie: ничего о регистрации не раскрывается."""
    return JSONResponse(
        status_code=400,
        content={"detail": _REGISTRATION_NOT_FOUND_MESSAGE, "code": "oauth_registration_not_found"},
    )


def _conflict_response() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": _REGISTRATION_CONFLICT_MESSAGE,
            "code": "oauth_registration_ticket_conflict",
        },
    )


def _drop_dead_cookie(response: Response, ticket: Optional[str], from_cookie: bool) -> Response:
    """Отказ по ticket из cookie: если ticket больше не жив (истёк, списан,
    сожжён), бесполезная cookie удаляется. Живой ticket (исправимая ошибка:
    неверный код, cooldown) cookie сохраняет."""
    if from_cookie and not service.registration_ticket_alive(ticket):
        _delete_registration_cookie(response)
    return response


def _audit_registration_failed(
    request: Request, audit_code: str, provider: Optional[str],
    email: Optional[str] = None,
) -> None:
    """registration_failed (AUTH_LOG, INDEPENDENT/SOFT). Без ticket, OTP,
    subject, имени и текста провайдера; email — только из ticket."""
    record_event(
        event="registration_failed",
        actor=Actor.anonymous(),
        outcome=Outcome.FAILURE,
        failure_reason_code=audit_code,
        user_email=email,
        auth_method=_auth_method(provider),
        context=_context(request),
    )


@router.post("/registration/preview", response_model=OAuthRegistrationPreviewResponse)
def oauth_registration_preview(
    body: OAuthRegistrationPreviewRequest, request: Request, response: Response,
):
    """Шаг email регистрации: провайдер, МАСКИРОВАННЫЙ адрес ticket и можно ли с
    ним продолжить. Ничего не меняет: ticket не списывается, код не уходит."""
    try:
        ticket, from_cookie = _registration_ticket(request, body.ticket)
    except _TicketSourceConflict:
        return _conflict_response()
    try:
        enforce_rate_limit(
            "oauth_registration_preview", ip=_client_ip(request),
            ticket_digest=sha256_hex(ticket) if ticket else None,
        )
    except RateLimitExceeded:
        return _rate_limited_response()
    if ticket is None:
        return _not_found_response()
    try:
        preview = service.registration_preview(ticket)
    except OAuthTicketInvalidError:
        return _drop_dead_cookie(_ticket_invalid_response(), ticket, from_cookie)
    _no_store(response)
    return preview


@router.post("/registration/resume", response_model=OAuthRegistrationResumeResponse)
def oauth_registration_resume(
    body: OAuthRegistrationResumeRequest, request: Request, response: Response,
):
    """Продолжение регистрации из письма (/register/social): ticket ТОЛЬКО из
    HttpOnly cookie этого браузера. Только чтение: ticket не списывается и не
    продлевается, код не отправляется, email не меняется."""
    ticket = _cookie_ticket(request)
    try:
        enforce_rate_limit(
            "oauth_registration_resume", ip=_client_ip(request),
            ticket_digest=sha256_hex(ticket) if ticket else None,
        )
    except RateLimitExceeded:
        return _rate_limited_response()
    if ticket is None:
        return _not_found_response()
    try:
        state = service.registration_resume(ticket)
    except OAuthTicketInvalidError:
        return _drop_dead_cookie(_ticket_invalid_response(), ticket, True)
    _no_store(response)
    return state


@router.post("/registration/init", response_model=OAuthRegistrationInitResponse)
def oauth_registration_init(body: OAuthRegistrationInitRequest, request: Request):
    """registration-ticket → OTP на email ticket. Без `email` — на уже привязанный
    адрес (повторная отправка, cooldown 60 с). С `email` (только VK) — адрес
    выбирает пользователь: allowlist, занятость, привязка к ticket и код на
    него. Отказы init не аудируются (как и у /auth/register/init)."""
    # Выбор адреса — отдельный лимит: исправимые отказы (домен, занятый email)
    # не должны съедать квоту повторной отправки, а чужой ящик защищён лимитом
    # по самому адресу.
    action = (
        "oauth_registration_init" if body.email is None else "oauth_registration_email"
    )
    try:
        ticket, from_cookie = _registration_ticket(request, body.ticket)
    except _TicketSourceConflict:
        return _conflict_response()
    try:
        enforce_rate_limit(
            action, ip=_client_ip(request), email=body.email,
            # Только SHA-256 digest: raw ticket в ключи лимитера не попадает.
            ticket_digest=sha256_hex(ticket) if ticket else None,
        )
    except RateLimitExceeded:
        return _rate_limited_response()
    if ticket is None:
        return _not_found_response()

    try:
        email_masked = service.registration_init(ticket, body.email)
    except OAuthTicketInvalidError:
        return _drop_dead_cookie(_ticket_invalid_response(), ticket, from_cookie)
    except OAuthRegistrationError as exc:
        return _drop_dead_cookie(_registration_error_response(exc), ticket, from_cookie)
    return {
        "message": "Код подтверждения отправлен на email",
        "email_masked": email_masked,
    }


@router.post("/registration/confirm", response_model=SessionResponse)
def oauth_registration_confirm(
    body: OAuthRegistrationConfirmRequest, request: Request, response: Response,
):
    """ticket + OTP + согласие MindCare → аккаунт без пароля + identity +
    обычная сессия MindCare."""
    try:
        ticket, from_cookie = _registration_ticket(request, body.ticket)
    except _TicketSourceConflict:
        return _conflict_response()
    try:
        enforce_rate_limit(
            "oauth_registration_confirm", ip=_client_ip(request),
            # Только SHA-256 digest: raw ticket в ключи лимитера не попадает.
            ticket_digest=sha256_hex(ticket) if ticket else None,
        )
    except RateLimitExceeded:
        return _rate_limited_response()
    if ticket is None:
        return _not_found_response()

    try:
        result = service.registration_confirm(
            ticket, body.code,
            consent_accepted=body.consent_accepted,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except OAuthTicketInvalidError as exc:
        # Ticket не найден/списан/истёк/не привязан — провайдер не установлен.
        _audit_registration_failed(request, exc.audit_code, None)
        return _drop_dead_cookie(_ticket_invalid_response(), ticket, from_cookie)
    except OAuthRegistrationError as exc:
        if exc.audit_code:
            _audit_registration_failed(request, exc.audit_code, exc.provider, exc.email)
        return _drop_dead_cookie(_registration_error_response(exc), ticket, from_cookie)

    user = result.user
    auth_method = _auth_method(result.provider)
    record_event(
        event="registration_succeeded",
        actor=Actor.user(int(user["id"]), "student"),
        outcome=Outcome.SUCCESS,
        user_email=user["email"],
        auth_method=auth_method,
        context=_context(request),
    )
    # Регистрация сразу создаёт сессию — это и первый вход.
    record_event(
        event="login",
        actor=Actor.user(int(user["id"]), user["role"]),
        outcome=Outcome.SUCCESS,
        user_email=user["email"],
        auth_method=auth_method,
        context=_context(
            request, session_id_hash=hash_session_token(result.session_token),
        ),
    )
    _no_store(response)
    # Регистрация завершена: ticket списан — cookie продолжения больше не нужна.
    # Удаляется всегда (и при ticket из тела): cookie этого браузера относилась
    # к этому же ticket (иначе был бы 409 выше) либо отсутствовала.
    _delete_registration_cookie(response)
    return {
        "session_token": result.session_token,
        "expires_at": result.expires_at,
        "roles": user["roles"],
        "role": user["role"],
    }
