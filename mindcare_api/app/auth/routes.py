from fastapi import APIRouter, HTTPException, Depends, Request

from app.auth.schemas import (
    RegisterRequest,
    RegisterInitRequest,
    RegisterConfirmRequest,
    LoginRequest,
    SessionResponse,
    UserResponse,
    MessageResponse,
    PasswordResetInitRequest,
    PasswordResetConfirmRequest,
)
from app.auth import service
from app.auth.deps import get_current_user, get_session_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=MessageResponse, status_code=201)
def register(body: RegisterRequest):
    try:
        service.register_user(name=body.name, email=body.email, password=body.password)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"message": "Registration successful"}


@router.post("/register/init", response_model=MessageResponse)
def register_init(body: RegisterInitRequest):
    try:
        service.register_init(name=body.name, email=body.email, password=body.password)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"message": "Код подтверждения отправлен на email"}


@router.post("/register/confirm", response_model=MessageResponse, status_code=201)
def register_confirm(body: RegisterConfirmRequest):
    try:
        service.register_confirm(email=body.email, code=body.code)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"message": "Регистрация завершена"}


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, request: Request):
    try:
        user = service.authenticate_user(email=body.email, password=body.password)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    session_token, expires_at = service.create_session(
        user_id=user["id"],
        ip=ip,
        user_agent=user_agent,
    )

    return {
        "session_token": session_token,
        "expires_at":    expires_at,
        "role":          user["role"],
    }


@router.post("/logout", response_model=MessageResponse)
def logout(token: str = Depends(get_session_token)):
    service.terminate_session(token)
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
def password_reset_init(body: PasswordResetInitRequest):
    try:
        service.password_reset_init(email=body.email)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"message": "Если аккаунт с таким email существует, код отправлен на него"}


@router.post("/password/reset/confirm", response_model=MessageResponse)
def password_reset_confirm(body: PasswordResetConfirmRequest):
    try:
        service.password_reset_confirm(
            email=body.email,
            code=body.code,
            new_password=body.new_password,
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"message": "Пароль успешно изменён. Войдите с новым паролем"}
