from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError

from app.schemas.user import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.core.security import verify_password, create_access_token, decode_token
from app.data.fake_db import get_user_by_email, get_user_by_id, create_user

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer()


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    try:
        payload = decode_token(credentials.credentials)
        user_id: int = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невалидный токен")

    user = get_user_by_id(int(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Пользователь не найден")
    return user


def require_role(*roles: str):
    def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Нет доступа")
        return current_user
    return dependency


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    try:
        user = create_user(email=body.email, password=body.password, name=body.name)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    token = create_access_token({"sub": str(user["id"]), "role": user["role"]})
    return TokenResponse(
        access_token=token,
        user=UserResponse(**{k: user[k] for k in ("id", "email", "name", "role")}),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль")

    token = create_access_token({"sub": str(user["id"]), "role": user["role"]})
    return TokenResponse(
        access_token=token,
        user=UserResponse(**{k: user[k] for k in ("id", "email", "name", "role")}),
    )


@router.get("/me", response_model=UserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(**{k: current_user[k] for k in ("id", "email", "name", "role")})
