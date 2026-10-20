"""
Эндпоинты супервизора для управления расписанием и групповыми занятиями.
Доступ: admin и supervisor.

Пути (ADR-015): /api/supervisor/* — НЕ /api/admin/*.
"""

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.audit import Actor
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.appointments import service
from app.appointments.schemas import (
    AppointmentDetailRead,
    GroupSessionCreate,
    GroupSessionRead,
    GroupSessionUpdate,
    MeetingTypeCreate,
    MeetingTypeRead,
    MeetingTypeUpdate,
    PaginatedGroupSessionsResponse,
    PaginatedUnregisteredStudentCardsResponse,
    ScheduleBreakCreate,
    ScheduleBreakRead,
    ScheduleCreate,
    ScheduleDeleteResult,
    ScheduleExceptionCreate,
    ScheduleExceptionRead,
    ScheduleImpactRead,
    ScheduleRuleCreate,
    ScheduleRuleRead,
    ScheduleSeriesRead,
    ScheduleUpdate,
    SlotsResponse,
    SupervisorAppointmentCreate,
    UnregisteredStudentCardCreate,
    UnregisteredStudentCardRead,
    UnregisteredStudentCardUpdate,
)


def _sup_role(current_user: dict) -> str:
    return resolve_role_or_403(
        current_user, allowed={"admin", "supervisor"}, preferred="supervisor",
    )


def _ip(request: Request):
    return request.client.host if request.client else None


