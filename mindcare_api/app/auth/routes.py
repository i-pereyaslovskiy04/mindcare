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
)
from app.auth import service, audit
from app.auth.deps import get_current_user, get_session_token
from app.auth.security import hash_session_token

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
        audit.log_auth_event(
            event="register",
            success=False,
            user_email=body.email,
            failure_reason=e.message[:255],
            ip_address=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    audit.log_auth_event(
        event="register",
        success=True,
        user_id=int(user["id"]),
        user_email=user["email"],
        ip_address=ip,
        user_agent=user_agent,
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
        audit.log_auth_event(
            event="failed_login",
            success=False,
            user_email=body.email,
            failure_reason=e.message[:255],
            ip_address=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)

    session_token, expires_at = service.create_session(
        user_id=user["id"],
        ip=ip,
        user_agent=user_agent,
    )

    audit.log_auth_event(
        event="login",
        success=True,
        user_id=int(user["id"]),
        user_email=user["email"],
        ip_address=ip,
        user_agent=user_agent,
        # В audit пишем hash, не raw token: совпадает с user_sessions.id,
        # join для расследований работает, credential в лог не утекает.
        session_id=hash_session_token(session_token),
    )

    return {
        "session_token": session_token,
        "expires_at":    expires_at,
        "role":          user["role"],
    }


@router.post("/logout", response_model=MessageResponse)
def logout(
    request: Request,
    token: str = Depends(get_session_token),
    current_user: dict = Depends(get_current_user),
):
    service.terminate_session(token)
    audit.log_auth_event(
        event="logout",
        success=True,
        user_id=int(current_user["id"]),
        user_email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        session_id=hash_session_token(token),
    )
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return {
        "id":    current_user["id"],
        "email": current_user["email"],
        "name":  current_user["name"],
        "role":  current_user["role"],
    }


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
    audit.log_auth_event(
        event="password_change",
        success=True,
        user_id=int(current_user["id"]),
        user_email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"message": "Пароль изменён. Войдите снова."}


@router.post("/password/reset/confirm", response_model=MessageResponse)
def password_reset_confirm(body: PasswordResetConfirmRequest, request: Request):
    _check_rate_limit("confirm", request, email=body.email)
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    try:
        service.password_reset_confirm(
            email=body.email,
            code=body.code,
            new_password=body.new_password,
        )
    except service.AuthError as e:
        audit.log_auth_event(
            event="password_reset",
            success=False,
            user_email=body.email,
            failure_reason=e.message[:255],
            ip_address=ip,
            user_agent=user_agent,
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    audit.log_auth_event(
        event="password_reset",
        success=True,
        user_email=body.email,
        ip_address=ip,
        user_agent=user_agent,
    )
    return {"message": "Пароль успешно изменён. Войдите с новым паролем"}
