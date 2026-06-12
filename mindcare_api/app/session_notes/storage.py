from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc

from app.db.session import SessionLocal
from app.db.models import SessionNote
from app.core.encryption import decrypt_text, encrypt_text


def _note_to_dict(note: SessionNote) -> dict:
    """Build response dict with decrypted content. Does NOT mutate the ORM object."""
    try:
        plaintext = decrypt_text(note.content)
    except (ValueError, RuntimeError) as exc:
        raise RuntimeError(f"Note decryption failed (id={note.id})") from exc

    return {
        "id":                    note.id,
        "uuid":                  str(note.uuid),
        "appointment_id":        note.appointment_id,
        "engagement_id":         note.engagement_id,
        "author_id":             note.author_id,
        "note_type":             note.note_type,
        "content":               plaintext,
        "is_shared_with_client": note.is_shared_with_client,
        "version":               note.version,
        "created_at":            note.created_at,
        "updated_at":            note.updated_at,
    }


def _note_to_meta_dict(note: SessionNote) -> dict:
    """
    Metadata-only dict: терапевтический content не включается и
    decrypt_text НЕ вызывается вообще (не падает на битых записях,
    не расшифровывает то, что роль не должна видеть).
    """
    return {
        "id":                    note.id,
        "uuid":                  str(note.uuid),
        "appointment_id":        note.appointment_id,
        "engagement_id":         note.engagement_id,
        "author_id":             note.author_id,
        "note_type":             note.note_type,
        "is_shared_with_client": note.is_shared_with_client,
        "version":               note.version,
        "created_at":            note.created_at,
        "updated_at":            note.updated_at,
        "content_available":     False,
    }


def create_note(
    *,
    author_id:             int,
    appointment_id:        Optional[int],
    engagement_id:         Optional[int],
    note_type:             str,
    content:               str,
    is_shared_with_client: bool,
) -> dict:
    with SessionLocal() as db:
        note = SessionNote(
            author_id=author_id,
            appointment_id=appointment_id,
            engagement_id=engagement_id,
            note_type=note_type,
            content=encrypt_text(content),
            is_shared_with_client=is_shared_with_client,
        )
        db.add(note)
        db.commit()
        db.refresh(note)
        return _note_to_dict(note)


def get_note_by_id(
    note_id: int,
    *,
    author_id: Optional[int] = None,
    include_content: bool = True,
) -> Optional[dict]:
    """
    Returns note dict or None. author_id scopes the query to own notes
    when provided. include_content=False возвращает metadata-only dict
    без вызова decrypt (permission-фильтры применяются до выборки).
    """
    with SessionLocal() as db:
        q = db.query(SessionNote).filter(SessionNote.id == note_id)
        if author_id is not None:
            q = q.filter(SessionNote.author_id == author_id)
        note = q.first()
        if not note:
            return None
        return _note_to_dict(note) if include_content else _note_to_meta_dict(note)


def find_notes(
    *,
    page:            int           = 1,
    size:            int           = 20,
    author_id:       Optional[int] = None,
    appointment_id:  Optional[int] = None,
    engagement_id:   Optional[int] = None,
    include_content: bool          = True,
) -> tuple[list[dict], int]:
    with SessionLocal() as db:
        q = db.query(SessionNote)
        if author_id is not None:
            q = q.filter(SessionNote.author_id == author_id)
        if appointment_id is not None:
            q = q.filter(SessionNote.appointment_id == appointment_id)
        if engagement_id is not None:
            q = q.filter(SessionNote.engagement_id == engagement_id)

        total = q.count()
        notes = (
            q.order_by(desc(SessionNote.created_at))
            .offset((page - 1) * size)
            .limit(size)
            .all()
        )
        mapper = _note_to_dict if include_content else _note_to_meta_dict
        items = [mapper(n) for n in notes]

    return items, total


def update_note(
    note_id:   int,
    data:      dict,
    *,
    author_id: Optional[int] = None,
) -> Optional[dict]:
    """
    Updates fields present in data (exclude_unset semantics from routes).
    author_id scopes the query to own notes when provided.
    content is re-encrypted on change; version increments on content change.
    """
    with SessionLocal() as db:
        q = db.query(SessionNote).filter(SessionNote.id == note_id)
        if author_id is not None:
            q = q.filter(SessionNote.author_id == author_id)
        note = q.first()
        if not note:
            return None

        if "content" in data and data["content"] is not None:
            note.content = encrypt_text(data["content"])
            note.version = (note.version or 1) + 1
        if "is_shared_with_client" in data:
            note.is_shared_with_client = data["is_shared_with_client"]
        if "note_type" in data and data["note_type"] is not None:
            note.note_type = data["note_type"]

        note.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(note)
        return _note_to_dict(note)
