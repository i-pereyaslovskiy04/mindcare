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


def log_message_edited(
    *,
    actor_id:          int,
    actor_role:        str,
    conversation_id:   int,
    conversation_uuid: str,
    message_id:        int,
    message_uuid:      str,
) -> None:
    """Факт редактирования сообщения (Stage 31x). Soft-fail: сбой audit не ломает
    правку (consistent с log_conversation_created). Метаданные ТОЛЬКО технические —
    ни старого, ни нового текста, ни ciphertext."""
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                user_id=actor_id,
                user_role=actor_role,
                event_type="chat_message_edited",
                entity_type="chat_message",
                entity_id=message_id,
                description=f"chat_message_edited: id={message_id}",
                log_metadata={
                    "conversation_uuid": conversation_uuid,
                    "conversation_id":   conversation_id,
                    "message_uuid":      message_uuid,
                    "actor_id":          actor_id,
                },
            ))
            db.commit()
    except Exception as exc:
        print(
            f"[AUDIT FAIL] chat_message_edited "
            f"(message id={message_id}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def log_message_deleted(
    *,
    actor_id:          int,
    actor_role:        str,
    conversation_id:   int,
    conversation_uuid: str,
    message_id:        int,
    message_uuid:      str,
) -> None:
    """Факт удаления (soft delete) сообщения (Stage 31y). Soft-fail: сбой audit
    не ломает удаление (consistent с log_message_edited). Метаданные ТОЛЬКО
    технические — ни текста, ни ciphertext."""
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                user_id=actor_id,
                user_role=actor_role,
                event_type="chat_message_deleted",
                entity_type="chat_message",
                entity_id=message_id,
                description=f"chat_message_deleted: id={message_id}",
                log_metadata={
                    "conversation_uuid": conversation_uuid,
                    "conversation_id":   conversation_id,
                    "message_uuid":      message_uuid,
                    "actor_id":          actor_id,
                },
            ))
            db.commit()
    except Exception as exc:
        print(
            f"[AUDIT FAIL] chat_message_deleted "
            f"(message id={message_id}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def log_attachment_uploaded(
    *,
    actor_id:          int,
    actor_role:        str,
    conversation_id:   int,
    conversation_uuid: str,
    attachment_uuid:   str,
    file_size:         int,
    mime_type:         str,
) -> None:
    """Факт загрузки вложения (Stage 32c). Soft-fail.
    Не логируется: storage_key, original_filename, checksum, содержимое файла."""
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                user_id=actor_id,
                user_role=actor_role,
                event_type="chat_attachment_uploaded",
                entity_type="chat_attachment",
                description=f"chat_attachment_uploaded: uuid={attachment_uuid}",
                log_metadata={
                    "conversation_uuid": conversation_uuid,
                    "conversation_id":   conversation_id,
                    "attachment_uuid":   attachment_uuid,
                    "file_size":         file_size,
                    "mime_type":         mime_type,
                },
            ))
            db.commit()
    except Exception as exc:
        print(
            f"[AUDIT FAIL] chat_attachment_uploaded "
            f"(uuid={attachment_uuid}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def log_attachment_downloaded(
    *,
    actor_id:          int,
    actor_role:        str,
    conversation_id:   int,
    conversation_uuid: str,
    attachment_uuid:   str,
    mime_type:         str,
) -> None:
    """Факт скачивания вложения (Stage 32c). Soft-fail.
    Не логируется: storage_key, original_filename, содержимое файла."""
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                user_id=actor_id,
                user_role=actor_role,
                event_type="chat_attachment_downloaded",
                entity_type="chat_attachment",
                description=f"chat_attachment_downloaded: uuid={attachment_uuid}",
                log_metadata={
                    "conversation_uuid": conversation_uuid,
                    "conversation_id":   conversation_id,
                    "attachment_uuid":   attachment_uuid,
                    "mime_type":         mime_type,
                },
            ))
            db.commit()
    except Exception as exc:
        print(
            f"[AUDIT FAIL] chat_attachment_downloaded "
            f"(uuid={attachment_uuid}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def log_system_conversation_created(
    *,
    recipient_id:      int,
    conversation_id:   int,
    conversation_uuid: str,
) -> None:
    """Одно событие на создание system-беседы. Без content / event text / ciphertext."""
    try:
        with SessionLocal() as db:
            db.add(AuditLog(
                user_id=recipient_id,
                event_type="system_conversation_created",
                entity_type="chat_conversation",
                entity_id=conversation_id,
                description=f"system_conversation_created: id={conversation_id}",
                log_metadata={"conversation_uuid": conversation_uuid},
            ))
            db.commit()
    except Exception as exc:
        print(
            f"[AUDIT FAIL] system_conversation_created "
            f"(conversation id={conversation_id}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
