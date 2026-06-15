"""
Access policy session_notes (Stage 25b, политика B):

  psychologist — create/list/get/update только свои заметки, с content;
  supervisor   — list: metadata-only (без decrypt);
                 get by id: content разрешён, КАЖДЫЙ такой read → audit_log;
  admin        — list и get: metadata-only, decrypt не вызывается вообще;
                 доступ к терапевтическому content админу не предоставляется
                 (возможный break-glass — отдельное compliance-решение);
  student      — 403 на уровне роутера (require_role).

Plaintext content не логируется нигде; audit-хелпер принимает только id/метаданные.
"""

from typing import Optional

from app.session_notes import storage
from app.session_notes.audit import log_note_event


class NoteNotFound(Exception):
    pass


def create_note(
    data: dict,
    author_id: int,
    *,
    actor_role: str = "psychologist",
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    note = storage.create_note(
        author_id=author_id,
        appointment_id=data.get("appointment_id"),
        engagement_id=data.get("engagement_id"),
        note_type=data.get("note_type", "general"),
        content=data["content"],
        is_shared_with_client=data.get("is_shared_with_client", False),
    )
    log_note_event(
        "session_note_created",
        actor_id=author_id,
        actor_role=actor_role,
        note_id=note["id"],
        author_id=note["author_id"],
        engagement_id=note["engagement_id"],
        appointment_id=note["appointment_id"],
        ip=ip,
        user_agent=user_agent,
    )
    return note


def get_note(
    note_id: int,
    *,
    current_user: dict,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    role = current_user["role"]

    if role == "admin":
        # Metadata-only: decrypt не вызывается, content недоступен
        note = storage.get_note_by_id(note_id, include_content=False)
    elif role == "supervisor":
        note = storage.get_note_by_id(note_id)
    else:
        # psychologist: только свои (чужая заметка неотличима от несуществующей)
        note = storage.get_note_by_id(note_id, author_id=current_user["id"])

    if not note:
        raise NoteNotFound()

    if role == "supervisor":
        # Staff-доступ к расшифрованному терапевтическому content — в audit
        log_note_event(
            "session_note_content_read",
            actor_id=int(current_user["id"]),
            actor_role=role,
            note_id=note["id"],
            author_id=note["author_id"],
            engagement_id=note["engagement_id"],
            appointment_id=note["appointment_id"],
            ip=ip,
            user_agent=user_agent,
        )

    return note


def list_notes(
    page:             int,
    size:             int,
    appointment_id:   Optional[int],
    engagement_id:    Optional[int],
    filter_author_id: Optional[int],
    *,
    current_user: dict,
) -> tuple[list[dict], int]:
    role = current_user["role"]

    if role in ("admin", "supervisor"):
        # Staff-список — metadata-only: без content и без decrypt.
        # Content для supervisor доступен только поштучно (GET by id, под audit).
        return storage.find_notes(
            page=page,
            size=size,
            author_id=filter_author_id,   # None = все; конкретный id = фильтр
            appointment_id=appointment_id,
            engagement_id=engagement_id,
            include_content=False,
        )

    # psychologist: всегда только свои, с content
    return storage.find_notes(
        page=page,
        size=size,
        author_id=current_user["id"],
        appointment_id=appointment_id,
        engagement_id=engagement_id,
    )


def update_note(
    note_id: int,
    data: dict,
    *,
    current_user: dict,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    note = storage.update_note(note_id, data, author_id=current_user["id"])
    if not note:
        raise NoteNotFound()
    log_note_event(
        "session_note_updated",
        actor_id=int(current_user["id"]),
        actor_role=current_user["role"],
        note_id=note["id"],
        author_id=note["author_id"],
        engagement_id=note["engagement_id"],
        appointment_id=note["appointment_id"],
        ip=ip,
        user_agent=user_agent,
    )
    return note
