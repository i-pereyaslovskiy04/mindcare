"""
Audit-события Chat MVP → audit_log.

Логируется только chat_conversation_created — одно событие на беседу.
Отправка/чтение сообщений намеренно НЕ логируются: сами chat_messages
(sender_id, created_at) и есть запись, дублирование = шум в партициях.

Plaintext content в сигнатуре отсутствует by design и не должен
попадать в audit ни в каком виде (паттерн session_notes/audit.py).
"""

import sys
from typing import Optional

from app.db.session import SessionLocal
from app.db.models import AuditLog


def log_conversation_created(
    *,
    actor_id:          int,
    actor_role:        str,
    conversation_id:   int,
    conversation_uuid: str,
    engagement_id:     int,
    ip:                Optional[str] = None,
    user_agent:        Optional[str] = None,
) -> None:
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                user_id=actor_id,
                user_role=actor_role,
                event_type="chat_conversation_created",
                entity_type="chat_conversation",
                entity_id=conversation_id,
                description=f"chat_conversation_created: id={conversation_id}",
                log_metadata={
                    "conversation_uuid": conversation_uuid,
                    "engagement_id":     engagement_id,
                },
                ip_address=ip,
                user_agent=user_agent,
            ))
            db.commit()
    except Exception as exc:
        print(
            f"[AUDIT FAIL] chat_conversation_created "
            f"(conversation id={conversation_id}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
