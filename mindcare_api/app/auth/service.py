"""
Business logic layer — no FastAPI, no HTTP concepts.
Depends only on storage and bcrypt. Safe to unit-test in isolation.
"""

import logging
from datetime import datetime
from typing import Optional

import bcrypt
from app.auth import storage
from app.core.normalization import mask_email

log = logging.getLogger(__name__)

# Стабильное сообщение клиенту при сбое доставки письма: не раскрывает
# SMTP host/user/stack/internal exception. Детали — только в server-side логах.
_EMAIL_SEND_FAILED_MESSAGE = "Не удалось отправить письмо. Попробуйте позже."


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

REQUIRED_CONSENTS = ["privacy_policy", "data_processing"]


def register_init(name: str, email: str, password: str) -> None:
    """Валидация данных -> OTP в БД -> отправка письма."""
    if not name or len(name.strip()) < 2:
        raise AuthError("Имя должно содержать не менее 2 символов", 422)
    if len(password) < 8:
        raise AuthError("Пароль должен быть не короче 8 символов", 422)
    if storage.find_user_by_email(email):
        raise AuthError("Email уже зарегистрирован", 409)

    from app.auth import otp_service
    from app.services.email_service import send_registration_otp

    password_hash = _hash(password)
    try:
        code = otp_service.create_or_update_otp(
            email, name.strip(), password_hash
        )
    except ValueError as e:
        raise AuthError(str(e), 429)

    log.info("[register_init] sending OTP to %s", mask_email(email))
    try:
        send_registration_otp(email, code)
    except Exception:
        log.exception(
            "[register_init] failed to send email to %s", mask_email(email)
        )
        raise AuthError(_EMAIL_SEND_FAILED_MESSAGE, 500)


def register_confirm(
    email: str,
    code: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Подтверждает регистрацию атомарно (Stage 31m-fix-b2).

    OTP-валидация, создание/реактивация пользователя, роль student, обязательные
    consent_records и потребление OTP выполняются как одна core DB-транзакция
    в storage.register_confirm_atomic — без частичных состояний. SMTP здесь не
    участвует (письмо ушло на init-шаге). Welcome-уведомление — soft-fail и
    выполняется уже ПОСЛЕ успешного commit (его сбой не откатывает регистрацию).
    """
    try:
        user = storage.register_confirm_atomic(
            email=email,
            code=code,
            required_consent_types=REQUIRED_CONSENTS,
            ip=ip,
            user_agent=user_agent,
        )
    except storage.RegistrationDataError as e:
        # Отсутствует роль/consent-политика — проблема seed/reference data.
        raise AuthError(str(e), 500)
    except ValueError as e:
        raise AuthError(str(e), 400)

    # Welcome-уведомление в раздел «Сообщения» (soft-fail, content не логируется).
    # Вне core-транзакции: пользователь уже зафиксирован, сбой уведомления
    # не должен ломать регистрацию.
    from app.chat.system_publisher import publish_system_message
    publish_system_message(
        recipient_id=int(user["id"]),
        event_key=f"welcome:user:{user['id']}",
        text="Добро пожаловать в MindCare.",
    )

    return user


# ---------------------------------------------------------------------------
# Аутентификация
# ---------------------------------------------------------------------------

def authenticate_user(email: str, password: str) -> dict:
    user = storage.find_user_by_email(email)
    if not user or not _verify(password, user["hashed_password"]):
        raise AuthError("Неверный email или пароль", 401)
    storage.update_last_login(user["id"])
    return user


# ---------------------------------------------------------------------------
# Сброс пароля
# ---------------------------------------------------------------------------

def password_reset_init(email: str) -> None:
    """Отправляет OTP для сброса пароля. Молчит если email не найден."""
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
    except Exception:
        log.exception(
            "[password_reset_init] failed to send email to %s", mask_email(email)
        )
        raise AuthError(_EMAIL_SEND_FAILED_MESSAGE, 500)


def password_reset_confirm(
    email: str, code: str, new_password: str
) -> None:
    """Проверяет OTP, обновляет пароль, отзывает все сессии пользователя."""
    if len(new_password) < 8:
        raise AuthError("Пароль должен быть не короче 8 символов", 422)

    from app.auth import otp_service

    try:
        otp_service.verify_otp(email, code)
    except ValueError as e:
        raise AuthError(str(e), 400)

    user = storage.find_user_by_email(email)
    if not user:
        raise AuthError("Пользователь не найден", 404)

    storage.update_user_password(user["id"], _hash(new_password))
    storage.revoke_all_user_sessions(user["id"])


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


def change_password(
    user_id: str,
    current_password: str,
    new_password: str,
    new_password_confirm: str,
) -> None:
    """Меняет пароль авторизованного пользователя и отзывает все его сессии."""
    if new_password != new_password_confirm:
        raise AuthError("Новый пароль и подтверждение не совпадают", 422)
    if len(new_password) < 8:
        raise AuthError("Пароль должен быть не короче 8 символов", 422)

    user = storage.find_user_by_id(user_id)
    if not user:
        raise AuthError("Пользователь не найден", 404)

    if not _verify(current_password, user["hashed_password"]):
        raise AuthError("Неверный текущий пароль", 400)

    storage.update_user_password(user_id, _hash(new_password))
    storage.revoke_all_user_sessions(user_id)

    # System-уведомление (soft-fail, content не логируется). Timestamp в event_key —
    # чтобы каждая смена пароля давала отдельное сообщение.
    from datetime import datetime, timezone
    from app.chat.system_publisher import publish_system_message
    _ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    publish_system_message(
        recipient_id=int(user["id"]),
        event_key=f"password_changed:user:{user['id']}:{_ts}",
        text="Пароль вашей учётной записи был изменён.",
    )


def terminate_session(token: str) -> None:
    """Отзывает сессию (logout)."""
    storage.revoke_session(token)
