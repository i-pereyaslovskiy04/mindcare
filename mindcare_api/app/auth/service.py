"""
Business logic layer — no FastAPI, no HTTP concepts.
Depends only on storage and bcrypt. Safe to unit-test in isolation.
"""

import logging
from datetime import datetime
from typing import Optional

import bcrypt
from app.auth import storage
from app.auth.roles import ROLE_PRIORITY
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
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        audit_code: Optional[str] = None,
    ):
        self.message = message          # клиентское сообщение (может быть на русском)
        self.status_code = status_code  # HTTP status
        # Стабильный машинный код для audit (facade failure_reason_code). Обязателен
        # для loggable failure-путей (register_confirm/login/password_reset_confirm);
        # для прочих AuthError допустим None (их routes не пишут failure-audit в 4B-1).
        self.audit_code = audit_code


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
    # Ранняя проверка домена (до создания OTP/письма). Authoritative повторная
    # проверка — внутри транзакции confirm (register_confirm_atomic).
    from app.email_domains.errors import EmailDomainNotAllowedError
    from app.email_domains.service import assert_email_domain_allowed
    try:
        assert_email_domain_allowed(email)
    except EmailDomainNotAllowedError as e:
        raise AuthError(str(e), 422)
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
    from app.email_domains.errors import EmailDomainNotAllowedError
    from app.auth.errors import OtpExpiredError, OtpInvalidError
    try:
        user = storage.register_confirm_atomic(
            email=email,
            code=code,
            required_consent_types=REQUIRED_CONSENTS,
            ip=ip,
            user_agent=user_agent,
        )
    except EmailDomainNotAllowedError as e:
        # Домен отключили между init и confirm — новое регистрационное действие
        # отклоняется; OTP не потреблён (rollback внутри register_confirm_atomic).
        raise AuthError(str(e), 422, audit_code="domain_not_allowed")
    except storage.RegistrationDataError:
        # Отсутствует роль/consent-политика — проблема seed/reference data.
        # Клиенту — фиксированное безопасное сообщение (str(e) называет
        # роль/таблицу/consent-политику и в HTTP-ответ попадать не должен);
        # деталь остаётся только в server-side логах (см. storage-уровень).
        raise AuthError(
            "Не удалось завершить регистрацию. Обратитесь в поддержку.",
            500,
            audit_code="internal_error",
        )
    except OtpExpiredError as e:
        raise AuthError(str(e), 400, audit_code="otp_expired")
    except OtpInvalidError as e:
        # Явно только типизированный OTP-сбой (not-found/attempts/wrong).
        raise AuthError(str(e), 400, audit_code="otp_invalid")
    # Прочий (неожиданный) ValueError НЕ маскируется под otp_invalid: он
    # распространяется как внутренняя ошибка (route не ловит → 500), а не даёт
    # клиенту ложный «неверный код». Durable-обработка неожиданного — Stage 5A.

    # Привязка карточек незарегистрированного студента к новому аккаунту (этап 2).
    # Только ПОСЛЕ подтверждения владения email (этот шаг и есть подтверждение).
    # Вне core-транзакции и soft-fail: регистрация уже зафиксирована, сбой
    # привязки её не откатывает. ПДн (email) не логируем — только user_id.
    try:
        from app.appointments.service import link_unregistered_cards_to_user
        # Stage 5B-1: actor = сам подтвердивший email student (self-service).
        link_unregistered_cards_to_user(
            user["id"], user["email"],
            actor_id=int(user["id"]), actor_role="student",
            ip=ip, user_agent=user_agent,
        )
    except Exception as exc:
        # Минимизация: без exc_info/str(exc)/email/UUID/id/SQL — только фаза и
        # класс исключения. Postcommit soft-fail: регистрация не откатывается.
        log.warning("[register_confirm] phase=card_link error=%s",
                    type(exc).__name__)

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
        raise AuthError(
            "Неверный email или пароль", 401, audit_code="invalid_credentials"
        )
    # Fail-closed role invariant: не создаём сессию для аккаунта без валидной
    # активной роли. role — backend-computed primary из реальных roles; проверяем
    # ДО update_last_login/create_session.
    #
    # ADR-018: это ШТАТНЫЙ доменный отказ (403 / `no_active_roles`), а не
    # внутренняя авария. Прежний 500/`internal_error` был неотличим от реального
    # сбоя, шумел в мониторинге и вводил оператора в заблуждение.
    # `internal_error` остаётся только за настоящими внутренними сбоями.
    # Наружное сообщение обобщённое: состав ролей аккаунта не раскрывается.
    roles = user.get("roles") or []
    role = user.get("role")
    if (
        not roles                       # есть хотя бы одна активная роль
        or not isinstance(role, str)    # primary role — строка (не None/не мусор)
        or role not in roles            # primary role принадлежит активному набору
        or role not in ROLE_PRIORITY    # и это каноническая известная роль
    ):
        raise AuthError(
            "Доступ к системе не активирован. Обратитесь к администратору.",
            403,
            audit_code="no_active_roles",
        )
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
    """
    Подтверждает сброс пароля атомарно (Stage 31m-fix-b3).

    Валидация OTP, обновление password_hash, отзыв всех сессий пользователя и
    потребление OTP выполняются как одна core DB-транзакция в
    storage.password_reset_confirm_atomic — без частичных состояний. Хеш нового
    пароля считается ДО открытия транзакции (bcrypt медленный). Если OTP верный,
    но любой следующий шаг падает, всё откатывается и OTP не теряется.
    """
    if len(new_password) < 8:
        raise AuthError(
            "Пароль должен быть не короче 8 символов", 422,
            audit_code="password_policy",
        )

    from app.auth.errors import OtpExpiredError, OtpInvalidError
    new_password_hash = _hash(new_password)
    try:
        storage.password_reset_confirm_atomic(
            email=email,
            code=code,
            new_password_hash=new_password_hash,
        )
    except storage.UserNotFoundError:
        raise AuthError("Пользователь не найден", 404, audit_code="user_not_found")
    except OtpExpiredError as e:
        raise AuthError(str(e), 400, audit_code="otp_expired")
    except OtpInvalidError as e:
        # Только типизированный OTP-сбой; неожиданный ValueError не маскируется
        # (распространяется как внутренняя ошибка → 500).
        raise AuthError(str(e), 400, audit_code="otp_invalid")


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
    """
    Меняет пароль авторизованного пользователя атомарно (Stage 31m-fix-b3).

    Поиск пользователя, проверка текущего пароля, обновление password_hash и
    отзыв ВСЕХ сессий выполняются как одна core DB-транзакция в
    storage.change_password_atomic — без частичных состояний (сбой на отзыве
    сессий откатывает и смену пароля). Хеш нового пароля считается ДО открытия
    транзакции (bcrypt медленный); проверка текущего пароля — внутри транзакции
    через callback. System-уведомление — soft-fail ПОСЛЕ успешного commit.
    """
    if new_password != new_password_confirm:
        raise AuthError("Новый пароль и подтверждение не совпадают", 422)
    if len(new_password) < 8:
        raise AuthError("Пароль должен быть не короче 8 символов", 422)

    new_password_hash = _hash(new_password)
    try:
        user = storage.change_password_atomic(
            user_id=user_id,
            verify_current=lambda stored_hash: _verify(current_password, stored_hash),
            new_password_hash=new_password_hash,
        )
    except storage.UserNotFoundError:
        raise AuthError("Пользователь не найден", 404)
    except storage.InvalidCurrentPasswordError:
        raise AuthError("Неверный текущий пароль", 400)

    # System-уведомление (soft-fail, content не логируется). Вне core-транзакции:
    # пароль уже изменён и сессии отозваны, сбой уведомления это не откатывает.
    # Timestamp в event_key — чтобы каждая смена пароля давала отдельное сообщение.
    from datetime import datetime, timezone
    from app.chat.system_publisher import publish_system_message
    _ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    publish_system_message(
        recipient_id=int(user["id"]),
        event_key=f"password_changed:user:{user['id']}:{_ts}",
        text="Пароль вашей учётной записи был изменён.",
    )


