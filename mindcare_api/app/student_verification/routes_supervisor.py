"""
Подтверждение студента ДонГУ — проверка заявок supervisor'ом (ADR-029).

Доступ (router-level, нельзя забыть на новом эндпоинте):
  * require_role("supervisor") — admin без supervisor и psychologist → 403;
  * _forbid_impersonation — любая impersonation-сессия → 403 ДО handler:
    admin, вошедший «под именем» supervisor'а, не получает ни список, ни
    карточку (номер не читается и не расшифровывается, content_read не
    пишется), ни решения. Прямой вход пользователя admin+supervisor разрешён.
    Audit-решение: это auth-guard до бизнес-операции (как 403 require_role) —
    события нет; пользователю-цели отказ не приписывается, а сам вход «под
    именем» уже зафиксирован admin_user_impersonated.

  GET  ""                 — список без номера билета (без аудита);
  GET  /{uuid}            — карточка с полным номером: content_read
                            INDEPENDENT + RAISE, сбой → 503 без номера;
  POST /{uuid}/approve    — решение; POST /{uuid}/reject {reason}.
Отказы решений — {"detail", "code"} + student_verification_review_failed после
отката. Malformed UUID → 422 (FastAPI).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.student_verification import errors, service
from app.student_verification.routes import error_response
from app.student_verification.schemas import (
    HistoryItem, ListStatusFilter, PaginatedVerificationsOut, RejectIn,
    VerificationCardOut,
)

_NO_STORE = "no-store, private"


def _forbid_impersonation(current_user: dict = Depends(get_current_user)) -> None:
    if current_user.get("impersonator_user_id") is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Проверка заявок недоступна при входе под именем пользователя",
        )


router = APIRouter(
    prefix="/supervisor/student-verifications",
    tags=["supervisor-student-verifications"],
    dependencies=[
        Depends(require_role("supervisor")),
        Depends(_forbid_impersonation),
    ],
)


def _reviewer(current_user: dict) -> int:
    # Acting-роль — только supervisor (у admin+supervisor — тоже supervisor).
    resolve_role_or_403(current_user, allowed={"supervisor"}, preferred="supervisor")
    return int(current_user["id"])


def _client(request: Request) -> tuple:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


@router.get("", response_model=PaginatedVerificationsOut)
def list_verifications(
    response: Response,
    status_filter: ListStatusFilter = Query(default="pending", alias="status"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=200),
):
    response.headers["Cache-Control"] = _NO_STORE
    items, total = service.list_for_review(
        status=status_filter, page=page, size=size, search=search,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{request_uuid}", response_model=VerificationCardOut)
def get_verification_card(
    request_uuid: UUID,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    reviewer_id = _reviewer(current_user)
    ip, ua = _client(request)
    try:
        card = service.get_card_for_review(
            request_uuid, reviewer_id=reviewer_id, ip=ip, user_agent=ua,
        )
    except errors.VerificationError as exc:
        return error_response(exc)
    except AuditError:
        # Fail-closed: факт чтения не зафиксирован → номер не отдаём.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось зафиксировать обращение к данным заявки. Повторите попытку.",
        ) from None
    response.headers["Cache-Control"] = _NO_STORE
    return card


def _decide(
    request_uuid: UUID,
    decision: str,
    request: Request,
    current_user: dict,
    reason: Optional[str] = None,
):
    reviewer_id = _reviewer(current_user)
    ip, ua = _client(request)
    try:
        return service.decide(
            request_uuid,
            decision=decision,
            reviewer_id=reviewer_id,
            reason=reason,
            ip=ip,
            user_agent=ua,
        )
    except errors.VerificationError as exc:
        record_secondary_failure(
            event="student_verification_review_failed",
            actor=Actor.user(reviewer_id, "supervisor"),
            failure_reason_code=exc.code,
            context=build_request_context(ip=ip, user_agent=ua),
        )
        return error_response(exc)


@router.post("/{request_uuid}/approve", response_model=HistoryItem)
def approve_verification(
    request_uuid: UUID,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return _decide(request_uuid, "approve", request, current_user)


@router.post("/{request_uuid}/reject", response_model=HistoryItem)
def reject_verification(
    request_uuid: UUID,
    body: RejectIn,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return _decide(request_uuid, "reject", request, current_user, reason=body.reason)
