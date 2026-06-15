"""
Бизнес-логика Chat MVP (Stage 28c).

Политика доступа:
  student      — только своя беседа (по своему engagement); запись только
                 при engagement.status == 'active';
  psychologist — беседы только своих engagements; запись только если он
                 текущий психолог активного engagement;
  admin / supervisor — доступа к чату НЕТ (403 на уровне роутера);
                 content им не предоставляется; break-glass — отдельное
                 future compliance-решение.

Закрытый engagement: чтение истории участникам разрешено, запись — 409.
Чужая/несуществующая беседа неотличимы (404).

content шифруется в storage (encrypt-on-write); decrypt — только после
проверок прав в этом слое. Plaintext не логируется.
"""

import uuid as _uuid
from typing import Optional

from app.chat import storage
from app.chat.audit import log_conversation_created


class ChatError(Exception):
    """Ошибка бизнес-логики чата с HTTP-статусом."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


_NOT_FOUND = "Диалог не найден"
_CLOSED = "Диалог закрыт: консультационная связь завершена"


def _conversation_read_dict(conv, eng, *, current_user_id: int) -> dict:
    """Собирает ChatConversationRead для участника."""
    partner_id = (
        eng.psychologist_id if current_user_id == eng.client_id else eng.client_id
    )
    partner = storage.get_user_brief(partner_id) or {
        "id": partner_id, "full_name": "—",
    }
    return {
        "uuid":              str(conv.uuid),
        "partner":           partner,
        "engagement_status": eng.status,
        "last_message_at":   conv.last_message_at,
        "unread_count":      storage.unread_count(
            conv.id, user_id=current_user_id,
        ),
        "peer_is_online":    storage.is_user_online(partner_id),
    }


# ─── Student ──────────────────────────────────────────────────────────────────

def _resolve_student_conversation(student_id: int, *, create: bool = False):
    """
    Возвращает (conversation, engagement) студента или (None, engagement|None).

    create=True — lazy-create беседы, но ТОЛЬКО для активного engagement;
    для исторического engagement без существующей беседы ничего не создаётся.
    """
    eng = storage.get_engagement_for_student(student_id)
    if eng is None:
        return None, None

    conv = storage.get_conversation_for_engagement(eng.id)
    if conv is None and create and eng.status == "active":
        conv, _created = storage.get_or_create_conversation(eng.id)
    return conv, eng


def get_my_conversation(
    current_user: dict,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    student_id = int(current_user["id"])
    eng = storage.get_engagement_for_student(student_id)
    if eng is None:
        return {"conversation": None}

    conv = storage.get_conversation_for_engagement(eng.id)
    if conv is None:
        if eng.status != "active":
            return {"conversation": None}
        conv, created = storage.get_or_create_conversation(eng.id)
        if created:
            log_conversation_created(
                actor_id=student_id,
                actor_role=current_user["role"],
                conversation_id=conv.id,
                conversation_uuid=str(conv.uuid),
                engagement_id=eng.id,
                ip=ip,
                user_agent=user_agent,
            )

    return {
        "conversation": _conversation_read_dict(
            conv, eng, current_user_id=student_id,
        ),
    }


def get_my_messages(
    current_user: dict,
    *,
    limit: int,
    before_id: Optional[int],
    after_id: Optional[int],
) -> list[dict]:
    student_id = int(current_user["id"])
    conv, eng = _resolve_student_conversation(student_id)
    if conv is None or eng is None:
        raise ChatError(_NOT_FOUND, status_code=404)

    return storage.get_messages(
        conv.id,
        current_user_id=student_id,
        client_id=eng.client_id,
        limit=limit,
        before_id=before_id,
        after_id=after_id,
    )


def send_my_message(
    current_user: dict,
    content: str,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    student_id = int(current_user["id"])
    eng = storage.get_engagement_for_student(student_id)
    if eng is None:
        raise ChatError(_NOT_FOUND, status_code=404)
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)

    conv, created = storage.get_or_create_conversation(eng.id)
    if created:
        log_conversation_created(
            actor_id=student_id,
            actor_role=current_user["role"],
            conversation_id=conv.id,
            conversation_uuid=str(conv.uuid),
            engagement_id=eng.id,
            ip=ip,
            user_agent=user_agent,
        )

    return storage.create_message(
        conv.id,
        sender_id=student_id,        # только из сессии — spoof невозможен
        content=content,
        client_id=eng.client_id,
    )


def mark_my_read(current_user: dict) -> int:
    student_id = int(current_user["id"])
    conv, _eng = _resolve_student_conversation(student_id)
    if conv is None:
        raise ChatError(_NOT_FOUND, status_code=404)
    return storage.mark_read(conv.id, reader_id=student_id)


# ─── Psychologist ─────────────────────────────────────────────────────────────

def list_conversations(current_user: dict, *, page: int, size: int) -> tuple[list[dict], int]:
    return storage.list_conversations_for_psychologist(
        int(current_user["id"]), page=page, size=size,
    )


def _resolve_psychologist_conversation(psychologist_id: int, conversation_uuid: str):
    """(conversation, engagement) если психолог — участник, иначе 404."""
    try:
        _uuid.UUID(conversation_uuid)
    except ValueError:
        raise ChatError(_NOT_FOUND, status_code=404)

    row = storage.get_conversation_by_uuid(conversation_uuid)
    if row is None:
        raise ChatError(_NOT_FOUND, status_code=404)
    conv, eng = row
    if eng.psychologist_id != psychologist_id:
        # чужая беседа неотличима от несуществующей
        raise ChatError(_NOT_FOUND, status_code=404)
    return conv, eng


def get_conversation(current_user: dict, conversation_uuid: str) -> dict:
    psychologist_id = int(current_user["id"])
    conv, eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return _conversation_read_dict(conv, eng, current_user_id=psychologist_id)


def get_messages(
    current_user: dict,
    conversation_uuid: str,
    *,
    limit: int,
    before_id: Optional[int],
    after_id: Optional[int],
) -> list[dict]:
    psychologist_id = int(current_user["id"])
    conv, eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return storage.get_messages(
        conv.id,
        current_user_id=psychologist_id,
        client_id=eng.client_id,
        limit=limit,
        before_id=before_id,
        after_id=after_id,
    )


def send_message(current_user: dict, conversation_uuid: str, content: str) -> dict:
    psychologist_id = int(current_user["id"])
    conv, eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)

    return storage.create_message(
        conv.id,
        sender_id=psychologist_id,   # только из сессии
        content=content,
        client_id=eng.client_id,
    )


def mark_read(current_user: dict, conversation_uuid: str) -> int:
    psychologist_id = int(current_user["id"])
    conv, _eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return storage.mark_read(conv.id, reader_id=psychologist_id)


# ─── System conversation (Stage 29b) ────────────────────────────────────────
#
# Read-only. Доступна ТОЛЬКО своему получателю (любая авторизованная роль —
# к своей беседе). Чужую прочитать нельзя: запросы всегда скоупятся по
# current_user.id, отдельного conversation_uuid в API нет. Write-эндпоинта для
# пользователя нет: system-сообщения создаёт только internal publisher.

def get_my_system_conversation(current_user: dict) -> dict:
    user_id = int(current_user["id"])
    conv = storage.get_system_conversation(user_id)
    if conv is None:
        return {"conversation": None}
    return {
        "conversation": {
            "uuid":            str(conv.uuid),
            "type":            "system",
            "last_message_at": conv.last_message_at,
            "unread_count":    storage.system_unread_count(user_id),
        }
    }


def get_my_system_messages(
    current_user: dict,
    *,
    limit: int,
    before_id: Optional[int],
    after_id: Optional[int],
) -> list[dict]:
    user_id = int(current_user["id"])
    return storage.get_system_messages(
        user_id, limit=limit, before_id=before_id, after_id=after_id,
    )


def mark_my_system_read(current_user: dict) -> int:
    """Идемпотентно; не падает, если system-беседы ещё нет (вернёт 0)."""
    return storage.mark_system_read(int(current_user["id"]))
