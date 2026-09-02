import ipaddress

from fastapi import APIRouter, HTTPException, Depends, Request

from app.core.rate_limit import RateLimitExceeded, enforce as enforce_rate_limit
from app.auth.schemas import (
    RegisterInitRequest,
    RegisterConfirmRequest,
    LoginRequest,
    SessionResponse,
    UserResponse,
    MessageResponse,
    PasswordResetInitRequest,
    PasswordResetConfirmRequest,
    ChangePasswordRequest,
    ProfileRead,
    ProfileUpdate,
)
from app.auth import service
from app.auth.deps import get_current_user, get_session_token
from app.auth.security import hash_session_token
from app.audit import record_event, Actor, Outcome, RequestContext
from app.audit.failsafe import record_secondary_failure

router = APIRouter(prefix="/auth", tags=["auth"])

_RATE_LIMIT_MESSAGE = "Слишком много попыток. Попробуйте позже."


def _check_rate_limit(action: str, request: Request, email: str | None = None) -> None:
    """
    Лимит по IP и нормализованному email. При превышении — 429 с единым
    сообщением, не раскрывающим существование email.
    """
    ip = request.client.host if request.client else None
    try:
        enforce_rate_limit(action, email=email, ip=ip)
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail=_RATE_LIMIT_MESSAGE)


# Единый безопасный audit-контекст. Недоверенные optional IP/User-Agent приходят
# из заголовков клиента: невалидное значение НЕ должно ломать уже успешную
# бизнес-операцию (facade validate_context бросил бы AuditError → 500 после
# смены пароля/создания сессии). Санитизируем ДО передачи facade: невалидное →
# None (не попадает в журнал), строгую валидацию record_event НЕ ослабляем.
# Исходное значение нигде не печатаем. session_id_hash пробрасываем как есть
# (raw token сюда никогда не передаётся).
_UA_MAX_LEN = 512


def _safe_user_agent(user_agent) -> str | None:
    if not isinstance(user_agent, str):
        return None
    if len(user_agent) > _UA_MAX_LEN:
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in user_agent):
        return None
    return user_agent


def _safe_ip(ip) -> str | None:
    if not isinstance(ip, str):
        return None
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


def _audit_context(
    request: Request, *, session_id_hash: str | None = None
) -> RequestContext:
    ip = request.client.host if request.client else None
    return RequestContext(
        ip_address=_safe_ip(ip),
        user_agent=_safe_user_agent(request.headers.get("user-agent")),
        session_id_hash=session_id_hash,
    )


@router.post("/register/init", response_model=MessageResponse)
def register_init(body: RegisterInitRequest, request: Request):
    _check_rate_limit("register_init", request, email=body.email)
    try:
        service.register_init(name=body.name, email=body.email, password=body.password)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"message": "Код подтверждения отправлен на email"}


