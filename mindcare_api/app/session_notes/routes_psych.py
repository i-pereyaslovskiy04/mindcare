"""
Заметки психолога в карточке клиента (ADR-035) — существующий session_notes:
  GET   /api/psychologist/clients/{student_uuid}/notes
  POST  /api/psychologist/clients/{student_uuid}/notes
  PATCH /api/psychologist/clients/{student_uuid}/notes/{note_uuid}

Router-level: require_role("psychologist") и запрет impersonation. Право —
строгое активное сопровождение с активным клиентом (иначе 404). Видны и
правятся только СВОИ заметки, у которых каждая заполненная связь принадлежит
этому психологу и этому клиенту. Удаления и публикации клиенту нет.

Аудит: создание/правка — session_note_created/_updated (ATOMIC, в storage);
отказы — session_note_create_failed (access_denied — область/чужая встреча)
и session_note_update_failed (access_denied — область/нет заметки,
version_conflict). Чтение своих заметок события не пишет. Все ответы —
Cache-Control: no-store, private (NoStoreRoute); 422 тело не эхоит.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, require_role
from app.core.no_store_route import NoStoreRoute, audit_unavailable_response, no_store_json
from app.session_notes import service
from app.session_notes.guards import forbid_impersonation
from app.session_notes.schemas import (
    ClientNoteCreate, ClientNoteRead, ClientNotesPage, ClientNoteUpdate,
    ClientNoteUpdateRead,
)

router = APIRouter(
    prefix="/psychologist/clients",
    tags=["psychologist-session-notes"],
    route_class=NoStoreRoute,
    dependencies=[
        Depends(require_role("psychologist")),
        Depends(forbid_impersonation),
    ],
)

NOT_AVAILABLE = "Заметки клиента недоступны"


def _meta(request: Request):
    return (request.client.host if request.client else None), request.headers.get("user-agent")


def _failure(event: str, actor_id: int, code: str, ip, ua) -> None:
    record_secondary_failure(
        event=event,
        actor=Actor.user(int(actor_id), "psychologist"),
        failure_reason_code=code,
        context=build_request_context(ip=ip, user_agent=ua),
    )


@router.get("/{student_uuid}/notes", response_model=ClientNotesPage)
def list_client_notes(
    student_uuid: UUID,
    before: Optional[str] = Query(default=None, max_length=256),
    size:   int = Query(default=service.CLIENT_NOTES_DEFAULT_SIZE, ge=1,
                        le=service.CLIENT_NOTES_MAX_SIZE),
    current_user: dict = Depends(get_current_user),
):
    try:
        return service.list_client_notes(int(current_user["id"]), student_uuid, before, size)
    except service.InvalidCursor:
        return no_store_json(422, {"detail": "Некорректный курсор"})
    except service.ClientScopeUnavailable:
        return no_store_json(404, {"detail": NOT_AVAILABLE})


@router.post(
    "/{student_uuid}/notes", response_model=ClientNoteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_client_note(
    student_uuid: UUID,
    body: ClientNoteCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ip, ua = _meta(request)
    actor_id = int(current_user["id"])
    try:
        return service.create_client_note(
            actor_id, student_uuid, body.model_dump(),
            actor_role="psychologist", ip=ip, user_agent=ua,
        )
    except service.ClientScopeUnavailable:
        _failure("session_note_create_failed", actor_id, "access_denied", ip, ua)
        return no_store_json(404, {"detail": NOT_AVAILABLE})
    except service.NoteLinkInvalid as exc:
        _failure("session_note_create_failed", actor_id, exc.failure_reason, ip, ua)
        return no_store_json(422, {"detail": "Встреча недоступна для привязки заметки"})
    except AuditError:
        return audit_unavailable_response()


@router.patch("/{student_uuid}/notes/{note_uuid}", response_model=ClientNoteUpdateRead)
def update_client_note(
    student_uuid: UUID,
    note_uuid: UUID,
    body: ClientNoteUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    ip, ua = _meta(request)
    actor_id = int(current_user["id"])
    try:
        return service.update_client_note(
            actor_id, student_uuid, note_uuid, body.model_dump(exclude_unset=True),
            actor_role="psychologist", ip=ip, user_agent=ua,
        )
    except (service.ClientScopeUnavailable, service.NoteNotFound):
        _failure("session_note_update_failed", actor_id, "access_denied", ip, ua)
        return no_store_json(404, {"detail": "Заметка недоступна"})
    except service.NoteVersionConflict as exc:
        _failure("session_note_update_failed", actor_id, exc.failure_reason, ip, ua)
        return no_store_json(409, {
            "detail": "Заметку уже изменили. Обновите её и повторите правку.",
            "code": "note_version_conflict",
        })
    except AuditError:
        return audit_unavailable_response()
