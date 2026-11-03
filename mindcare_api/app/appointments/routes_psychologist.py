"""
Эндпоинты для психолога: список записей, подтверждение, отклонение, итог
встречи (ADR-035) и встречи клиента для карточки.
Доступ: только роль psychologist.
"""

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.appointments import service
from app.appointments.guards import forbid_impersonation
from app.appointments.schemas import (
    AppointmentDecline,
    AppointmentDetailRead,
    AppointmentOutcomeIn,
    AppointmentOutcomeRead,
    ClientAppointmentsPage,
    PaginatedAppointmentsResponse,
    PaginatedGroupSessionsResponse,
    PsychologistScheduleRead,
    ScheduleExceptionRead,
)
from app.core.no_store_route import (
    NoStoreRoute, audit_unavailable_response, no_store_json,
)


def _ip(request: Request):
    return request.client.host if request.client else None


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
    page:         int           = Query(default=1, ge=1),
    size:         int           = Query(default=20, ge=1, le=100),
    include_past: bool          = Query(default=False),
    date_from:    Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to:      Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    current_user: dict          = Depends(get_current_user),
):
    """Групповые занятия, назначенные текущему психологу.

    Подтверждение психологом не требуется — это read-only список.
    date_from/date_to — опц. фильтр по диапазону (для календарного обзора).
    """
    df = _parse_date(date_from) if date_from else None
    dt = _parse_date(date_to) if date_to else None
    items, total = service.list_group_sessions_psychologist(
        psychologist_id=current_user["id"],
        page=page,
        size=size,
        include_past=include_past,
        date_from=df,
        date_to=dt,
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
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    """Подтвердить запись студента (pending_confirmation → confirmed)."""
    role = resolve_role_or_403(
        current_user, allowed={"psychologist"}, preferred="psychologist",
    )
    actor = Actor.user(int(current_user["id"]), role)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    try:
        return service.psychologist_confirm(
            uuid=uuid,
            psychologist_user=current_user,
            actor_role=role,
            ip=ip,
            user_agent=ua,
        )
    except service.AppointmentError as exc:
        if isinstance(exc, service.AuditableAppointmentError):
            record_secondary_failure(
                event="appointment_confirm_failed", actor=actor,
                failure_reason_code=exc.audit_code,
                context=build_request_context(ip=ip, user_agent=ua),
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/{uuid}/decline", response_model=AppointmentDetailRead)
def decline_appointment(
    uuid:         str,
    body:         AppointmentDecline,
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    """Отклонить запись студента с необязательной причиной."""
    role = resolve_role_or_403(
        current_user, allowed={"psychologist"}, preferred="psychologist",
    )
    actor = Actor.user(int(current_user["id"]), role)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    try:
        return service.psychologist_decline(
            uuid=uuid,
            psychologist_user=current_user,
            reason=body.reason,
            actor_role=role,
            ip=ip,
            user_agent=ua,
        )
    except service.AppointmentError as exc:
        if isinstance(exc, service.AuditableAppointmentError):
            record_secondary_failure(
                event="appointment_decline_failed", actor=actor,
                failure_reason_code=exc.audit_code,
                context=build_request_context(ip=ip, user_agent=ua),
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch(
    "/{uuid}/outcome",
    response_model=AppointmentOutcomeRead,
    dependencies=[Depends(forbid_impersonation)],
)
def mark_appointment_outcome(
    uuid:         UUID,
    body:         AppointmentOutcomeIn,
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Итог индивидуальной встречи (ADR-035): confirmed → completed («Состоялась»)
    | no_show («Неявка»). Только психолог этой встречи, только после её
    окончания (время сервера). Повтор того же итога — 200 changed=false без
    события; иной итог / не confirmed / не закончилась — 409 без изменений.
    """
    role = resolve_role_or_403(
        current_user, allowed={"psychologist"}, preferred="psychologist",
    )
    actor = Actor.user(int(current_user["id"]), role)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    try:
        return service.psychologist_mark_outcome(
            uuid=str(uuid),
            psychologist_user=current_user,
            outcome=body.outcome,
            actor_role=role,
            ip=ip,
            user_agent=ua,
        )
    except service.AppointmentError as exc:
        if isinstance(exc, service.AuditableAppointmentError):
            record_secondary_failure(
                event="appointment_outcome_failed", actor=actor,
                failure_reason_code=exc.audit_code,
                context=build_request_context(ip=ip, user_agent=ua),
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except AuditError:
        # Сбой обязательного аудита: переход откатан, итог не сохранён.
        return audit_unavailable_response()


# ── Встречи клиента в карточке психолога (ADR-035) ───────────────────────────

client_router = APIRouter(
    prefix="/psychologist/clients",
    tags=["appointments-psychologist"],
    route_class=NoStoreRoute,
    dependencies=[
        Depends(require_role("psychologist")),
        Depends(forbid_impersonation),
    ],
)


@client_router.get("/{student_uuid}/appointments", response_model=ClientAppointmentsPage)
def list_client_appointments(
    student_uuid: UUID,
    view:   Literal["upcoming", "history"] = Query(default="upcoming"),
    before: Optional[str] = Query(default=None, max_length=256),
    size:   int = Query(
        default=service.CLIENT_APPOINTMENTS_DEFAULT_SIZE,
        ge=1, le=service.CLIENT_APPOINTMENTS_MAX_SIZE,
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Встречи выбранного клиента с текущим психологом: предстоящие и история.
    Право — строгое активное сопровождение с активным клиентом; иначе 404.
    Групповые занятия и рабочая доступность психолога сюда не входят.
    """
    try:
        return service.list_client_appointments(
            int(current_user["id"]), student_uuid, view, before, size,
        )
    except service.ClientAppointmentsNotAvailable:
        return no_store_json(404, {"detail": "Встречи клиента недоступны"})
    except service.AppointmentError as exc:
        return no_store_json(exc.status_code, {"detail": exc.message})


exception_router = APIRouter(
    prefix="/psychologist/schedule-exceptions",
    tags=["schedule-psychologist"],
    dependencies=[Depends(require_role("psychologist"))],
)


@exception_router.get("", response_model=list[ScheduleExceptionRead])
def list_my_schedule_exceptions(
    date_from: Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(default=None, description="YYYY-MM-DD"),
    current_user: dict = Depends(get_current_user),
):
    """Разовые изменения (исключения) своего расписания (read-only)."""
    try:
        df = _parse_date(date_from) if date_from else None
        dt = _parse_date(date_to) if date_to else None
    except ValueError:
        raise HTTPException(status_code=422, detail="Некорректная дата (YYYY-MM-DD)")
    return service.list_schedule_exceptions(int(current_user["id"]), df, dt)


def _parse_date(s: str):
    return date.fromisoformat(s)
