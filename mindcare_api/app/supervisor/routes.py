"""
Эндпоинты кабинета супервизора.
Доступ: только роли admin и supervisor.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import Optional

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.supervisor import service, storage
from app.supervisor.schemas import (
    EngagementClose,
    EngagementCreate,
    EngagementRead,
    EngagementTransfer,
    PaginatedEngagementsResponse,
    PaginatedPsychologistsResponse,
    PaginatedStudentsResponse,
    SupervisorStudentCreate,
    SupervisorStudentCreateResponse,
)

router = APIRouter(
    prefix="/supervisor",
    tags=["supervisor"],
    dependencies=[Depends(require_role("admin", "supervisor"))],
)


# ── Студенты ──────────────────────────────────────────────────────────────────

@router.get("/students", response_model=PaginatedStudentsResponse)
def list_students(
    page:   int            = Query(default=1, ge=1),
    size:   int            = Query(default=20, ge=1, le=100),
    search: Optional[str]  = Query(default=None, max_length=200),
):
    """
    Список активных студентов с информацией о назначенном психологе.
    Поддерживает поиск по ФИО и email.
    """
    items, total = storage.get_students(search=search, page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.post(
    "/students",
    response_model=SupervisorStudentCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_student(
    request:      Request,
    body:         SupervisorStudentCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Создать полноценный аккаунт студента (admin/supervisor) с временным паролем.

    personal_data_consent — staff подтверждает личное согласие студента на
    обработку ПДн (получено очно); фиксируется в consent_records (НЕ legal basis).
    Опциональный psychologist_id создаёт активную связь студент↔психолог.
    Карточка незарегистрированного студента с тем же email привязывается к аккаунту.
    """
    try:
        return service.create_student(
            full_name=body.full_name,
            email=body.email,
            phone=body.phone,
            psychologist_id=body.psychologist_id,
            primary_concern=body.primary_concern,
            actor_id=current_user["id"],
            actor_role=resolve_role_or_403(
                current_user, allowed={"admin", "supervisor"},
                preferred="supervisor",
            ),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.SupervisorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Психологи ─────────────────────────────────────────────────────────────────

@router.get("/psychologists", response_model=PaginatedPsychologistsResponse)
def list_psychologists(
    page:   int            = Query(default=1, ge=1),
    size:   int            = Query(default=100, ge=1, le=200),
    search: Optional[str]  = Query(default=None, max_length=200),
):
    """
    Список активных психологов. Поддерживает поиск по ФИО и email.
    Возвращает поле is_accepting из psychologist_profiles.
    """
    items, total = storage.get_psychologists(search=search, page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


# ── Список связок ─────────────────────────────────────────────────────────────

@router.get("/engagements", response_model=PaginatedEngagementsResponse)
def list_engagements(
    page:               int            = Query(default=1, ge=1),
    size:               int            = Query(default=20, ge=1, le=100),
    status:             Optional[str]  = Query(default=None),
    student_search:     Optional[str]  = Query(default=None, max_length=200),
    psychologist_search: Optional[str] = Query(default=None, max_length=200),
):
    """
    Список связок студент ↔ психолог с фильтрами по статусу, ФИО студента/психолога.
    """
    items, total = storage.get_engagements(
        status=status,
        student_search=student_search,
        psychologist_search=psychologist_search,
        page=page,
        size=size,
    )
    return {"items": items, "total": total, "page": page, "size": size}


# ── Назначить психолога ───────────────────────────────────────────────────────

@router.post(
    "/engagements",
    response_model=EngagementRead,
    status_code=status.HTTP_201_CREATED,
)
def create_engagement(
    body:         EngagementCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Назначить психолога студенту.
    Возвращает 409 если у студента уже есть активная связь.
    """
    try:
        return service.assign_psychologist(
            client_id=body.client_id,
            psychologist_id=body.psychologist_id,
            primary_concern=body.primary_concern,
            actor_id=current_user["id"],
            actor_role=resolve_role_or_403(
                current_user, allowed={"admin", "supervisor"},
                preferred="supervisor",
            ),
        )
    except service.SupervisorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Переназначить психолога ───────────────────────────────────────────────────

@router.patch("/engagements/{engagement_id}/transfer", response_model=EngagementRead)
def transfer_engagement(
    engagement_id: int,
    body:          EngagementTransfer,
    current_user:  dict = Depends(get_current_user),
):
    """
    Переназначить клиента на другого психолога.
    Закрывает текущую связь (status=transferred), создаёт новую (status=active).
    """
    try:
        return service.transfer_psychologist(
            engagement_id=engagement_id,
            new_psychologist_id=body.new_psychologist_id,
            transfer_reason=body.transfer_reason,
            actor_id=current_user["id"],
            actor_role=resolve_role_or_403(
                current_user, allowed={"admin", "supervisor"},
                preferred="supervisor",
            ),
        )
    except service.SupervisorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Закрыть связь ─────────────────────────────────────────────────────────────

@router.patch("/engagements/{engagement_id}/close", response_model=EngagementRead)
def close_engagement(
    engagement_id: int,
    body:          EngagementClose,
    current_user:  dict = Depends(get_current_user),
):
    """
    Закрыть активную связь (status=completed).
    """
    try:
        return service.close_engagement(
            engagement_id=engagement_id,
            reason=body.reason,
            actor_id=current_user["id"],
            actor_role=resolve_role_or_403(
                current_user, allowed={"admin", "supervisor"},
                preferred="supervisor",
            ),
        )
    except service.SupervisorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
