"""
Админские эндпоинты управления пользователями.
Префикс: /api/admin/users
Доступ: только с ролью 'admin' через Depends(require_role("admin")).
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Optional, Literal

from app.auth.deps import require_role, get_current_user, resolve_role_or_403
from app.auth import service as auth_service
from app.auth.security import hash_session_token
from app.audit import Actor, Target, record_event
from app.audit.contracts import AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.users import service
from app.users.schemas import (
    AdminUserListQuery,
    PaginatedUsersResponse,
    AdminUserCreate,
    AdminUserCreateResponse,
    AdminUserUpdate,
    AdminUserRead,
    ImpersonateResponse,
)


def _admin_actor(current_user: dict) -> Actor:
    """Валидный admin-actor до business try (router-dep гарантирует роль admin)."""
    return Actor.user(
        int(current_user["id"]),
        resolve_role_or_403(current_user, allowed={"admin"}, preferred="admin"),
    )


def _client_ip(request: Request):
    return request.client.host if request.client else None


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
    Создание нового пользователя (психолога, супервизора или админа).
    Пароль генерируется автоматически и отправляется на email.
    Требует подтверждения документированного основания (legal_basis_confirmed);
    запись основания создаётся в одной транзакции с пользователем.
    """
    actor = _admin_actor(current_user)   # валидный actor ДО business try
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        user = service.create_user(
            body,
            actor_id=actor.user_id,
            actor_role=actor.role,
            ip=ip,
            user_agent=ua,
        )
    except service.AuthError as e:
        # Durable best-effort failure audit (INDEPENDENT/SOFT); НЕ меняет HTTP.
        record_secondary_failure(
            event="admin_user_create_failed", actor=actor,
            failure_reason_code=e.audit_code,
            context=build_request_context(ip=ip, user_agent=ua),
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return user


@router.post("/{uuid}/impersonate", response_model=ImpersonateResponse)
def impersonate_user(
    request: Request,
    uuid: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Вход администратора «под именем» пользователя (ADR-025).

    Создаёт сессию целевого пользователя с серверной отметкой
    impersonator_user_id (для атрибуции) и возвращает её токен. Запрещено:
    вход под самим собой, под другим admin, под заблокированным пользователем
    и под аккаунтом без активных ролей (guard в service.impersonate_target).
    Аудит: admin_user_impersonated (target — целевой пользователь).
    """
    actor = _admin_actor(current_user)
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        target = service.impersonate_target(uuid, actor_id=actor.user_id)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)

    session_token, expires_at = auth_service.create_session(
        user_id=target["id"],
        ip=ip,
        user_agent=ua,
        impersonator_user_id=actor.user_id,
    )

    # session_id_hash новой сессии = user_sessions.id impersonation-сессии:
    # связывает audit-строку с конкретной созданной сессией.
    # Fail-closed (RAISE): если аудит не записался — отзываем уже созданную
    # сессию (raw-токен ещё не отдан клиенту, станет непригоден) и отдаём 503,
    # чтобы привилегированный вход не остался без следа.
    try:
        record_event(
            event="admin_user_impersonated",
            actor=actor,
            target=Target("user", int(target["id"])),
            context=build_request_context(
                ip=ip, user_agent=ua,
                session_id_hash=hash_session_token(session_token),
            ),
        )
    except AuditError:
        auth_service.terminate_session(session_token)
        raise HTTPException(
            status_code=503,
            detail="Не удалось зафиксировать вход. Попробуйте позже.",
        )

    return {
        "session_token": session_token,
        "expires_at":    expires_at,
        "roles":         target["roles"],
        "role":          target["role"],
        "name":          target["full_name"],
    }


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
    actor = _admin_actor(current_user)
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        result = service.update_user(
            uuid,
            body,
            actor_id=actor.user_id,
            actor_role=actor.role,
            ip=ip,
            user_agent=ua,
        )
    except service.AuthError as e:
        record_secondary_failure(
            event="admin_user_update_failed", actor=actor,
            failure_reason_code=e.audit_code,
            context=build_request_context(ip=ip, user_agent=ua),
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
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
    actor = _admin_actor(current_user)
    ip = _client_ip(request)
    ua = request.headers.get("user-agent")
    try:
        service.delete_user(
            uuid,
            actor_id=actor.user_id,
            actor_role=actor.role,
            ip=ip,
            user_agent=ua,
        )
    except service.AuthError as e:
        record_secondary_failure(
            event="admin_user_delete_failed", actor=actor,
            failure_reason_code=e.audit_code,
            context=build_request_context(ip=ip, user_agent=ua),
        )
        raise HTTPException(status_code=e.status_code, detail=e.message)
