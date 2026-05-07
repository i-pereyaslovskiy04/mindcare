"""
Business logic layer — no FastAPI, no HTTP concepts.
Depends only on storage and bcrypt. Safe to unit-test in isolation.
"""

from datetime import datetime
from typing import Optional

import bcrypt
from app.auth import storage


def _hash(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Регистрация
# ---------------------------------------------------------------------------
# говорит что это лишнее так как есть register_init и register_confirm
# def register_user(name: str, email: str, password: str) -> dict:
#     if not name or len(name.strip()) < 2:
#         raise AuthError("Name must be at least 2 characters", 422)
#     if len(password) < 8:
#         raise AuthError("Password must be at least 8 characters", 422)
#     if storage.find_user_by_email(email):
#         raise AuthError("Email already registered", 409)

#     return storage.save_user({
#         "name":            name.strip(),
#         "email":           email,
#         "hashed_password": _hash(password),
#         "role":            "student",
#     })


def register_init(name: str, email: str, password: str) -> None:
    """Валидация данных → OTP в БД → отправка письма."""
    if not name or len(name.strip()) < 2:
        raise AuthError("Name must be at least 2 characters", 422)
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters", 422)
    if storage.find_user_by_email(email):
        raise AuthError("Email already registered", 409)

    from app.auth import otp_service
    from app.services.email_service import send_registration_otp

    password_hash = _hash(password)
    try:
        code = otp_service.create_or_update_otp(email, name.strip(), password_hash)
    except ValueError as e:
        raise AuthError(str(e), 429)

    print(f"[register_init] sending OTP to {email}")
    try:
        send_registration_otp(email, code)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise AuthError(f"Не удалось отправить письмо: {type(e).__name__}: {e}", 500)

REQUIRED_CONSENTS = ["privacy_policy", "data_processing"]
# Как было
#def register_confirm(email: str, code: str) -> dict:
#    """Проверяет OTP и создаёт пользователя."""
#    from app.auth import otp_service
#
#    try:
#        user_data = otp_service.verify_otp(email, code)
#    except ValueError as e:
#        raise AuthError(str(e), 400)
#
#    return storage.save_user({
#        "name":            user_data["name"],
#        "email":           email,
#        "hashed_password": user_data["password_hash"],
#        "role":            "student",
#    })


def register_confirm(
    email: str,
    code: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """Проверяет OTP, создаёт пользователя и записывает согласия на ПДн."""
    from app.auth import otp_service

    try:
        user_data = otp_service.verify_otp(email, code)
    except ValueError as e:
        raise AuthError(str(e), 400)

    # Проверяем что в БД есть актуальные политики до создания юзера
    consent_ids = {}
    for policy_type in REQUIRED_CONSENTS:
        cid = storage.get_active_consent_id(policy_type)
        if cid is None:
            raise AuthError(
                f"Политика '{policy_type}' не найдена в БД. Обратитесь к администратору.",
                500,
            )
        consent_ids[policy_type] = cid

    user = storage.save_user({
        "name":            user_data["name"],
        "email":           email,
        "hashed_password": user_data["password_hash"],
        "role":            "student",
    })

    # Записываем согласия
    for cid in consent_ids.values():
        storage.save_consent_record(
            user_id=int(user["id"]),
            consent_id=cid,
            ip=ip,
            user_agent=user_agent,
        )

    return user

# ---------------------------------------------------------------------------
# Аутентификация
# ---------------------------------------------------------------------------

def authenticate_user(email: str, password: str) -> dict:
    user = storage.find_user_by_email(email)
    if not user or not _verify(password, user["hashed_password"]):
        raise AuthError("Invalid email or password", 401)
    storage.update_last_login(user["id"])
    return user


def get_user_by_id(user_id: str) -> Optional[dict]:
    return storage.find_user_by_id(user_id)


# ---------------------------------------------------------------------------
# Сброс пароля
# ---------------------------------------------------------------------------

def password_reset_init(email: str) -> None:
    """Отправляет OTP для сброса пароля. Возвращает молча если email не найден."""
    from app.auth import otp_service
    from app.services.email_service import send_password_reset_otp

    user = storage.find_user_by_email(email)
    if not user:
        return  # не раскрываем, есть ли такой email

    try:
        code = otp_service.create_or_update_otp(
            email=email,
            name=user["name"],
            password_hash=user["hashed_password"],
        )
    except ValueError as e:
        raise AuthError(str(e), 429)

    try:
        send_password_reset_otp(email, code)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise AuthError(f"Не удалось отправить письмо: {type(e).__name__}: {e}", 500)


def password_reset_confirm(email: str, code: str, new_password: str) -> None:
    """Проверяет OTP, обновляет пароль, отзывает все сессии пользователя."""
    if len(new_password) < 8:
        raise AuthError("Password must be at least 8 characters", 422)

    from app.auth import otp_service

    try:
        otp_service.verify_otp(email, code)
    except ValueError as e:
        raise AuthError(str(e), 400)

    user = storage.find_user_by_email(email)
    if not user:
        raise AuthError("Пользователь не найден", 404)

    storage.update_user_password(user["id"], _hash(new_password))
    storage.revoke_all_user_sessions(user["id"])  # инвалидируем все сессии после смены пароля


# ---------------------------------------------------------------------------
# Сессии
# ---------------------------------------------------------------------------

def create_session(
    user_id: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[str, datetime]:
    """Создаёт сессию, возвращает (session_token, expires_at)."""
    return storage.create_session(user_id, ip=ip, user_agent=user_agent)


def terminate_session(token: str) -> None:
    """Отзывает сессию (logout)."""
    storage.revoke_session(token)
