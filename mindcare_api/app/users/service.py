"""
Бизнес-логика управления пользователями (со стороны админа).
Зависит только от storage и не знает про FastAPI/HTTP.
"""

import logging
import secrets
import string
from typing import Optional

log = logging.getLogger(__name__)

from app.users import storage
from app.users.errors import (
    ActorContextError,
    EmailAlreadyExistsError,
    InvalidUserRequestError,
    RoleConfigError,
    UserNotFoundError,
)
from app.users.schemas import (
    AdminUserListQuery,
    AdminUserListItem,
    PaginatedUsersResponse,
    AdminUserCreate,
    AdminUserUpdate,
)
from app.auth.service import AuthError
from app.services.email_service import send_welcome_staff


def _generate_password(length: int = 12) -> str:
    """
    Генерирует случайный пароль из букв, цифр и безопасных спецсимволов.
    Гарантирует наличие минимум одного символа каждого типа.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*" for c in password)
        ):
            return password


def get_users_list(query: AdminUserListQuery) -> PaginatedUsersResponse:
    """
    Возвращает пагинированный список юзеров по заданным фильтрам.

    Принимает Pydantic-схему запроса, делегирует выборку в storage,
    упаковывает результат в PaginatedUsersResponse.
    """
    items_raw, total = storage.find_users(
        page=query.page,
        size=query.size,
        search=query.search,
        role=query.role,
        is_active=query.is_active,
        sort=query.sort,
        order=query.order,
        include_deleted=query.include_deleted,
    )

    items = [AdminUserListItem.model_validate(item) for item in items_raw]

    return PaginatedUsersResponse(
        items=items,
        total=total,
        page=query.page,
        size=query.size,
    )


def create_user(
    data: AdminUserCreate,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Создаёт нового юзера (психолога, супервизора или админа) от имени
    администратора. Вместе с пользователем в одной транзакции фиксируется
    legal basis record (документированное основание организации).

    Генерирует временный пароль и отправляет его на email нового юзера.
    Пароль хешируется перед сохранением в БД.

    Raises:
        AuthError: если email уже занят (409)
        AuthError: если не удалось отправить письмо (500)
    """
    from app.auth.service import _hash  # локальный импорт — circular import

    password = _generate_password()
    password_hash = _hash(password)

    # Multi-role создание: набор staff-ролей из roles[] либо legacy single role.
    # Schema гарантирует ровно одно из полей; storage делает defense-in-depth
    # (dedupe + validate staff-only + существование ролей).
    roles = list(data.roles) if data.roles else [data.role]

    from app.email_domains.errors import EmailDomainNotAllowedError
    try:
        user = storage.create_user(
            email=data.email,
            full_name=data.full_name,
            password_hash=password_hash,
            roles=roles,
            phone=data.phone,
            basis_type=data.basis_type,
            basis_reference=data.basis_reference,
            legal_basis_comment=data.legal_basis_comment,
            confirmed_by_user_id=actor_id,
            actor_role=actor_role,
            ip=ip,
            user_agent=user_agent,
        )
    except EmailDomainNotAllowedError as e:
        # Домен вне allowlist — 422 (не подкласс ValueError).
        raise AuthError(str(e), status_code=422, audit_code="domain_not_allowed")
    except EmailAlreadyExistsError as e:
        # Дубликат email (active/soft-deleted/allowlisted-race) — precommit.
        raise AuthError(
            str(e), status_code=409, audit_code="email_already_exists",
        )
    except (RoleConfigError, ActorContextError):
        # Config/wiring internal precommit — generic 500 без раскрытия деталей.
        raise AuthError(
            "Не удалось создать пользователя.", status_code=500,
            audit_code="internal_error",
        )
    # commit-time/postcommit/unknown НЕ ловятся здесь → 500 без *_failed.

    try:
        # Нейтральное staff-письмо (без «аккаунта психолога» и перечня прав) —
        # корректно для admin/supervisor/psychologist и multi-role.
        send_welcome_staff(
            to_email=user["email"],
            name=user["full_name"],
            password=password,
        )
    except Exception as e:
        # Минимизировано: email/raw exception text не логируются (могут
        # содержать ПДн/SMTP-детали) — только фаза и класс исключения.
        log.warning(
            "[ADMIN USER] phase=welcome_email error=%s", type(e).__name__,
        )

    # Welcome-уведомление в раздел «Сообщения» (soft-fail, content не логируется).
    from app.chat.system_publisher import publish_system_message
    publish_system_message(
        recipient_id=int(user["id"]),
        event_key=f"welcome:user:{user['id']}",
        text="Ваша учётная запись MindCare создана.",
    )

    user["temporary_password"] = password
    return user


def get_user(uuid: str) -> dict:
    user = storage.get_user_by_uuid(uuid)
    if user is None:
        raise AuthError("Пользователь не найден", status_code=404)
    return user


def delete_user(
    uuid: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """
    Мягкое удаление юзера от имени администратора.
    Raises AuthError 404/user_not_found если юзер не найден (в т.ч. malformed
    UUID — текущий контракт сохранён); 500/internal_error при wiring-сбое.
    """
    try:
        found = storage.soft_delete_user(
            uuid,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=ip,
            user_agent=user_agent,
        )
    except ActorContextError:
        raise AuthError(
            "Не удалось удалить пользователя.", status_code=500,
            audit_code="internal_error",
        )
    if not found:
        raise AuthError(
            "Пользователь не найден", status_code=404,
            audit_code="user_not_found",
        )


def update_user(
    uuid: str,
    data: AdminUserUpdate,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Частичное обновление юзера от имени администратора (multi-role, set-based).
    Требует хотя бы одно непустое поле — иначе 400.

    Управление ролями — только staff, без destructive replace-all (см.
    storage.update_user): `roles[]` (set-based) либо legacy `role` (adapter).
    Запись legal basis и изменение ролей выполняются атомарно в storage.

    Raises:
        AuthError: если нет ни одного поля (400);
        AuthError: если юзер не найден (404);
        AuthError: нарушение role-контракта — свой status_code (400/409/422).
    """
    if all(
        v is None
        for v in (
            data.full_name, data.phone, data.is_active, data.role, data.roles,
        )
    ):
        raise AuthError(
            "Необходимо указать хотя бы одно поле для обновления",
            status_code=400, audit_code="invalid_request",
        )

    try:
        return storage.update_user(
            uuid=uuid,
            full_name=data.full_name,
            phone=data.phone,
            is_active=data.is_active,
            role=data.role,
            roles=data.roles,
            legal_basis_confirmed=data.legal_basis_confirmed,
            basis_type=data.basis_type,
            basis_reference=data.basis_reference,
            legal_basis_comment=data.legal_basis_comment,
            confirmed_by_user_id=actor_id,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=ip,
            user_agent=user_agent,
        )
    except storage.RoleChangeError as e:
        # audit_code задан на raise-site (role_policy_violation/self_admin_
        # protected/legal_basis_required/invalid_request), не по тексту.
        raise AuthError(str(e), status_code=e.status_code, audit_code=e.audit_code)
    except UserNotFoundError:
        raise AuthError(
            "Пользователь не найден", status_code=404,
            audit_code="user_not_found",
        )
    except InvalidUserRequestError as e:
        raise AuthError(str(e), status_code=400, audit_code="invalid_request")
    except (RoleConfigError, ActorContextError):
        raise AuthError(
            "Не удалось обновить пользователя.", status_code=500,
            audit_code="internal_error",
        )
    # commit-time/postcommit/unknown НЕ ловятся здесь → 500 без *_failed.
