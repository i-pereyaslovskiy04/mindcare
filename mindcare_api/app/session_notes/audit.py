"""
Audit-события session_notes → audit_log (Stage 25b, H3).

Главное событие — session_note_content_read: каждый staff-доступ
(supervisor) к расшифрованному терапевтическому content фиксируется.

ВАЖНО: хелпер принимает только идентификаторы/метаданные — plaintext
content не попадает в сигнатуру by design и не должен логироваться
ни в description, ни в metadata, ни в stdout.

Паттерн «мягкого» аудита как в app/auth/audit.py: сбой записи не ломает
основной flow, но уходит в stderr для мониторинга.
"""

import sys
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import AuditLog


def log_note_event(
    event_type: str,
    *,
    actor_id:       int,
    actor_role:     str,
    note_id:        int,
    author_id:      Optional[int] = None,
    engagement_id:  Optional[int] = None,
    appointment_id: Optional[int] = None,
    ip:             Optional[str] = None,
    user_agent:     Optional[str] = None,
) -> None:
    """
    Пишет событие в audit_log:
      event_type  — session_note_content_read / session_note_created /
                    session_note_updated
      entity_type — "session_note", entity_id — id заметки
      metadata    — author_id / engagement_id / appointment_id (без content)
    """
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                user_id=actor_id,
                user_role=actor_role,
                event_type=event_type,
                entity_type="session_note",
                entity_id=note_id,
                description=f"{event_type}: note id={note_id}",
                log_metadata={
                    "author_id":      author_id,
                    "engagement_id":  engagement_id,
                    "appointment_id": appointment_id,
                },
                ip_address=ip,
                user_agent=user_agent,
            ))
            db.commit()
    except Exception as exc:
        print(
            f"[AUDIT FAIL] {event_type} (note id={note_id}): "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
