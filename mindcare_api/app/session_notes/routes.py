"""
Session notes API.
Доступ: только аутентифицированные пользователи с ролями psychologist / admin / supervisor.

Политика доступа (Stage 25b, вариант B) + multi-role (ADR-018):
  - POST / PATCH  → только psychologist (только свои заметки)
  - GET list      → psychologist: свои с content;
                    admin/supervisor: metadata-only (без content, без decrypt)
  - GET by id     → psychologist: свои с content;
                    supervisor: content + audit-событие session_note_content_read;
                    admin: metadata-only (content_available=false)
  - DELETE        → эндпоинта нет (намеренно)

Для multi-role пользователя policy-ветка/audit выбираются через
`service._resolve_notes_role`: заголовок `X-Active-Role` (активный кабинет)
валидируется по membership (невалидная роль → 403, не тихий fallback); без
заголовка — единственная policy-роль или консервативный default. См. docstring
service.py.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from typing import Optional, Union

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.session_notes import service
from app.session_notes.schemas import (
    PaginatedNotesMetaResponse,
    PaginatedNotesResponse,
    SessionNoteCreate,
    SessionNoteMetaRead,
    SessionNoteRead,
    SessionNoteUpdate,
)

router = APIRouter(
    prefix="/session-notes",
    tags=["session-notes"],
    dependencies=[Depends(require_role("psychologist", "admin", "supervisor"))],
)


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("", response_model=SessionNoteRead, status_code=status.HTTP_201_CREATED)
def create_note(
    body:         SessionNoteCreate,
    request:      Request,
    current_user: dict = Depends(require_role("psychologist")),
):
    try:
        return service.create_note(
            body.model_dump(),
            author_id=int(current_user["id"]),
            actor_role=resolve_role_or_403(
                current_user, allowed={"psychologist"}, preferred="psychologist",
            ),
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось сохранить заметку",
        )


@router.get(
    "",
    response_model=Union[PaginatedNotesResponse, PaginatedNotesMetaResponse],
)
def list_notes(
    page:           int           = Query(default=1, ge=1),
    size:           int           = Query(default=20, ge=1, le=100),
    appointment_id: Optional[int] = Query(default=None),
    engagement_id:  Optional[int] = Query(default=None),
    author_id:      Optional[int] = Query(default=None),
    current_user:   dict          = Depends(get_current_user),
    x_active_role:  Optional[str] = Header(default=None, alias="X-Active-Role"),
):
    try:
        items, total = service.list_notes(
            page=page,
            size=size,
            appointment_id=appointment_id,
            engagement_id=engagement_id,
            filter_author_id=author_id,
            current_user=current_user,
            requested_role=x_active_role,
        )
    except service.NotesAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить заметки",
        )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{note_id}", response_model=Union[SessionNoteRead, SessionNoteMetaRead])
def get_note(
    note_id:      int,
    request:      Request,
    current_user: dict = Depends(get_current_user),
    x_active_role: Optional[str] = Header(default=None, alias="X-Active-Role"),
):
    try:
        return service.get_note(
            note_id,
            current_user=current_user,
            requested_role=x_active_role,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.NotesAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
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
    request:      Request,
    current_user: dict = Depends(require_role("psychologist")),
):
    try:
        return service.update_note(
            note_id,
            body.model_dump(exclude_unset=True),
            author_id=int(current_user["id"]),
            actor_role=resolve_role_or_403(
                current_user, allowed={"psychologist"}, preferred="psychologist",
            ),
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except service.NotesAccessError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except service.NoteNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Заметка не найдена")
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось обновить заметку",
        )
