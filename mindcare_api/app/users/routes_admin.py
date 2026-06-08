"""
Админские эндпоинты управления пользователями.
Префикс: /api/admin/users
Доступ: только с ролью 'admin' через Depends(require_role("admin")).
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Optional, Literal

from app.auth import audit
from app.auth.deps import require_role, get_current_user
from app.users import service
from app.users.schemas import (
    AdminUserListQuery,
    PaginatedUsersResponse,
    AdminUserCreate,
    AdminUserCreateResponse,
    AdminUserUpdate,
    AdminUserRead,
)


router = APIRouter(
    prefix="/admin/users",
    tags=["admin: users"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/", response_model=PaginatedUsersResponse)
def list_users(
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    size: int = Query(
        default=20, ge=1, le=100, description="Элементов на странице"
    ),
    search: Optional[str] = Query(
        default=None, max_length=200, description="Поиск по email или ФИО"
    ),
    role: Optional[Literal["student", "psychologist", "admin", "supervisor"]] = Query(
        default=None, description="Фильтр по роли"
    ),
    is_active: Optional[bool] = Query(
        default=None, description="Фильтр по активности"
    ),
    sort: str = Query(default="created_at", description="Поле сортировки"),
    order: Literal["asc", "desc"] = Query(
        default="desc", description="Направление сортировки"
    ),
    include_deleted: bool = Query(default=False, description="Включать удалённых пользователей"),
):
    """Список всех пользователей с пагинацией, поиском и фильтрами."""
    query = AdminUserListQuery(
        page=page,
        size=size,
        search=search,
        role=role,
        is_active=is_active,
        sort=sort,
        order=order,
        include_deleted=include_deleted,
    )
    return service.get_users_list(query)


@router.post("/", response_model=AdminUserCreateResponse, status_code=201)
def create_user(
    request: Request,
    body: AdminUserCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Создание нового пользователя (психолога или админа).
    Пароль генерируется автоматически и отправляется на email.
    """
    try:
        user = service.create_user(body)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    audit.log_auth_event(
        event=f"admin_create_user:{user['uuid']}",
        user_id=current_user["id"],
        user_email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return user


@router.get("/{uuid}", response_model=AdminUserRead)
def get_user(uuid: str):
    """Профиль конкретного пользователя по UUID."""
    try:
        return service.get_user(uuid)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch("/{uuid}", response_model=AdminUserRead)
def update_user(
    request: Request,
    uuid: str,
    body: AdminUserUpdate,
    current_user: dict = Depends(get_current_user),
):
    """
    Частичное обновление пользователя.
    Поддерживает: блокировку/разблокировку, смену роли, ФИО и телефон.
    """
    try:
        result = service.update_user(uuid, body)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    audit.log_auth_event(
        event=f"admin_update_user:{uuid}",
        user_id=current_user["id"],
        user_email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return result


@router.delete("/{uuid}", status_code=204)
def delete_user(
    request: Request,
    uuid: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Мягкое удаление пользователя. Отзывает все сессии.
    Возвращает 204 No Content при успехе.
    """
    try:
        service.delete_user(uuid)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    audit.log_auth_event(
        event=f"admin_delete_user:{uuid}",
        user_id=current_user["id"],
        user_email=current_user["email"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
