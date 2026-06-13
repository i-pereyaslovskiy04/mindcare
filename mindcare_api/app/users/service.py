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
from app.users.schemas import (
    AdminUserListQuery,
    AdminUserListItem,
    PaginatedUsersResponse,
    AdminUserCreate,
    AdminUserUpdate,
)
from app.auth.service import AuthError
from app.services.email_service import send_welcome_psychologist


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

    try:
        user = storage.create_user(
            email=data.email,
            full_name=data.full_name,
            password_hash=password_hash,
            role=data.role,
            phone=data.phone,
            basis_type=data.basis_type,
            basis_reference=data.basis_reference,
            legal_basis_comment=data.legal_basis_comment,
            confirmed_by_user_id=actor_id,
            ip=ip,
            user_agent=user_agent,
        )
    except ValueError as e:
        raise AuthError(str(e), status_code=409)

    try:
        send_welcome_psychologist(
            to_email=user["email"],
            name=user["full_name"],
            password=password,
        )
    except Exception as e:
        log.warning(
            "[create_user] User %s created but welcome email failed: %s",
            user["email"], e,
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


def delete_user(uuid: str) -> None:
    """
    Мягкое удаление юзера от имени администратора.
    Raises AuthError 404 если юзер не найден.
    """
    found = storage.soft_delete_user(uuid)
    if not found:
        raise AuthError("Пользователь не найден", status_code=404)


def update_user(uuid: str, data: AdminUserUpdate) -> dict:
    """
    Частичное обновление юзера от имени администратора.
    Требует хотя бы одно непустое поле — иначе 400.

    Raises:
        AuthError: если нет ни одного поля (400)
        AuthError: если юзер не найден (404)
        AuthError: если роль не существует в БД (400)
    """
    if all(
        v is None
        for v in (data.full_name, data.phone, data.is_active, data.role)
    ):
        raise AuthError(
            "Необходимо указать хотя бы одно поле для обновления",
            status_code=400,
        )

    try:
        return storage.update_user(
            uuid=uuid,
            full_name=data.full_name,
            phone=data.phone,
            is_active=data.is_active,
            role=data.role,
        )
    except ValueError as e:
        msg = str(e)
        status = 404 if "не найден" in msg else 400
        raise AuthError(msg, status_code=status)