def _parse_series_id(series_id: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(series_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail="Некорректный series_id")


router = APIRouter(
    prefix="/supervisor",
    tags=["supervisor-appointments"],
    dependencies=[Depends(require_role("admin", "supervisor"))],
)


# ── MeetingTypes ──────────────────────────────────────────────────────────────

@router.get("/meeting-types", response_model=list[MeetingTypeRead])
def list_meeting_types(
    include_inactive: bool = Query(default=False),
):
    """Список типов встреч/занятий."""
    return service.list_meeting_types(include_inactive=include_inactive)


@router.post(
    "/meeting-types",
    response_model=MeetingTypeRead,
    status_code=status.HTTP_201_CREATED,
)
def create_meeting_type(
    body: MeetingTypeCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать тип встречи."""
    role = _sup_role(current_user)
    try:
        return service.create_meeting_type(
            body.model_dump(),
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/meeting-types/{mt_id}", response_model=MeetingTypeRead)
def update_meeting_type(
    mt_id: int,
    body: MeetingTypeUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Обновить тип встречи (частичное обновление)."""
    role = _sup_role(current_user)
    try:
        return service.update_meeting_type(
            mt_id, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Slots (supervisor) ───────────────────────────────────────────────────────

@router.get("/slots", response_model=SlotsResponse)
def get_supervisor_slots(
    psychologist_id: int = Query(..., description="ID психолога"),
    date: str = Query(..., description="YYYY-MM-DD (Moscow date)"),
    meeting_type_id: int = Query(..., description="ID типа встречи"),
    modality: str = Query("in_person", description="in_person | online"),
):
    """Свободные слоты выбранного психолога (для ручной записи супервизором).

    Переиспользует ту же логику слотов, что и студент (расписание, перерывы,
    исключения, занятые записи, групповые сессии), но psychologist_id берётся
    из query, а не из engagement текущего пользователя.
    """
    from datetime import date as dt_date
    try:
        target_date = dt_date.fromisoformat(date)
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Неверный формат даты (YYYY-MM-DD)"
        )
    try:
        return service.get_slots(
            psychologist_id, target_date, meeting_type_id, modality
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── ScheduleRules ──────────────────────────────────────────────────────────────

@router.get("/schedule-rules", response_model=list[ScheduleRuleRead])
def list_schedule_rules(
    psychologist_id: int = Query(..., description="ID психолога"),
    include_inactive: bool = Query(
        default=False,
        description="Показывать деактивированные (soft-deleted) серии",
    ),
):
    """Рабочие окна психолога (доступность).

    По умолчанию только активные правила (активный список). include_inactive=
    True возвращает и деактивированные серии.
    """
    return service.list_schedule_rules(
        psychologist_id, include_inactive=include_inactive
    )


@router.post(
    "/schedule-rules",
    response_model=list[ScheduleRuleRead],
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_rules(
    body: ScheduleRuleCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать рабочие окна на один или несколько дней (общий series_id)."""
    role = _sup_role(current_user)
    try:
        data = body.model_dump()
        from datetime import time as dt_time, date as dt_date
        data["start_time"] = dt_time.fromisoformat(data["start_time"])
        data["end_time"] = dt_time.fromisoformat(data["end_time"])
        data["effective_from"] = dt_date.fromisoformat(data["effective_from"])
        if data.get("effective_until"):
            data["effective_until"] = dt_date.fromisoformat(
                data["effective_until"]
            )
        return service.create_schedule_rules(
            data,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete(
    "/schedule-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
def deactivate_schedule_rule(
    rule_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Деактивировать рабочее окно (is_active=False)."""
    role = _sup_role(current_user)
    try:
        service.deactivate_schedule_rule(
            rule_id,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Schedules: unified create + series soft-delete/restore/extend ────────────

@router.post(
    "/schedules",
    response_model=ScheduleSeriesRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(
    body: ScheduleCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать расписание (серию): рабочие окна + перерывы одной операцией.

    Несколько дней недели сразу, время start/end, период (effective_from/until),
    повторяющиеся перерывы и auto_extend. auto_extend требует effective_until.
    """
    role = _sup_role(current_user)
    try:
        from datetime import time as dt_time, date as dt_date
        data = body.model_dump()
        data["start_time"] = dt_time.fromisoformat(data["start_time"])
        data["end_time"] = dt_time.fromisoformat(data["end_time"])
        data["effective_from"] = dt_date.fromisoformat(data["effective_from"])
        if data.get("effective_until"):
            data["effective_until"] = dt_date.fromisoformat(
                data["effective_until"]
            )
        for brk in data.get("breaks", []):
            brk["start_time"] = dt_time.fromisoformat(brk["start_time"])
            brk["end_time"] = dt_time.fromisoformat(brk["end_time"])
        data["created_by"] = int(current_user["id"])
        return service.create_schedule(
            data,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.patch("/schedules/{series_id}", response_model=ScheduleSeriesRead)
def update_schedule(
    series_id: str,
    body: ScheduleUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Редактировать серию расписания (та же series_id, тот же психолог).

    Существующие записи не удаляются и не переносятся. auto_extend требует
    effective_until. is_active серии сохраняется.
    """
    sid = _parse_series_id(series_id)
    role = _sup_role(current_user)
    try:
        from datetime import time as dt_time, date as dt_date
        data = body.model_dump()
        data["start_time"] = dt_time.fromisoformat(data["start_time"])
        data["end_time"] = dt_time.fromisoformat(data["end_time"])
        data["effective_from"] = dt_date.fromisoformat(data["effective_from"])
        if data.get("effective_until"):
            data["effective_until"] = dt_date.fromisoformat(
                data["effective_until"]
            )
        for brk in data.get("breaks", []):
            brk["start_time"] = dt_time.fromisoformat(brk["start_time"])
            brk["end_time"] = dt_time.fromisoformat(brk["end_time"])
        return service.update_schedule(
            sid, data,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/schedules/{series_id}/impact", response_model=ScheduleImpactRead
)
def schedule_impact(series_id: str):
    """Предупреждение перед деактивацией: будущие записи в периоде серии."""
    sid = _parse_series_id(series_id)
    try:
        return service.schedule_impact(sid)
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/schedules/{series_id}", response_model=ScheduleDeleteResult)
def soft_delete_schedule(
    series_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Soft-delete расписания-серии (is_active=False). Записи не удаляются.

    Возвращает количество будущих записей в периоде как предупреждение.
    """
    sid = _parse_series_id(series_id)
    role = _sup_role(current_user)
    try:
        return service.soft_delete_schedule(
            sid,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/schedules/{series_id}/restore", response_model=ScheduleSeriesRead
)
def restore_schedule(
    series_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Восстановить ранее деактивированное расписание-серию."""
    sid = _parse_series_id(series_id)
    role = _sup_role(current_user)
    try:
        return service.restore_schedule(
            sid,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/schedules/{series_id}/extend", response_model=ScheduleSeriesRead
)
def extend_schedule(
    series_id: str,
    request: Request,
    months: int = Query(default=1, ge=1, le=12),
    current_user: dict = Depends(get_current_user),
):
    """Быстрое действие «продлить на месяц»: двигает effective_until серии."""
    sid = _parse_series_id(series_id)
    role = _sup_role(current_user)
    try:
        return service.extend_schedule(
            sid, months=months,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Manual booking by supervisor ─────────────────────────────────────────────

@router.post(
    "/appointments",
    response_model=AppointmentDetailRead,
    status_code=status.HTTP_201_CREATED,
)
def supervisor_book_appointment(
    body: SupervisorAppointmentCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Ручная запись на свободный слот (создаётся pending_confirmation).

    Субъект — ровно один: зарегистрированный студент (student_id) ИЛИ карточка
    незарегистрированного студента (unregistered_student_card_id). Психолог
    получает system-уведомление о записи; created_by фиксирует supervisor'а (аудит).
    """
    role = _sup_role(current_user)
    actor = Actor.user(int(current_user["id"]), role)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    try:
        return service.supervisor_book_appointment(
            student_id=body.student_id,
            unregistered_student_card_id=body.unregistered_student_card_id,
            psychologist_id=body.psychologist_id,
            meeting_type_id=body.meeting_type_id,
            starts_at=body.starts_at,
            modality=body.modality,
            topic=body.topic,
            current_user=current_user,
            actor_role=role,
            ip=ip,
            user_agent=ua,
        )
    except service.AppointmentError as exc:
        if isinstance(exc, service.AuditableAppointmentError):
            record_secondary_failure(
                event="appointment_create_failed", actor=actor,
                failure_reason_code=exc.audit_code,
                context=build_request_context(ip=ip, user_agent=ua),
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Unregistered student cards ───────────────────────────────────────────────

@router.get(
    "/unregistered-student-cards",
    response_model=PaginatedUnregisteredStudentCardsResponse,
)
def list_unregistered_student_cards(
    q: str = Query(default=None, description="Поиск по ФИО/email/телефону"),
    include_archived: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
):
    """Список карточек незарегистрированных студентов (поиск + пагинация)."""
    items, total = service.list_unregistered_student_cards(
        page=page,
        size=size,
        query=q,
        include_archived=include_archived,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.post(
    "/unregistered-student-cards",
    response_model=UnregisteredStudentCardRead,
    status_code=status.HTTP_201_CREATED,
)
def create_unregistered_student_card(
    body: UnregisteredStudentCardCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать карточку незарегистрированного студента.

    Требует full_name и personal_data_consent=true. created_by фиксирует
    создавшего supervisor/admin.
    """
    role = _sup_role(current_user)
    actor = Actor.user(int(current_user["id"]), role)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    try:
        return service.create_unregistered_student_card(
            body.model_dump(), current_user,
            actor_role=role,
            ip=ip,
            user_agent=ua,
        )
    except service.AppointmentError as exc:
        if isinstance(exc, service.AuditableAppointmentError):
            record_secondary_failure(
                event="unregistered_student_card_create_failed", actor=actor,
                failure_reason_code=exc.audit_code,
                context=build_request_context(ip=ip, user_agent=ua),
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch(
    "/unregistered-student-cards/{card_id}",
    response_model=UnregisteredStudentCardRead,
)
def update_unregistered_student_card(
    card_id: int,
    body: UnregisteredStudentCardUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Обновить личные поля карточки (частично). Audit/consent не меняются."""
    try:
        return service.update_unregistered_student_card(
            card_id, body.model_dump(exclude_unset=True),
            current_user=current_user,
            actor_role=_sup_role(current_user),
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/unregistered-student-cards/{card_id}/archive",
    response_model=UnregisteredStudentCardRead,
)
def archive_unregistered_student_card(
    card_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Архивировать карточку (soft archive через archived_at)."""
    try:
        return service.archive_unregistered_student_card(
            card_id,
            current_user=current_user,
            actor_role=_sup_role(current_user),
            ip=_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Schedule breaks ────────────────────────────────────────────────────────────

@router.get("/schedule-breaks", response_model=list[ScheduleBreakRead])
def list_schedule_breaks(
    psychologist_id: int = Query(..., description="ID психолога"),
):
    """Повторяющиеся перерывы психолога."""
    return service.list_schedule_breaks(psychologist_id)


@router.post(
    "/schedule-breaks",
    response_model=list[ScheduleBreakRead],
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_breaks(
    body: ScheduleBreakCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать повторяющиеся перерывы (например обед) на один/несколько дней."""
    role = _sup_role(current_user)
    try:
        data = body.model_dump()
        from datetime import time as dt_time, date as dt_date
        data["start_time"] = dt_time.fromisoformat(data["start_time"])
        data["end_time"] = dt_time.fromisoformat(data["end_time"])
        data["effective_from"] = dt_date.fromisoformat(
            data["effective_from"]
        )
        if data.get("effective_until"):
            data["effective_until"] = dt_date.fromisoformat(
                data["effective_until"]
            )
        return service.create_schedule_breaks(
            data,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.delete(
    "/schedule-breaks/{break_id}", status_code=status.HTTP_204_NO_CONTENT
)
def deactivate_schedule_break(
    break_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Деактивировать перерыв (is_active=False)."""
    role = _sup_role(current_user)
    try:
        service.deactivate_schedule_break(
            break_id,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post(
    "/schedule-exceptions",
    response_model=ScheduleExceptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule_exception(
    body: ScheduleExceptionCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать разовое исключение (day_off / unavailable / extra_availability)."""
    role = _sup_role(current_user)
    try:
        data = body.model_dump()
        from datetime import time as dt_time, date as dt_date
        data["exception_date"] = dt_date.fromisoformat(data["exception_date"])
        if data.get("start_time"):
            data["start_time"] = dt_time.fromisoformat(data["start_time"])
        if data.get("end_time"):
            data["end_time"] = dt_time.fromisoformat(data["end_time"])
        return service.create_schedule_exception(
            data,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get(
    "/schedule-exceptions", response_model=list[ScheduleExceptionRead]
)
def list_schedule_exceptions(
    psychologist_id: int = Query(...),
    date_from: str = Query(default=None, description="YYYY-MM-DD"),
    date_to: str = Query(default=None, description="YYYY-MM-DD"),
):
    """Список разовых изменений психолога (новейшая дата первой)."""
    from datetime import date as dt_date
    try:
        df = dt_date.fromisoformat(date_from) if date_from else None
        dt = dt_date.fromisoformat(date_to) if date_to else None
    except ValueError:
        raise HTTPException(
            status_code=422, detail="Некорректная дата (YYYY-MM-DD)"
        )
    return service.list_schedule_exceptions(psychologist_id, df, dt)


# ── GroupSessions ──────────────────────────────────────────────────────────────

@router.get("/group-sessions", response_model=PaginatedGroupSessionsResponse)
def list_group_sessions(
    page:         int  = Query(default=1, ge=1),
    size:         int  = Query(default=20, ge=1, le=100),
    include_past: bool = Query(default=True),
):
    """Список групповых занятий (supervisor видит все, включая прошедшие)."""
    items, total = service.list_group_sessions(
        page=page,
        size=size,
        include_past=include_past,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.post(
    "/group-sessions",
    response_model=GroupSessionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_group_session(
    body:         GroupSessionCreate,
    request:      Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать групповое занятие."""
    role = _sup_role(current_user)
    try:
        data = body.model_dump()
        data["created_by"] = current_user["id"]
        return service.create_group_session(
            data,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/group-sessions/{uuid}", response_model=GroupSessionRead)
def update_group_session(
    uuid: str,
    body: GroupSessionUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Обновить групповое занятие (частичное обновление).

    `status` принимает только стабильный enum; допустим лишь переход
    scheduled→cancelled ('completed' — за system maintenance).
    """
    role = _sup_role(current_user)
    try:
        return service.update_group_session(
            uuid, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.patch("/group-sessions/{uuid}/booking", response_model=GroupSessionRead)
def set_group_session_booking(
    uuid:    str,
    request: Request,
    enabled: bool = Query(..., description="true = открыть запись, false = закрыть"),
    current_user: dict = Depends(get_current_user),
):
    """Открыть или закрыть запись на групповое занятие."""
    role = _sup_role(current_user)
    try:
        return service.set_group_session_booking(
            uuid, enabled,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.AppointmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
