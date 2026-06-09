"""
Эндпоинты кабинета психолога.
Доступ: только роль psychologist.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.auth.deps import get_current_user, require_role
from app.psychologist import storage
from app.psychologist.schemas import MyStudentDetail, PaginatedMyStudentsResponse

router = APIRouter(
    prefix="/psychologist",
    tags=["psychologist"],
    dependencies=[Depends(require_role("psychologist"))],
)


@router.get("/students/{student_id}", response_model=MyStudentDetail)
def get_student_detail(
    student_id:   int,
    current_user: dict = Depends(get_current_user),
):
    """
    Детальная карточка студента, назначенного текущему психологу.
    Возвращает 404 если студент не найден или назначен другому психологу.
    """
    detail = storage.get_my_student_detail(
        psychologist_id=current_user["id"],
        student_id=student_id,
    )
    if detail is None:
        raise HTTPException(status_code=404, detail="Студент не найден или не назначен вам")
    return detail


@router.get("/students", response_model=PaginatedMyStudentsResponse)
def list_my_students(
    page:   int           = Query(default=1, ge=1),
    size:   int           = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=200),
    current_user: dict    = Depends(get_current_user),
):
    """
    Список студентов, назначенных текущему психологу через активные therapy_engagements.
    Поддерживает поиск по ФИО и email.
    """
    items, total = storage.get_my_students(
        psychologist_id=current_user["id"],
        search=search,
        page=page,
        size=size,
    )
    return {"items": items, "total": total, "page": page, "size": size}
