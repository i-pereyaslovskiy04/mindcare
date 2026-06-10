"""
Session notes API.
Доступ: только аутентифицированные пользователи с ролями psychologist / admin / supervisor.
  - POST / PATCH  → только psychologist (только свои заметки)
  - GET           → psychologist (свои), admin / supervisor (все)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Optional

from app.auth.deps import get_current_user, require_role
from app.session_notes import service
from app.session_notes.schemas import (
    PaginatedNotesResponse,
    SessionNoteCreate,
    SessionNoteRead,
    SessionNoteUpdate,
)

router = APIRouter(
    prefix="/session-notes",
    tags=["session-notes"],
    dependencies=[Depends(require_role("psychologist", "admin", "supervisor"))],
)


@router.post("", response_model=SessionNoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    body:         SessionNoteCreate,
    current_user: dict = Depends(require_role("psychologist")),
):
    try:
        return service.create_note(body.model_dump(), author_id=current_user["id"])
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сохранить заметку",
        )


@router.get("", response_model=PaginatedNotesResponse)
def list_notes(
    page:           int           = Query(default=1, ge=1),
    size:           int           = Query(default=20, ge=1, le=100),
    appointment_id: Optional[int] = Query(default=None),
    engagement_id:  Optional[int] = Query(default=None),
    author_id:      Optional[int] = Query(default=None),
    current_user:   dict          = Depends(get_current_user),
):
    try:
        items, total = service.list_notes(
            page=page,
            size=size,
            appointment_id=appointment_id,
            engagement_id=engagement_id,
            filter_author_id=author_id,
            current_user=current_user,
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить заметки",
        )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{note_id}", response_model=SessionNoteRead)
def get_note(
    note_id:      int,
    current_user: dict = Depends(get_current_user),
):
    try:
        return service.get_note(note_id, current_user=current_user)
    except service.NoteNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заметка не найдена")
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить заметку",
        )


@router.patch("/{note_id}", response_model=SessionNoteRead)
def update_note(
    note_id:      int,
    body:         SessionNoteUpdate,
    current_user: dict = Depends(require_role("psychologist")),
):
    try:
        return service.update_note(
            note_id, body.model_dump(exclude_unset=True), current_user=current_user,
        )
    except service.NoteNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заметка не найдена")
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить заметку",
        )
