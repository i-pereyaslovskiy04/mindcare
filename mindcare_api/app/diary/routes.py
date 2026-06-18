"""
Diary API.

Доступ: только студент (role=student).
  Другие роли (psychologist, supervisor, admin) → 403 на уровне роутера.

Endpoints:
  GET  /api/diary/emotions  — активный справочник эмоций
  GET  /api/diary/today     — запись текущего дня (или пустая структура)
  PUT  /api/diary/today     — создать / обновить запись текущего дня
  GET  /api/diary/entries   — история записей (limit/offset)
  GET  /api/diary/summary   — агрегат для графика (period=14d|month|year)
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.deps import require_role
from app.diary import service
from app.diary.schemas import (
    DiaryEntryRead,
    DiaryEntryWrite,
    DiarySummaryRead,
    EmotionRead,
    PaginatedEntriesResponse,
)

router = APIRouter(
    prefix="/diary",
    tags=["diary"],
    dependencies=[Depends(require_role("student"))],
)


@router.get("/emotions", response_model=List[EmotionRead])
def get_emotions():
    return service.get_emotions()


@router.get("/today", response_model=DiaryEntryRead)
def get_today(
    current_user: dict = Depends(require_role("student")),
):
    return service.get_today(student_id=current_user["id"])


@router.put("/today", response_model=DiaryEntryRead)
def put_today(
    body:         DiaryEntryWrite,
    current_user: dict = Depends(require_role("student")),
):
    try:
        return service.upsert_today(student_id=current_user["id"], data=body)
    except service.InvalidEmotionKey as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )


@router.get("/entries", response_model=PaginatedEntriesResponse)
def get_entries(
    limit:        int  = Query(default=10, ge=1, le=100),
    offset:       int  = Query(default=0,  ge=0),
    current_user: dict = Depends(require_role("student")),
):
    items, total = service.get_entries(
        student_id=current_user["id"], limit=limit, offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/summary", response_model=DiarySummaryRead)
def get_summary(
    period:       str  = Query(default="14d"),
    current_user: dict = Depends(require_role("student")),
):
    try:
        return service.get_summary(student_id=current_user["id"], period=period)
    except service.InvalidPeriod:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Неизвестный период. Допустимые значения: 14d, month, year",
        )
