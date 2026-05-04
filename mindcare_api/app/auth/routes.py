from fastapi import APIRouter, HTTPException, Depends

from app.auth.schemas import (
    RegisterRequest,
    RegisterInitRequest,
    RegisterConfirmRequest,
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    AccessTokenResponse,
    RefreshResponse,
    LogoutRequest,
    UserResponse,
    MessageResponse,
    PasswordResetInitRequest,
    PasswordResetConfirmRequest,
)
from app.auth import service
from app.auth.security import create_access_token, create_refresh_token
from app.auth.deps import get_current_user

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


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    try:
        user = service.authenticate_user(email=body.email, password=body.password)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    access_token = create_access_token(user["id"], user["role"])
    refresh_token = create_refresh_token()
    service.save_refresh_token(refresh_token, user["id"])

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "role": user["role"],
    }


@router.post("/refresh", response_model=RefreshResponse)
def refresh(body: RefreshRequest):
    try:
        user_id, new_refresh_token = service.rotate_refresh_token(body.refresh_token)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    user = service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "access_token": create_access_token(user["id"], user["role"]),
        "refresh_token": new_refresh_token,
    }


@router.post("/logout", response_model=MessageResponse)
def logout(body: LogoutRequest):
    service.revoke_refresh_token(body.refresh_token)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "name": current_user["name"],
        "role": current_user["role"],
    }


@router.post("/password/reset/init", response_model=MessageResponse)
def password_reset_init(body: PasswordResetInitRequest):
    try:
        service.password_reset_init(email=body.email)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    # Always return the same message — do not reveal whether email is registered.
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
