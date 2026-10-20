"""
Staff-доступ к результатам психодиагностики (Этап E, ADR-016).

Политика доступа (шаблон session_notes):
  - supervisor — результаты любого студента;
  - psychologist — только студентов с active/past TherapyEngagement;
  - admin — доступа НЕТ (не в списке ролей роутера).

Список — metadata-only (без баллов, без audit). Деталь — полный результат +
audit-событие test_result_content_read. Роль-ветка выбирается по заголовку
X-Active-Role, валидированному по membership (service._resolve_staff_result_role).
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from app.auth.deps import get_current_user, require_role
from app.tests import service
from app.tests.schemas import PaginatedStaffResultsResponse, ResultRead

router = APIRouter(
    prefix="/staff/test-results",
    tags=["staff-test-results"],
    dependencies=[Depends(require_role("supervisor", "psychologist"))],
)


def _client(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


@router.get("", response_model=PaginatedStaffResultsResponse)
def list_student_results(
    student_uuid:  str           = Query(...),
    page:          int           = Query(default=1, ge=1),
    size:          int           = Query(default=20, ge=1, le=100),
    current_user:  dict          = Depends(get_current_user),
    x_active_role: Optional[str] = Header(default=None, alias="X-Active-Role"),
):
    try:
        items, total = service.list_student_results(
            current_user=current_user, requested_role=x_active_role,
            student_uuid=student_uuid, page=page, size=size,
        )
    except service.ResultAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except service.ResultNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{result_uuid}", response_model=ResultRead)
def get_staff_result(
    result_uuid:   str,
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
    except service.ResultNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
