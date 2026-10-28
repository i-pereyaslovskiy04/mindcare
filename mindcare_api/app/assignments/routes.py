"""
Задания владельца (ADR-033): GET/POST /api/assignments/my/*.

Router-level: require_role("student") — по membership roles[] (клиент со
staff-ролями тоже имеет student, ADR-024) и запрет impersonation (403 до
бизнес-операции, без события). Видны только собственные задания по всем
сопровождениям клиента; изменить можно лишь задание строго активного
сопровождения. Чтение своих заданий отдельного аудит-события не пишет.

Отказы complete пишут assignment_complete_failed ПОСЛЕ отката (access_denied /
engagement_inactive / assignment_finalized). Сбой обязательного аудита → 503 без
failure-события; технический сбой или сбой commit → 500 без failure-события.
Все ответы — Cache-Control: no-store, private (AssignmentsRoute).
"""
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from app.assignments import service
from app.assignments._http import client_meta, domain_response
from app.assignments.context import ClientContext
from app.assignments.errors import (
    AssignmentEngagementInactive, AssignmentFinalized, AssignmentNotAvailable,
    AssignmentValidationError,
)
from app.assignments.guards import forbid_impersonation
from app.assignments.sanitized_route import (
    AssignmentsRoute, audit_unavailable_response, invalid_response,
)
from app.assignments.schemas import (
    AssignmentMutationOut, MyAssignmentsPageOut, MySummaryOut,
)
from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, require_role

router = APIRouter(
    prefix="/assignments/my",
    tags=["assignments"],
    route_class=AssignmentsRoute,
    dependencies=[
        Depends(require_role("student")),
        Depends(forbid_impersonation),
    ],
)


@router.get("", response_model=MyAssignmentsPageOut)
def list_my_assignments(
    view: Literal["open", "history"] = Query(default="open"),
    before: Optional[str] = Query(default=None, max_length=256),
    size: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
):
    ctx = ClientContext(user_id=int(current_user["id"]))
    try:
        return service.list_my(ctx, view, before, size)
    except AssignmentValidationError as exc:
        return invalid_response(exc.errors)


@router.get("/summary", response_model=MySummaryOut)
def my_assignments_summary(current_user: dict = Depends(get_current_user)):
    return service.my_summary(ClientContext(user_id=int(current_user["id"])))


@router.post("/{assignment_uuid}/complete", response_model=AssignmentMutationOut)
def complete_my_assignment(
    assignment_uuid: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ctx = ClientContext(user_id=int(current_user["id"]))
    ip, ua = client_meta(request)
    try:
        return service.complete_my(ctx, assignment_uuid, ip=ip, user_agent=ua)
    except (
        AssignmentNotAvailable, AssignmentEngagementInactive, AssignmentFinalized,
    ) as exc:
        record_secondary_failure(
            event="assignment_complete_failed",
            actor=Actor.user(ctx.user_id, "student"),
            failure_reason_code=exc.failure_reason,
            context=build_request_context(ip=ip, user_agent=ua),
        )
        return domain_response(exc)
    except AuditError:
        # Обязательный аудит не записан → переход откатан; failure-события нет.
        return audit_unavailable_response()
