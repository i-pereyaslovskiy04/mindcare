"""
Эндпоинты для психолога: список записей, подтверждение, отклонение.
Доступ: только роль psychologist.
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.deps import get_current_user, require_role
from app.appointments import service
from app.appointments.schemas import (
    AppointmentDecline,
    AppointmentDetailRead,
    PaginatedAppointmentsResponse,
    PaginatedGroupSessionsResponse,
    PsychologistScheduleRead,
)

router = APIRouter(
    prefix="/psychologist/appointments",
    tags=["appointments-psychologist"],
    dependencies=[Depends(require_role("psychologist"))],
)

group_router = APIRouter(
    prefix="/psychologist/group-sessions",
    tags=["group-sessions-psychologist"],
    dependencies=[Depends(require_role("psychologist"))],
)

schedule_router = APIRouter(
    prefix="/psychologist/schedule",
    tags=["schedule-psychologist"],
    dependencies=[Depends(require_role("psychologist"))],
)


@schedule_router.get("", response_model=PsychologistScheduleRead)
def get_my_schedule(
    current_user: dict = Depends(get_current_user),
):
    """Своё расписание психолога (read-only): активные окна, перерывы и типы.

    Психолог не имеет доступа к supervisor/admin-эндпоинтам, поэтому типы
    встреч (названия/длительности) возвращаются вместе с правилами.
    """
    return service.get_psychologist_schedule(int(current_user["id"]))


@group_router.get("", response_model=PaginatedGroupSessionsResponse)
def list_my_group_sessions(
    page:         int  = Query(default=1, ge=1),
    size:         int  = Query(default=20, ge=1, le=100),
    include_past: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """Групповые занятия, назначенные текущему психологу.

    Подтверждение психологом не требуется — это read-only список.
    """
    items, total = service.list_group_sessions_psychologist(
        psychologist_id=current_user["id"],
        page=page,
        size=size,
        include_past=include_past,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("", response_model=PaginatedAppointmentsResponse)
def list_appointments(
    page:      int            = Query(default=1, ge=1),
    size:      int            = Query(default=20, ge=1, le=100),
    status:    Optional[str]  = Query(default=None),
    date_from: Optional[str]  = Query(default=None, description="YYYY-MM-DD"),
    date_to:   Optional[str]  = Query(default=None, description="YYYY-MM-DD"),
    current_user: dict        = Depends(get_current_user),
):
    """Список записей психолога (только его собственные)."""
    df = _parse_date(date_from) if date_from else None
    dt = _parse_date(date_to) if date_to else None
    items, total = service.list_psychologist_appointments(
        psychologist_id=current_user["id"],
        page=page,
        size=size,
        status_filter=status,
        date_from=df,
        date_to=dt,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.patch("/{uuid}/confirm", response_model=AppointmentDetailRead)
def confirm_appointment(
    uuid:         str,
    current_user: dict = Depends(get_current_user),
):
    """Подтвердить запись студента (pending_confirmation → confirmed)."""
    try:
        return service.psychologist_confirm(
            uuid=uuid,
            psychologist_user=current_user,
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/{uuid}/decline", response_model=AppointmentDetailRead)
def decline_appointment(
    uuid:         str,
    body:         AppointmentDecline,
    current_user: dict = Depends(get_current_user),
):
    """Отклонить запись студента с необязательной причиной."""
    try:
        return service.psychologist_decline(
            uuid=uuid,
            psychologist_user=current_user,
            reason=body.reason,
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


def _parse_date(s: str):
    return date.fromisoformat(s)
