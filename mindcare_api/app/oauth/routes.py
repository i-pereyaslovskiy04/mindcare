"""
/api/auth/oauth/* — social login core (Stage Social Auth 2B).

  POST /{provider}/start    → {authorize_url} + HttpOnly state-cookie
  GET  /{provider}/callback → 302 на OAUTH_FRONTEND_CALLBACK_URL#...
  POST /complete            → SessionResponse (тот же, что у входа по паролю)

Ошибки OAuth-потока — 400/403/404/429, НЕ 401: frontend client.js трактует
любой 401 как истёкшую сессию. Callback всегда отвечает redirect (это
навигация браузера), результат — во fragment: он не уходит на сервер, в access
log и Referer. Session token в URL не попадает никогда.
"""
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from app.audit import Actor, Outcome, record_event
from app.audit.request_context import build_request_context
from app.auth.schemas import SessionResponse
from app.auth.security import hash_session_token
from app.core.config import settings
from app.core.rate_limit import RateLimitExceeded, enforce as enforce_rate_limit
from app.oauth import service
from app.oauth.errors import (
    OAuthLoginDenied, OAuthProviderUnavailableError, OAuthTicketInvalidError,
)
from app.oauth.schemas import OAuthCompleteRequest, OAuthStartResponse

router = APIRouter(prefix="/auth/oauth", tags=["auth"])

_RATE_LIMIT_MESSAGE = "Слишком много попыток. Попробуйте позже."
_PROVIDER_UNAVAILABLE_MESSAGE = "Вход через этот сервис недоступен."
_TICKET_INVALID_MESSAGE = (
    "Ссылка для входа недействительна или устарела. Начните вход заново."
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


def _audit_failed_login(request: Request, audit_code: str) -> None:
    """failed_login (AUTH_LOG, INDEPENDENT/SOFT). Без email, state, ticket,
    code, токенов и текста провайдера."""
    record_event(
        event="failed_login",
        actor=Actor.anonymous(),
        outcome=Outcome.FAILURE,
        failure_reason_code=audit_code,
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


def _frontend_redirect(fragment, *, clear_cookie: bool) -> RedirectResponse:
    """Только фиксированный адрес из конфига + фиксированные коды во fragment."""
    url = f"{settings.OAUTH_FRONTEND_CALLBACK_URL}#{urlencode(dict(fragment))}"
    response = RedirectResponse(url, status_code=302)
    response.headers["Referrer-Policy"] = "no-referrer"
    _no_store(response)
    if clear_cookie:
        _delete_state_cookie(response)
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
        _audit_failed_login(request, outcome.audit_code)
    return _frontend_redirect(outcome.fragment, clear_cookie=outcome.clear_cookie)


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
        _audit_failed_login(request, exc.audit_code)
        return JSONResponse(
            status_code=400,
            content={"detail": _TICKET_INVALID_MESSAGE, "code": "oauth_ticket_invalid"},
        )
    except OAuthLoginDenied as denial:
        _audit_failed_login(request, denial.audit_code)
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
