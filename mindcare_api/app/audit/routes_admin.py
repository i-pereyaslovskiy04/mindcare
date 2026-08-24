"""
Stage 8 — HTTP-слой read-only admin viewer журналов.

Доступ: только активная membership-роль `admin` (ADR-018). Проверка стоит на
уровне router'а, поэтому её нельзя забыть на новом эндпоинте; seed-permissions
`admin:audit` / `auth:view_logs` источником авторизации НЕ являются —
application-level permission enforcement в проекте отсутствует.

Порядок обработки list-эндпоинта:
  1. 401/403 (router dependency) и валидация запроса — ДО чтения журналов,
     поэтому неуспешная попытка не создаёт success-события;
  2. SELECT + безопасная проекция;
  3. `audit_logs_viewed` через facade;
  4. сбой этой записи → 503 без данных журнала (fail-closed);
  5. только после успешной записи — сам ответ.

Сырой session-токен из route не выходит: наружу в service отдаётся его SHA-256
хеш, тот же формат, который хранится в `user_sessions.id`.
"""
from __future__ import annotations

from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.auth.deps import (
    get_current_user, get_session_token, require_role, resolve_role_or_403,
)
from app.auth.security import hash_session_token

from app.audit import admin_service as service
from app.audit.admin_schemas import (
    AuditEventsPage, AuditOptionsOut, AuthEventsPage, DataChangesPage,
)
from app.audit.contracts import AuditError

router = APIRouter(
    prefix="/admin/audit",
    tags=["admin: audit"],
    dependencies=[Depends(require_role("admin"))],
)

# Содержимое журналов не кэшируется ни браузером, ни промежуточными узлами.
# ETag намеренно не выставляется: валидатор сам по себе является утечкой
# (по его изменению можно наблюдать активность в журнале, не читая его).
_NO_STORE = "no-store, private"


def _admin_actor(current_user: dict) -> tuple[int, str]:
    """Валидный admin-актор ДО обращения к журналам.

    `require_role` на router'е гарантирует членство, `resolve_role_or_403` —
    что acting-роль действительно `admin`, а не другая роль multi-role
    пользователя.
    """
    return (
        int(current_user["id"]),
        resolve_role_or_403(current_user, allowed={"admin"}, preferred="admin"),
    )


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = _NO_STORE


def _call(handler, **kwargs):
    """Единый маппинг ошибок слоя.

    `AuditQueryError` — контракт запроса (422). `AuditError` (включая
    `AuditStorageError`) — не удалось зафиксировать факт просмотра; отдаём 503
    и НИЧЕГО из журнала. Текст исключения наружу не идёт.
    """
    try:
        return handler(**kwargs)
    except service.AuditQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.message,
        ) from None
    except AuditError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось зафиксировать обращение к журналу. Повторите попытку.",
        ) from None


@router.get("/options", response_model=AuditOptionsOut)
def get_audit_options(response: Response) -> AuditOptionsOut:
    """Безопасные значения фильтров из живых REGISTRY / CHANGE_REGISTRY.

    Событие просмотра НЕ пишется: содержимого журналов здесь нет, а шум от
    загрузки справочника обесценил бы сам access-журнал.
    """
    _no_store(response)
    return service.build_options()


@router.get("/events", response_model=AuditEventsPage)
def list_audit_events(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1, le=service.MAX_RECORD_REF),
    size: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    order: str = Query(default="desc"),
    actor_uuid: Optional[UUID] = Query(default=None),
    actor_kind: Optional[str] = Query(default=None, max_length=32),
    actor_role: Optional[str] = Query(default=None, max_length=32),
    event_type: Optional[str] = Query(default=None, max_length=100),
    outcome: Optional[str] = Query(default=None, max_length=16),
    entity_type: Optional[str] = Query(default=None, max_length=100),
    entity_id: Optional[int] = Query(default=None),
    target_user_uuid: Optional[UUID] = Query(default=None),
    include_access_events: bool = Query(default=False),
    token: str = Depends(get_session_token),
    current_user: dict = Depends(get_current_user),
) -> AuditEventsPage:
    actor_id, acting_role = _admin_actor(current_user)
    _no_store(response)
    return _call(
        service.list_audit_events,
        actor_id=actor_id,
        actor_role=acting_role,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        session_id_hash=hash_session_token(token),
        page=page, size=size, date_from=date_from, date_to=date_to, order=order,
        actor_uuid=actor_uuid, actor_kind=actor_kind, filter_actor_role=actor_role,
        event_type=event_type, outcome=outcome, entity_type=entity_type,
        entity_id=entity_id, target_user_uuid=target_user_uuid,
        include_access_events=include_access_events,
    )


@router.get("/auth-events", response_model=AuthEventsPage)
def list_auth_events(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1, le=service.MAX_RECORD_REF),
    size: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    order: str = Query(default="desc"),
    actor_uuid: Optional[UUID] = Query(default=None),
    actor_kind: Optional[str] = Query(default=None, max_length=32),
    event: Optional[str] = Query(default=None, max_length=150),
    success: Optional[bool] = Query(default=None),
    token: str = Depends(get_session_token),
    current_user: dict = Depends(get_current_user),
) -> AuthEventsPage:
    # Фильтра по роли здесь нет намеренно: auth_log роль актора не хранит, а
    # подстановка текущей роли выдавала бы за исторический факт то, чем она не
    # является.
    actor_id, acting_role = _admin_actor(current_user)
    _no_store(response)
    return _call(
        service.list_auth_events,
        actor_id=actor_id,
        actor_role=acting_role,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        session_id_hash=hash_session_token(token),
        page=page, size=size, date_from=date_from, date_to=date_to, order=order,
        actor_uuid=actor_uuid, actor_kind=actor_kind, event=event, success=success,
    )


@router.get("/data-changes", response_model=DataChangesPage)
def list_data_changes(
    request: Request,
    response: Response,
    page: int = Query(default=1, ge=1, le=service.MAX_RECORD_REF),
    size: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    order: str = Query(default="desc"),
    actor_uuid: Optional[UUID] = Query(default=None),
    actor_kind: Optional[str] = Query(default=None, max_length=32),
    actor_role: Optional[str] = Query(default=None, max_length=32),
    table_name: Optional[str] = Query(default=None, max_length=100),
    operation: Optional[str] = Query(default=None, max_length=10),
    record_id: Optional[int] = Query(default=None),
    target_user_uuid: Optional[UUID] = Query(default=None),
    token: str = Depends(get_session_token),
    current_user: dict = Depends(get_current_user),
) -> DataChangesPage:
    actor_id, acting_role = _admin_actor(current_user)
    _no_store(response)
    return _call(
        service.list_data_changes,
        actor_id=actor_id,
        actor_role=acting_role,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        session_id_hash=hash_session_token(token),
        page=page, size=size, date_from=date_from, date_to=date_to, order=order,
        actor_uuid=actor_uuid, actor_kind=actor_kind, filter_actor_role=actor_role,
        table_name=table_name, operation=operation, record_id=record_id,
        target_user_uuid=target_user_uuid,
    )
