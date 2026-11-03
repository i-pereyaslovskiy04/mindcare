"""
Staff-доступ к результатам психодиагностики (Этап E, ADR-016; дополнение
2026-10-29).

Политика доступа (одна проверка для списка, детали и ответов — в storage ДО
чтения содержимого):
  - psychologist — только клиенты СТРОГОГО активного сопровождения
    (status='active' AND ended_at IS NULL) с активным клиентом; клиент может
    иметь staff-роли. Любой отказ — один и тот же 404 +
    test_result_read_failed (access_denied). Ответы на вопросы — только ему;
  - supervisor — список и деталь «чистого» активного студента (иначе 404),
    ответы → 403;
  - admin — доступа НЕТ (не в списке ролей роутера);
  - impersonation-сессия → 403 (forbid_impersonation, без события).

Список — metadata-only (без баллов, без события). Деталь и ответы — после
test_result_content_read (INDEPENDENT + RAISE): сбой аудита → 503 без
содержимого. Все ответы — Cache-Control: no-store, private (NoStoreRoute).
Роль-ветка выбирается по заголовку X-Active-Role, валидированному по
membership (service._resolve_staff_result_role).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, require_role
from app.core.no_store_route import NoStoreRoute, audit_unavailable_response
from app.tests import service
from app.tests.guards import forbid_impersonation
from app.tests.schemas import (
    PaginatedStaffResultsResponse, ResultRead, StaffResultAnswersRead,
)

router = APIRouter(
    prefix="/staff/test-results",
    tags=["staff-test-results"],
    route_class=NoStoreRoute,
    dependencies=[
        Depends(require_role("supervisor", "psychologist")),
        Depends(forbid_impersonation),
    ],
)

NOT_AVAILABLE = "Результаты клиента недоступны"


def _client(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def _not_available(current_user: dict, ip, ua) -> HTTPException:
    """Отказ области психолога: failure-событие + единый 404."""
    record_secondary_failure(
        event="test_result_read_failed",
        actor=Actor.user(int(current_user["id"]), "psychologist"),
        failure_reason_code=service.ResultNotAvailable.failure_reason,
        context=build_request_context(ip=ip, user_agent=ua),
    )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_AVAILABLE)


@router.get("", response_model=PaginatedStaffResultsResponse)
def list_student_results(
    request:       Request,
    student_uuid:  UUID          = Query(...),
    page:          int           = Query(default=1, ge=1),
    size:          int           = Query(default=20, ge=1, le=100),
    current_user:  dict          = Depends(get_current_user),
    x_active_role: Optional[str] = Header(default=None, alias="X-Active-Role"),
):
    ip, ua = _client(request)
    try:
        items, total = service.list_student_results(
            current_user=current_user, requested_role=x_active_role,
            student_uuid=student_uuid, page=page, size=size,
        )
    except service.ResultAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except service.ResultNotAvailable:
        raise _not_available(current_user, ip, ua)
    except service.ResultNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{result_uuid}/answers", response_model=StaffResultAnswersRead)
def get_staff_result_answers(
    result_uuid:   UUID,
    request:       Request,
    current_user:  dict          = Depends(require_role("psychologist")),
    x_active_role: Optional[str] = Header(default=None, alias="X-Active-Role"),
):
    ip, ua = _client(request)
    try:
        return service.get_staff_result_answers(
            current_user=current_user, requested_role=x_active_role,
            result_uuid=result_uuid, ip=ip, user_agent=ua,
        )
    except service.ResultAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except service.ResultNotAvailable:
        raise _not_available(current_user, ip, ua)
    except AuditError:
        # Fail-closed: чтение не зафиксировано → ответы не отдаются.
        return audit_unavailable_response()


@router.get("/{result_uuid}", response_model=ResultRead)
def get_staff_result(
    result_uuid:   UUID,
    request:       Request,
    current_user:  dict          = Depends(get_current_user),
    x_active_role: Optional[str] = Header(default=None, alias="X-Active-Role"),
):
    ip, ua = _client(request)
    try:
        return service.get_staff_result(
            current_user=current_user, requested_role=x_active_role,
            result_uuid=result_uuid, ip=ip, user_agent=ua,
        )
    except service.ResultAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except service.ResultNotAvailable:
        raise _not_available(current_user, ip, ua)
    except service.ResultNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except AuditError:
        return audit_unavailable_response()
