"""
ADR-035 — общие помощники integration-тестов заметок карточки клиента
(не тест-модуль). Заметки удаляются каскадом вместе с автором (integ_-users).
"""
import uuid

from app.core.encryption import encrypt_text
from app.db.models import SessionNote
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import auth, uuid_of

NOTE_SECRET = "Секрет-заметки-о-тревоге-5d1e"


def notes_url(client_uid):
    return f"/api/psychologist/clients/{uuid_of(client_uid)}/notes"


def create_note(client, token, client_uid, content=NOTE_SECRET, **extra):
    return client.post(notes_url(client_uid), headers=auth(token),
                       json={"content": content, **extra})


def patch_note(client, token, client_uid, note_uuid, **body):
    return client.patch(f"{notes_url(client_uid)}/{note_uuid}", headers=auth(token), json=body)


def generic_patch(client, token, note_id, **body):
    return client.patch(f"/api/session-notes/{note_id}", headers=auth(token), json=body)


def note_row(note_uuid):
    with SessionLocal() as db:
        n = db.query(SessionNote).filter(SessionNote.uuid == uuid.UUID(str(note_uuid))).one()
        db.expunge(n)
        return n


def insert_note(author_id, *, engagement_id=None, appointment_id=None, content=NOTE_SECRET):
    """Прямой insert (в т.ч. заведомо противоречивой старой записи)."""
    with SessionLocal() as db:
        n = SessionNote(
            author_id=author_id, engagement_id=engagement_id, appointment_id=appointment_id,
            note_type="general", content=encrypt_text(content), is_shared_with_client=False,
        )
        db.add(n)
        db.commit()
        return n.id, str(n.uuid), n.content
