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
from pathlib import Path
from typing import Optional

from fastapi import UploadFile

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.auth.roles import effective_role
from app.chat import storage
from app.chat import attachment_service as _att_svc


class ChatError(Exception):
    """Ошибка бизнес-логики чата с HTTP-статусом."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _actor_role(current_user: dict, cabinet: str) -> str:
    """
    Роль актора для audit, scoped под кабинет endpoint-а (ADR-018).

    Chat-эндпоинты role-специфичны (require_role("student"/"psychologist")),
    поэтому актор действует как участник в конкретном кабинете. Берём именно
    эту роль из membership (а не случайную primary у multi-role пользователя).
    None здесь невозможен после require_role; если всё же None — 403, а не
    actor_role=None в audit.
    """
    role = effective_role(
        current_user.get("roles") or [], allowed={cabinet}, preferred=cabinet
    )
    if role is None:
        raise ChatError("Недостаточно прав для выполнения действия", status_code=403)
    return role


_NOT_FOUND = "Диалог не найден"
_CLOSED = "Диалог закрыт: чат завершён."


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
            record_event(
                event="chat_conversation_created",
                actor=Actor.user(student_id, _actor_role(current_user, "student")),
                target=Target("chat_conversation", conv.id),
                outcome=Outcome.SUCCESS,
                context=build_request_context(ip=ip, user_agent=user_agent),
                db=None,
            )
    elif eng.status != "active" and not storage.conversation_has_messages(conv.id):
        # Пустая неактивная (transferred/closed) беседа — артефакт, скрываем
        # её и от студента (Stage 31p), как и в списке психолога.
        return {"conversation": None}

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
    attachment_uuids: Optional[list] = None,
) -> dict:
    student_id = int(current_user["id"])
    eng = storage.get_engagement_for_student(student_id)
    if eng is None:
        raise ChatError(_NOT_FOUND, status_code=404)
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)

    conv, created = storage.get_or_create_conversation(eng.id)
    if created:
        record_event(
            event="chat_conversation_created",
            actor=Actor.user(student_id, _actor_role(current_user, "student")),
            target=Target("chat_conversation", conv.id),
            outcome=Outcome.SUCCESS,
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=None,
        )

    try:
        return storage.create_message(
            conv.id,
            sender_id=student_id,
            content=content,
            client_id=eng.client_id,
            attachment_uuids=attachment_uuids,
        )
    except ValueError as e:
        raise ChatError(str(e), status_code=400)


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


def send_message(
    current_user: dict,
    conversation_uuid: str,
    content: str,
    attachment_uuids: Optional[list] = None,
) -> dict:
    psychologist_id = int(current_user["id"])
    conv, eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)

    try:
        return storage.create_message(
            conv.id,
            sender_id=psychologist_id,
            content=content,
            client_id=eng.client_id,
            attachment_uuids=attachment_uuids,
        )
    except ValueError as e:
        raise ChatError(str(e), status_code=400)


def mark_read(current_user: dict, conversation_uuid: str) -> int:
    psychologist_id = int(current_user["id"])
    conv, _eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return storage.mark_read(conv.id, reader_id=psychologist_id)


# ─── Edit message (Stage 31x) ────────────────────────────────────────────────
#
# Политика: редактировать можно ТОЛЬКО своё user-сообщение и ТОЛЬКО пока
# engagement активен. Без ограничения по времени. system-сообщения и чужие
# правке недоступны. Все «нельзя» в активном чате (не найдено / чужое / system /
# удалено) сводятся к 404 — приватность: чужое/недоступное неотличимо.
# Закрытый/архивный чат → 409 (как send). Audit пишется soft-fail без plaintext.


def _apply_message_edit(
    *,
    conv,
    eng,
    actor_user_id: int,
    actor_role: str,
    message_uuid: str,
    content: str,
    remove_attachment_uuids: Optional[list] = None,
) -> dict:
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)
    try:
        _uuid.UUID(message_uuid)
    except ValueError:
        raise ChatError(_NOT_FOUND, status_code=404)

    result = storage.update_message_content(
        conversation_id=conv.id,
        message_uuid=message_uuid,
        actor_user_id=actor_user_id,
        client_id=eng.client_id,
        new_content=content,
        remove_attachment_uuids=remove_attachment_uuids,
    )
    if result["status"] == "would_be_empty":
        raise ChatError(
            "Нельзя сохранить пустое сообщение: нет текста и все вложения удалены",
            status_code=400,
        )
    if result["status"] != "ok":
        # not_found / not_owner / forbidden_system / deleted / attachment_not_found → 404.
        raise ChatError(_NOT_FOUND, status_code=404)

    msg = result["message"]
    # Audit-факт без plaintext/ciphertext; soft-fail, не ломает правку.
    record_event(
        event="chat_message_edited",
        actor=Actor.user(actor_user_id, actor_role),
        target=Target("chat_message", msg["id"]),
        outcome=Outcome.SUCCESS,
        context=None,
        db=None,
    )
    return msg


def edit_message(
    current_user: dict,
    conversation_uuid: str,
    message_uuid: str,
    content: str,
    remove_attachment_uuids: Optional[list] = None,
) -> dict:
    """Psychologist редактирует своё сообщение в своей активной беседе."""
    psychologist_id = int(current_user["id"])
    conv, eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return _apply_message_edit(
        conv=conv, eng=eng,
        actor_user_id=psychologist_id,
        actor_role=_actor_role(current_user, "psychologist"),
        message_uuid=message_uuid, content=content,
        remove_attachment_uuids=remove_attachment_uuids,
    )


# ─── Delete message (Stage 31y) ──────────────────────────────────────────────
#
# Soft delete. Та же политика, что и edit: удалить можно ТОЛЬКО своё user-
# сообщение и ТОЛЬКО пока engagement активен. system/чужие → 404 (скрываем).
# Повторное удаление своего сообщения идемпотентно (storage возвращает "ok").
# Закрытый/архивный чат → 409. Audit chat_message_deleted soft-fail без текста.


def _apply_message_delete(
    *,
    conv,
    eng,
    actor_user_id: int,
    actor_role: str,
    message_uuid: str,
) -> dict:
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)
    try:
        _uuid.UUID(message_uuid)
    except ValueError:
        raise ChatError(_NOT_FOUND, status_code=404)

    result = storage.soft_delete_message(
        conversation_id=conv.id,
        message_uuid=message_uuid,
        actor_user_id=actor_user_id,
        client_id=eng.client_id,
    )
    if result["status"] != "ok":
        # not_found / not_owner / forbidden_system → 404 (скрываем).
        raise ChatError(_NOT_FOUND, status_code=404)

    msg = result["message"]
    record_event(
        event="chat_message_deleted",
        actor=Actor.user(actor_user_id, actor_role),
        target=Target("chat_message", msg["id"]),
        outcome=Outcome.SUCCESS,
        context=None,
        db=None,
    )
    return msg


def delete_message(
    current_user: dict, conversation_uuid: str, message_uuid: str,
) -> dict:
    """Psychologist удаляет своё сообщение в своей активной беседе."""
    psychologist_id = int(current_user["id"])
    conv, eng = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return _apply_message_delete(
        conv=conv, eng=eng,
        actor_user_id=psychologist_id,
        actor_role=_actor_role(current_user, "psychologist"),
        message_uuid=message_uuid,
    )


# ─── Student conversation list / archive (Stage 31t) ─────────────────────────
#
# Единая с психологом модель: список бесед студента (active + non-empty inactive),
# чтение/отправка/read по conversation_uuid. Доступ строго к своим беседам:
# engagement.client_id == student.id. Старые /my-conversation* остаются (badge
# legacy + back-compat) и не удаляются.

def list_student_conversations(
    current_user: dict, *, page: int, size: int,
) -> tuple[list[dict], int]:
    return storage.list_conversations_for_student(
        int(current_user["id"]), page=page, size=size,
    )


def _resolve_student_conversation_by_uuid(student_id: int, conversation_uuid: str):
    """(conversation, engagement) если студент — участник, иначе 404.
    Чужая/несуществующая беседа неотличимы (404). inactive разрешён (read-only)."""
    try:
        _uuid.UUID(conversation_uuid)
    except ValueError:
        raise ChatError(_NOT_FOUND, status_code=404)

    row = storage.get_conversation_by_uuid(conversation_uuid)
    if row is None:
        raise ChatError(_NOT_FOUND, status_code=404)
    conv, eng = row
    if eng.client_id != student_id:
        raise ChatError(_NOT_FOUND, status_code=404)
    return conv, eng


def get_student_conversation_messages(
    current_user: dict,
    conversation_uuid: str,
    *,
    limit: int,
    before_id: Optional[int],
    after_id: Optional[int],
) -> list[dict]:
    student_id = int(current_user["id"])
    conv, eng = _resolve_student_conversation_by_uuid(student_id, conversation_uuid)
    return storage.get_messages(
        conv.id,
        current_user_id=student_id,
        client_id=eng.client_id,
        limit=limit,
        before_id=before_id,
        after_id=after_id,
    )


def send_student_conversation_message(
    current_user: dict,
    conversation_uuid: str,
    content: str,
    attachment_uuids: Optional[list] = None,
) -> dict:
    student_id = int(current_user["id"])
    conv, eng = _resolve_student_conversation_by_uuid(student_id, conversation_uuid)
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)
    try:
        return storage.create_message(
            conv.id,
            sender_id=student_id,
            content=content,
            client_id=eng.client_id,
            attachment_uuids=attachment_uuids,
        )
    except ValueError as e:
        raise ChatError(str(e), status_code=400)


def mark_student_conversation_read(
    current_user: dict, conversation_uuid: str,
) -> int:
    student_id = int(current_user["id"])
    conv, _eng = _resolve_student_conversation_by_uuid(student_id, conversation_uuid)
    return storage.mark_read(conv.id, reader_id=student_id)


def edit_student_conversation_message(
    current_user: dict,
    conversation_uuid: str,
    message_uuid: str,
    content: str,
    remove_attachment_uuids: Optional[list] = None,
) -> dict:
    """Student редактирует своё сообщение в своей активной беседе (Stage 31x/32g)."""
    student_id = int(current_user["id"])
    conv, eng = _resolve_student_conversation_by_uuid(student_id, conversation_uuid)
    return _apply_message_edit(
        conv=conv, eng=eng,
        actor_user_id=student_id,
        actor_role=_actor_role(current_user, "student"),
        message_uuid=message_uuid, content=content,
        remove_attachment_uuids=remove_attachment_uuids,
    )


def delete_student_conversation_message(
    current_user: dict, conversation_uuid: str, message_uuid: str,
) -> dict:
    """Student удаляет своё сообщение в своей активной беседе (Stage 31y)."""
    student_id = int(current_user["id"])
    conv, eng = _resolve_student_conversation_by_uuid(student_id, conversation_uuid)
    return _apply_message_delete(
        conv=conv, eng=eng,
        actor_user_id=student_id,
        actor_role=_actor_role(current_user, "student"),
        message_uuid=message_uuid,
    )


# ─── Attachments (Stage 32c) ──────────────────────────────────────────────────
#
# Upload: pre-upload pattern — файл сохраняется до создания сообщения.
# message_id = NULL в момент upload; привязывается при send (create_message).
# Download: download разрешён участникам (active и closed/archive).
# System conversation: upload/download запрещены.
# Admin/supervisor: доступа нет (403 на уровне роутера).

def _do_upload_attachment(
    actor_user_id: int,
    actor_role:    str,
    conv,
    eng,
    file:          UploadFile,
    data:          bytes,
) -> dict:
    """Общая логика upload для student/psychologist после resolve беседы."""
    from app.chat import attachment_storage as fs

    # System-беседу блокируем
    if getattr(conv, "type", "engagement") == "system":
        raise ChatError("Вложения в системную беседу не разрешены", status_code=403)

    # Upload разрешён только в активной беседе
    if eng.status != "active":
        raise ChatError(_CLOSED, status_code=409)

    # Валидация файла
    try:
        _att_svc.validate_upload(file, data)
    except _att_svc.AttachmentValidationError as e:
        raise ChatError(e.message, status_code=e.status_code)

    mime     = _att_svc.normalize_mime(file)
    is_image = _att_svc.is_image_mime(mime)
    key      = fs.generate_storage_key()

    result, attachment_id = storage.save_attachment(
        conversation_id=conv.id,
        uploader_id=actor_user_id,
        original_filename=file.filename,
        storage_key=key,
        mime_type=mime,
        file_size=len(data),
        is_image=is_image,
        data=data,
    )

    # Audit soft-fail: сбой audit не ломает upload. Target — internal id
    # (attachment_id), не UUID; metadata строго file_size/mime_type (registry).
    record_event(
        event="chat_attachment_uploaded",
        actor=Actor.user(actor_user_id, actor_role),
        target=Target("chat_attachment", attachment_id),
        outcome=Outcome.SUCCESS,
        metadata={
            "file_size": result["file_size"],
            "mime_type": result["mime_type"],
        },
        context=None,
        db=None,
    )

    return result


def upload_attachment_student(
    current_user:  dict,
    conversation_uuid: str,
    file:          UploadFile,
    data:          bytes,
) -> dict:
    """Student загружает вложение в свою активную беседу."""
    student_id = int(current_user["id"])
    conv, eng  = _resolve_student_conversation_by_uuid(student_id, conversation_uuid)
    return _do_upload_attachment(
        student_id, _actor_role(current_user, "student"), conv, eng, file, data,
    )


def upload_attachment_psychologist(
    current_user:  dict,
    conversation_uuid: str,
    file:          UploadFile,
    data:          bytes,
) -> dict:
    """Psychologist загружает вложение в свою активную беседу."""
    psychologist_id = int(current_user["id"])
    conv, eng       = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return _do_upload_attachment(
        psychologist_id, _actor_role(current_user, "psychologist"),
        conv, eng, file, data,
    )


def _do_download_attachment(
    actor_user_id: int,
    actor_role:    str,
    conv,
    attachment_uuid: str,
) -> tuple[Path, str, str]:
    """
    Общая логика download. Возвращает (path, original_filename, mime_type).
    Download разрешён участникам active и closed/archive беседы.
    """
    from app.chat import attachment_storage as fs

    if getattr(conv, "type", "engagement") == "system":
        raise ChatError(_NOT_FOUND, status_code=404)

    att = storage.get_attachment_for_download(attachment_uuid, conv.id)
    if att is None:
        raise ChatError(_NOT_FOUND, status_code=404)

    try:
        path = fs.open_for_read(att.storage_key)
    except FileNotFoundError:
        raise ChatError("Файл вложения не найден", status_code=404)

    # Audit soft-fail. att.id (internal, уже доступен из ORM) — Target, без
    # повторного DB lookup ради аудита; metadata пуста (registry).
    record_event(
        event="chat_attachment_downloaded",
        actor=Actor.user(actor_user_id, actor_role),
        target=Target("chat_attachment", att.id),
        outcome=Outcome.SUCCESS,
        context=None,
        db=None,
    )

    return path, att.original_filename, att.mime_type


def download_attachment_student(
    current_user:    dict,
    conversation_uuid: str,
    attachment_uuid: str,
) -> tuple[Path, str, str]:
    """Student скачивает вложение из своей беседы (active или closed)."""
    student_id = int(current_user["id"])
    conv, _eng = _resolve_student_conversation_by_uuid(student_id, conversation_uuid)
    return _do_download_attachment(
        student_id, _actor_role(current_user, "student"), conv, attachment_uuid,
    )


def download_attachment_psychologist(
    current_user:    dict,
    conversation_uuid: str,
    attachment_uuid: str,
) -> tuple[Path, str, str]:
    """Psychologist скачивает вложение из своей беседы (active или closed)."""
    psychologist_id = int(current_user["id"])
    conv, _eng      = _resolve_psychologist_conversation(psychologist_id, conversation_uuid)
    return _do_download_attachment(
        psychologist_id, _actor_role(current_user, "psychologist"),
        conv, attachment_uuid,
    )


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