@router.post("/register/confirm", response_model=MessageResponse, status_code=201)
def register_confirm(body: RegisterConfirmRequest, request: Request):
    _check_rate_limit("confirm", request, email=body.email)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        user = service.register_confirm(
            email=body.email,
            code=body.code,
            ip=ip,
            user_agent=user_agent,
        )
    except service.AuthError as e:
        record_event(
            event="registration_failed",
            actor=Actor.anonymous(),
            outcome=Outcome.FAILURE,
            failure_reason_code=e.audit_code,
            user_email=body.email,
            context=_audit_context(request),
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    record_event(
        event="registration_succeeded",
        actor=Actor.user(int(user["id"]), "student"),
        outcome=Outcome.SUCCESS,
        user_email=user["email"],
        context=_audit_context(request),
    )
    return {"message": "Регистрация завершена"}


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, request: Request):
    _check_rate_limit("login", request, email=body.email)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        user = service.authenticate_user(email=body.email, password=body.password)
    except service.AuthError as e:
        record_event(
            event="failed_login",
            actor=Actor.anonymous(),
            outcome=Outcome.FAILURE,
            failure_reason_code=e.audit_code,
            user_email=body.email,
            context=_audit_context(request),
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)

    session_token, expires_at = service.create_session(
        user_id=user["id"],
        ip=ip,
        user_agent=user_agent,
    )

    record_event(
        event="login",
        actor=Actor.user(int(user["id"]), user["role"]),
        outcome=Outcome.SUCCESS,
        user_email=user["email"],
        # session_id_hash (не raw token): совпадает с user_sessions.id,
        # join для расследований работает, credential в лог не утекает.
        context=_audit_context(
            request, session_id_hash=hash_session_token(session_token)
        ),
    )

    return {
        "session_token": session_token,
        "expires_at":    expires_at,
        "roles":         user["roles"],
        "role":          user["role"],
    }


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    token: str = Depends(get_session_token),
    current_user: dict = Depends(get_current_user),
):
    service.terminate_session(token)
    record_event(
        event="logout",
        actor=Actor.user(int(current_user["id"]), current_user["role"]),
        outcome=Outcome.SUCCESS,
        # user_email НЕ передаётся: субъект известен по user_id.
        context=_audit_context(
            request, session_id_hash=hash_session_token(token)
        ),
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    impersonator_id = current_user.get("impersonator_user_id")
    return {
        "id":    current_user["id"],
        "email": current_user["email"],
        "name":  current_user["name"],
        "roles": current_user["roles"],
        "role":  current_user["role"],
        "impersonating":     impersonator_id is not None,
        "impersonator_name": current_user.get("impersonator_name"),
    }


@router.get("/profile", response_model=ProfileRead)
def get_profile(current_user: dict = Depends(get_current_user)):
    try:
        return service.get_profile(current_user["id"])
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch("/profile", response_model=ProfileRead)
def update_profile(
    body: ProfileUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    # PATCH-семантика: меняем только реально пришедшие поля (unset ≠ None).
    # ФИО/телефон НЕ логируются — profile_updated (record_event) пишется
    # внутри storage.update_profile_atomic, атомарно с мутацией, только если
    # хотя бы одно аудируемое поле реально изменилось (Stage 4B-4).
    actor = Actor.user(int(current_user["id"]), current_user["role"])
    try:
        profile = service.update_profile(
            user_id=current_user["id"],
            fields=body.model_dump(exclude_unset=True),
            actor_role=current_user["role"],
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.AuthError as e:
        # Stage 5A-2 durable best-effort failure audit (INDEPENDENT/SOFT);
        # НЕ меняет исходный HTTP-ответ. Только этот self-profile endpoint.
        record_secondary_failure(
            event="profile_update_failed", actor=actor,
            failure_reason_code=e.audit_code,
            context=_audit_context(request),
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return profile


@router.post("/password/reset/init", response_model=MessageResponse)
def password_reset_init(body: PasswordResetInitRequest, request: Request):
    # Лимит считается по запросам, а не по существованию аккаунта:
    # 429 для незарегистрированного email выглядит так же, как для живого.
    _check_rate_limit("reset_init", request, email=body.email)
    try:
        service.password_reset_init(email=body.email)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"message": "Если аккаунт с таким email существует, код отправлен на него"}


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    try:
        service.change_password(
            user_id=current_user["id"],
            current_password=body.current_password,
            new_password=body.new_password,
            new_password_confirm=body.new_password_confirm,
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    record_event(
        event="password_change",
        actor=Actor.user(int(current_user["id"]), current_user["role"]),
        outcome=Outcome.SUCCESS,
        # user_email НЕ передаётся: субъект известен по user_id.
        context=_audit_context(request),
    )
    return {"message": "Пароль изменён. Войдите снова."}


@router.post("/password/reset/confirm", response_model=MessageResponse)
def password_reset_confirm(body: PasswordResetConfirmRequest, request: Request):
    _check_rate_limit("confirm", request, email=body.email)
    try:
        service.password_reset_confirm(
            email=body.email,
            code=body.code,
            new_password=body.new_password,
        )
    except service.AuthError as e:
        record_event(
            event="password_reset",
            actor=Actor.anonymous(),
            outcome=Outcome.FAILURE,
            failure_reason_code=e.audit_code,
            user_email=body.email,
            context=_audit_context(request),
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    record_event(
        event="password_reset",
        actor=Actor.anonymous(),
        outcome=Outcome.SUCCESS,
        user_email=body.email,
        context=_audit_context(request),
    )
    return {"message": "Пароль успешно изменён. Войдите с новым паролем"}
