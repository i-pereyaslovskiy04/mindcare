from typing import Optional

from app.session_notes import storage


class NoteNotFound(Exception):
    pass


def create_note(data: dict, author_id: int) -> dict:
    return storage.create_note(
        author_id=author_id,
        appointment_id=data.get("appointment_id"),
        engagement_id=data.get("engagement_id"),
        note_type=data.get("note_type", "general"),
        content=data["content"],
        is_shared_with_client=data.get("is_shared_with_client", False),
    )


def get_note(note_id: int, *, current_user: dict) -> dict:
    role = current_user["role"]
    if role in ("admin", "supervisor"):
        note = storage.get_note_by_id(note_id)
    else:
        note = storage.get_note_by_id(note_id, author_id=current_user["id"])
    if not note:
        raise NoteNotFound()
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
        author_scope = filter_author_id   # None = all; specific id = filtered
    else:
        author_scope = current_user["id"]  # psychologist always sees own notes only

    return storage.find_notes(
        page=page,
        size=size,
        author_id=author_scope,
        appointment_id=appointment_id,
        engagement_id=engagement_id,
    )


def update_note(note_id: int, data: dict, *, current_user: dict) -> dict:
    note = storage.update_note(note_id, data, author_id=current_user["id"])
    if not note:
        raise NoteNotFound()
    return note
