"""
Эндпоинты для студентов: запись на приём, слоты, групповые занятия.
Доступ: только роль student.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import get_current_user, require_role
from app.appointments import service
from app.appointments.schemas import (
    AppointmentCancelBody,
    AppointmentCreate,
    AppointmentDetailRead,
    GroupSessionRegistrationRead,
    MeetingTypeRead,
    PaginatedAppointmentsResponse,
    PaginatedGroupSessionsResponse,
    SlotsResponse,
)

router = APIRouter(
    prefix="/appointments",
    tags=["appointments-student"],
    dependencies=[Depends(require_role("student"))],
)

group_router = APIRouter(
    prefix="/group-sessions",
    tags=["group-sessions-student"],
    dependencies=[Depends(require_role("student"))],
)


# ── Slots ─────────────────────────────────────────────────────────────────────

@router.get("/slots", response_model=SlotsResponse)
def get_slots(
    date: str = Query(..., description="YYYY-MM-DD (Moscow date)"),
    meeting_type_id: int = Query(..., description="ID типа встречи"),
    modality: str = Query(
        "in_person", description="in_person | online"
    ),
    current_user: dict = Depends(get_current_user),
):
    """Доступные слоты для выбранного типа встречи (Europe/Moscow).

    Психолог определяется только из активного TherapyEngagement студента —
    студент может видеть слоты лишь своего назначенного психолога. Слоты
    считаются по длительности и буферу MeetingType.
    """
    try:
        target_date = _parse_date(date)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Неверный формат даты (YYYY-MM-DD)"
        )

    from app.db.session import SessionLocal
    from app.appointments import storage as _storage
    with SessionLocal() as db:
        engagement = _storage.get_active_engagement(
            int(current_user["id"]), db
        )
    if not engagement:
        raise HTTPException(
            status_code=404, detail="Нет активного назначенного психолога"
        )

    try:
        return service.get_slots(
            engagement.psychologist_id, target_date, meeting_type_id, modality
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Meeting types (student) ─────────────────────────────────────────────────

@router.get("/meeting-types", response_model=list[MeetingTypeRead])
def list_student_meeting_types():
    """Доступные для записи индивидуальные типы встреч (для выбора студентом).

    Только is_active + is_bookable + не групповые. Групповые занятия
    записываются через отдельный эндпоинт group-sessions.
    """
    return service.list_student_meeting_types()


# ── My appointments ───────────────────────────────────────────────────────────

@router.get("/my", response_model=PaginatedAppointmentsResponse)
def list_my_appointments(
    page:   int            = Query(default=1, ge=1),
    size:   int            = Query(default=20, ge=1, le=100),
    status: Optional[str]  = Query(default=None),
    current_user: dict     = Depends(get_current_user),
):
    """Список записей студента (все статусы, newest-first)."""
    items, total = service.list_student_appointments(
        student_id=current_user["id"],
        page=page,
        size=size,
        status_filter=status,
    )
    return {"items": items, "total": total, "page": page, "size": size}


# ── Book appointment ──────────────────────────────────────────────────────────

@router.post("", response_model=AppointmentDetailRead, status_code=status.HTTP_201_CREATED)
def book_appointment(
    body: AppointmentCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Записаться к психологу. Требует активной связи (TherapyEngagement).
    Запись создаётся со статусом pending_confirmation.
    """
    try:
        return service.book_appointment(
            student_user=current_user,
            starts_at=body.starts_at,
            modality=body.modality,
            topic=body.topic,
            meeting_type_id=body.meeting_type_id,
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Cancel appointment ────────────────────────────────────────────────────────

@router.patch("/{uuid}/cancel", response_model=AppointmentDetailRead)
def cancel_appointment(
    uuid:         str,
    body:         AppointmentCancelBody,
    current_user: dict = Depends(get_current_user),
):
    """
    Студент отменяет запись. Разрешено только до дня записи (Moscow timezone).
    Статусы pending_confirmation и confirmed можно отменить.
    """
    try:
        return service.student_cancel(
            uuid=uuid,
            student_user=current_user,
            reason=body.reason,
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Group sessions (student view) ─────────────────────────────────────────────

@group_router.get("", response_model=PaginatedGroupSessionsResponse)
def list_group_sessions(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """Список предстоящих групповых занятий (с признаком is_registered)."""
    items, total = service.list_group_sessions_student(
        student_id=current_user["id"],
        page=page,
        size=size,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@group_router.post(
    "/{uuid}/register",
    response_model=GroupSessionRegistrationRead,
    status_code=status.HTTP_201_CREATED,
)
def register_group_session(
    uuid:         str,
    current_user: dict = Depends(get_current_user),
):
    """
    Записаться на групповое занятие.
    Подтверждение психолога не требуется.
    """
    try:
        return service.student_register_group(uuid, current_user)
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@group_router.delete("/{uuid}/register", status_code=status.HTTP_204_NO_CONTENT)
def cancel_group_session(
    uuid:         str,
    current_user: dict = Depends(get_current_user),
):
    """Отменить регистрацию на групповое занятие."""
    try:
        service.student_cancel_group(uuid, current_user)
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_date(s: str):
    from datetime import date as dt
    return dt.fromisoformat(s)
