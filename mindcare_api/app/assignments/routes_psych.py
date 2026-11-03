"""
Задания психолога (ADR-033):
  GET  /api/psychologist/clients/{student_uuid}/assignments
  POST /api/psychologist/clients/{student_uuid}/assignments
  POST /api/psychologist/assignments/{assignment_uuid}/cancel

Router-level: require_role("psychologist") (admin/supervisor сами по себе
доступа НЕ имеют) и запрет impersonation. Право — строгое активное
сопровождение actor → клиент (status='active' AND ended_at IS NULL), клиент
существует и активен; клиент может иметь staff-роли. Любой отказ доступа
(нет клиента / нет сопровождения / чужое задание / сопровождение завершено) —
один и тот же 404 + *_failed (access_denied).

Чтение — fail-closed: assignment_content_read на каждое задание страницы до
ответа; сбой → 503 без текстов. Сбой обязательного аудита мутации → 503 без
failure-события; технический сбой / commit → 500 без failure-события.
Все ответы — Cache-Control: no-store, private (AssignmentsRoute).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.assignments import service
from app.assignments._http import client_meta, domain_response
from app.assignments.context import PsychologistContext
from app.assignments.errors import (
    AssignmentFinalized, AssignmentNotAvailable, AssignmentValidationError,
    MaterialUnavailable,
)
from app.assignments.guards import forbid_impersonation
from app.assignments.sanitized_route import (
    AssignmentsRoute, audit_unavailable_response, invalid_response,
)
from app.assignments.schemas import (
    AssignmentCreateIn, AssignmentMutationOut, ClientAssignmentsPageOut,
)
from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, require_role

router = APIRouter(
    prefix="/psychologist",
    tags=["psychologist-assignments"],
    route_class=AssignmentsRoute,
    dependencies=[
        Depends(require_role("psychologist")),
        Depends(forbid_impersonation),
    ],
)


def _record_failure(event: str, actor_id: int, code: str, ip, ua) -> None:
    record_secondary_failure(
        event=event,
        actor=Actor.user(actor_id, "psychologist"),
        failure_reason_code=code,
        context=build_request_context(ip=ip, user_agent=ua),
    )


@router.get(
    "/clients/{student_uuid}/assignments", response_model=ClientAssignmentsPageOut,
)
def list_client_assignments(
    student_uuid: UUID,
    request: Request,
    before: Optional[str] = Query(default=None, max_length=256),
    size: int = Query(default=service.DEFAULT_PAGE_SIZE, ge=1, le=service.MAX_PAGE_SIZE),
    current_user: dict = Depends(get_current_user),
):
    ctx = PsychologistContext(user_id=int(current_user["id"]))
    ip, ua = client_meta(request)
    try:
        return service.list_for_client(
            ctx, student_uuid, before, size, ip=ip, user_agent=ua,
        )
    except AssignmentValidationError as exc:
        return invalid_response(exc.errors)
    except AssignmentNotAvailable as exc:
        _record_failure("assignment_read_failed", ctx.user_id, exc.failure_reason, ip, ua)
        return domain_response(exc)
    except AuditError:
        # Fail-closed: чтение не зафиксировано → тексты не отдаются.
        return audit_unavailable_response()


@router.post(
    "/clients/{student_uuid}/assignments",
    response_model=AssignmentMutationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_client_assignment(
    student_uuid: UUID,
    body: AssignmentCreateIn,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ctx = PsychologistContext(user_id=int(current_user["id"]))
    ip, ua = client_meta(request)
    try:
        return service.create_for_client(
            ctx, student_uuid,
            text=body.text, due_date=body.due_date, article_uuid=body.article_uuid,
            ip=ip, user_agent=ua,
        )
    except AssignmentValidationError as exc:
        _record_failure("assignment_create_failed", ctx.user_id, exc.failure_reason, ip, ua)
        return invalid_response(exc.errors)
    except (AssignmentNotAvailable, MaterialUnavailable) as exc:
        _record_failure("assignment_create_failed", ctx.user_id, exc.failure_reason, ip, ua)
        return domain_response(exc)
    except AuditError:
        return audit_unavailable_response()


@router.post(
    "/assignments/{assignment_uuid}/cancel", response_model=AssignmentMutationOut,
)
def cancel_client_assignment(
    assignment_uuid: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ctx = PsychologistContext(user_id=int(current_user["id"]))
    ip, ua = client_meta(request)
    try:
        return service.cancel(ctx, assignment_uuid, ip=ip, user_agent=ua)
    except (AssignmentNotAvailable, AssignmentFinalized) as exc:
        _record_failure("assignment_cancel_failed", ctx.user_id, exc.failure_reason, ip, ua)
        return domain_response(exc)
    except AuditError:
        return audit_unavailable_response()