def get_profile(user_id: str) -> dict:
    """Self-profile текущего пользователя."""
    profile = storage.get_profile(user_id)
    if not profile:
        raise AuthError("Пользователь не найден", 404)
    return profile


def update_profile(
    user_id: str,
    fields: dict,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """Обновляет разрешённые self-поля (PATCH-семантика: только переданные).
    ПДн (ФИО/телефон) не логируются. Значения полей темы уже провалидированы
    Literal-схемой (иначе 422).
    """
    updates = dict(fields)

    if "full_name" in updates:
        name = (updates["full_name"] or "").strip()
        if len(name) < 2:
            raise AuthError(
                "ФИО должно содержать минимум 2 символа", 422,
                audit_code="invalid_request",
            )
        updates["full_name"] = name

    if "phone" in updates:
        updates["phone"] = (updates["phone"] or "").strip() or None  # пустой → NULL

    from app.auth.errors import ProfileActorContextError
    try:
        return storage.update_profile_atomic(
            user_id, updates,
            actor_role=actor_role, ip=ip, user_agent=user_agent,
        )
    except storage.UserNotFoundError:
        raise AuthError(
            "Пользователь не найден", 404, audit_code="user_not_found",
        )
    except ProfileActorContextError:
        raise AuthError(
            "Не удалось обновить профиль.", 500, audit_code="internal_error",
        )
    # commit-time/postcommit/unknown НЕ ловятся здесь → 500 без *_failed.


def terminate_session(token: str) -> None:
    """Отзывает сессию (logout)."""
    storage.revoke_session(token)
