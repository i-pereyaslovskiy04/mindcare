"""
Чтение контактов сотрудником (ADR-032): GET /api/staff/users/{uuid}/contacts.

Router-level: require_role("psychologist","supervisor") (admin сам по себе
доступа НЕ имеет) и запрет impersonation. Права — по membership roles[], не по
выбранному кабинету и не по заголовку X-Active-Role: психолог — при строгом
активном сопровождении, супервизор — для чистых студентов из своего списка.
Любой отказ (нет цели / нет права) — один и тот же 404 + user_contacts_read_failed
(access_denied). Сбой обязательного аудита → 503 без значений.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.user_contacts import service
from app.user_contacts.context import StaffContext
from app.user_contacts.errors import ContactsNotAvailable
from app.user_contacts.guards import forbid_impersonation
from app.user_contacts.sanitized_route import NO_STORE, ContactsRoute
from app.user_contacts.schemas import ContactsStaffOut

_AUDIT_UNAVAILABLE = (
    "Не удалось зафиксировать обращение к контактам. Повторите попытку."
)

router = APIRouter(
    prefix="/staff/users",
    tags=["staff-user-contacts"],
    route_class=ContactsRoute,
    dependencies=[
        Depends(require_role("psychologist", "supervisor")),
        Depends(forbid_impersonation),
    ],
)


@router.get("/{user_uuid}/contacts", response_model=ContactsStaffOut)
def read_user_contacts(
    user_uuid: UUID,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    actor_id = int(current_user["id"])
    ctx = StaffContext(user_id=actor_id, roles=frozenset(current_user.get("roles") or []))
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    try:
        result = service.read_for_staff(ctx, user_uuid, ip=ip, user_agent=ua)
    except ContactsNotAvailable as exc:
        role = resolve_role_or_403(
            current_user, allowed={"psychologist", "supervisor"},
        )
        record_secondary_failure(
            event="user_contacts_read_failed",
            actor=Actor.user(actor_id, role),
            failure_reason_code="access_denied",
            context=build_request_context(ip=ip, user_agent=ua),
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "code": exc.code},
            headers={"Cache-Control": NO_STORE},
        )
    except AuditError:
        # Fail-closed: чтение не зафиксировано → ни контактов, ни телефона.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_AUDIT_UNAVAILABLE,
        ) from None
    response.headers["Cache-Control"] = NO_STORE
    return result
