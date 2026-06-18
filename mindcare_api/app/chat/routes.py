"""
Chat MVP API (Stage 28c). Префикс: /api/chat

Доступ: ТОЛЬКО student и psychologist (участники бесед по engagement).
admin / supervisor получают 403 — staff-доступа к переписке в MVP нет
(break-glass — отдельное future compliance-решение).

Polling-based: клиент опрашивает messages?after=<id> раз в 7–10 секунд.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse

from app.auth.deps import get_current_user, require_role
from app.core.rate_limit import RateLimitExceeded, check as rate_limit_check
from app.chat import service
from app.chat.attachment_service import safe_content_disposition
from app.chat.schemas import (
    ChatAttachmentRead,
    ChatConversationRead,
    ChatMessageCreate,
    ChatMessageEdit,
    ChatMessageRead,
    ChatMessagesResponse,
    ChatReadResponse,
    MyConversationResponse,
    MySystemConversationResponse,
    PaginatedChatConversationsResponse,
    PaginatedStudentConversationsResponse,
)

router = APIRouter(
    prefix="/chat",
    tags=["chat"],
    dependencies=[Depends(require_role("student", "psychologist"))],
)

# Анти-спам отправки: 30 сообщений / минуту / пользователь.
# Кортеж вынесен в константу для monkeypatch в тестах.
CHAT_SEND_LIMIT = (30, 60)

_RATE_MESSAGE = "Слишком много сообщений. Попробуйте позже."


def _check_send_limit(user_id: int) -> None:
    try:
        rate_limit_check(f"chat_send:user:{user_id}", *CHAT_SEND_LIMIT)
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail=_RATE_MESSAGE)


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


# ─── Student ──────────────────────────────────────────────────────────────────

@router.get("/my-conversation", response_model=MyConversationResponse)
def my_conversation(
    request:      Request,
    current_user: dict = Depends(require_role("student")),
):
    return service.get_my_conversation(
        current_user,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/my-conversation/messages", response_model=ChatMessagesResponse)
def my_messages(
    limit:        int           = Query(default=50, ge=1, le=100),
    before:       Optional[int] = Query(default=None, ge=1),
    after:        Optional[int] = Query(default=None, ge=0),
    current_user: dict          = Depends(require_role("student")),
):
    try:
        items = service.get_my_messages(
            current_user, limit=limit, before_id=before, after_id=after,
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить сообщения",
        )
    return {"items": items}


@router.post(
    "/my-conversation/messages",
    response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def my_send_message(
    body:         ChatMessageCreate,
    request:      Request,
    current_user: dict = Depends(require_role("student")),
):
    _check_send_limit(int(current_user["id"]))
    try:
        return service.send_my_message(
            current_user,
            body.content,
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            attachment_uuids=[str(u) for u in body.attachment_uuids],
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось отправить сообщение",
        )


@router.post("/my-conversation/read", response_model=ChatReadResponse)
def my_mark_read(
    current_user: dict = Depends(require_role("student")),
):
    try:
        updated = service.mark_my_read(current_user)
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"updated_count": updated}


# ─── Student conversation list / archive (Stage 31t) ────────────────────────
#
# Единая с психологом модель: список бесед студента + чтение/отправка/read по
# conversation_uuid. Доступ строго к своим беседам (service: client_id == user).

@router.get(
    "/student/conversations", response_model=PaginatedStudentConversationsResponse,
)
def list_student_conversations(
    page:         int  = Query(default=1, ge=1),
    size:         int  = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_role("student")),
):
    items, total = service.list_student_conversations(current_user, page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get(
    "/student/conversations/{conversation_uuid}/messages",
    response_model=ChatMessagesResponse,
)
def student_conversation_messages(
    conversation_uuid: str,
    limit:             int           = Query(default=50, ge=1, le=100),
    before:            Optional[int] = Query(default=None, ge=1),
    after:             Optional[int] = Query(default=None, ge=0),
    current_user:      dict          = Depends(require_role("student")),
):
    try:
        items = service.get_student_conversation_messages(
            current_user, conversation_uuid,
            limit=limit, before_id=before, after_id=after,
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить сообщения",
        )
    return {"items": items}


@router.post(
    "/student/conversations/{conversation_uuid}/messages",
    response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def student_send_message(
    conversation_uuid: str,
    body:              ChatMessageCreate,
    current_user:      dict = Depends(require_role("student")),
):
    _check_send_limit(int(current_user["id"]))
    try:
        return service.send_student_conversation_message(
            current_user, conversation_uuid, body.content,
            attachment_uuids=[str(u) for u in body.attachment_uuids],
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось отправить сообщение",
        )


@router.patch(
    "/student/conversations/{conversation_uuid}/messages/{message_uuid}",
    response_model=ChatMessageRead,
)
def student_edit_message(
    conversation_uuid: str,
    message_uuid:      str,
    body:              ChatMessageEdit,
    current_user:      dict = Depends(require_role("student")),
):
    _check_send_limit(int(current_user["id"]))
    try:
        return service.edit_student_conversation_message(
            current_user, conversation_uuid, message_uuid, body.content,
            remove_attachment_uuids=[str(u) for u in body.remove_attachment_uuids],
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось изменить сообщение",
        )


@router.delete(
    "/student/conversations/{conversation_uuid}/messages/{message_uuid}",
    response_model=ChatMessageRead,
)
def student_delete_message(
    conversation_uuid: str,
    message_uuid:      str,
    current_user:      dict = Depends(require_role("student")),
):
    try:
        return service.delete_student_conversation_message(
            current_user, conversation_uuid, message_uuid,
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить сообщение",
        )


@router.post(
    "/student/conversations/{conversation_uuid}/read", response_model=ChatReadResponse,
)
def student_mark_read(
    conversation_uuid: str,
    current_user:      dict = Depends(require_role("student")),
):
    try:
        updated = service.mark_student_conversation_read(current_user, conversation_uuid)
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"updated_count": updated}


@router.post(
    "/student/conversations/{conversation_uuid}/attachments",
    response_model=ChatAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def student_upload_attachment(
    conversation_uuid: str,
    file:              UploadFile = File(...),
    current_user:      dict       = Depends(require_role("student")),
):
    data = file.file.read()
    try:
        return service.upload_attachment_student(current_user, conversation_uuid, file, data)
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/student/conversations/{conversation_uuid}/attachments/{attachment_uuid}/download",
)
def student_download_attachment(
    conversation_uuid: str,
    attachment_uuid:   str,
    current_user:      dict = Depends(require_role("student")),
):
    try:
        path, filename, mime_type = service.download_attachment_student(
            current_user, conversation_uuid, attachment_uuid,
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return FileResponse(
        path=str(path),
        media_type=mime_type,
        headers={
            "Content-Disposition":  safe_content_disposition(filename),
            "Cache-Control":        "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ─── Psychologist ─────────────────────────────────────────────────────────────

@router.get("/conversations", response_model=PaginatedChatConversationsResponse)
def list_conversations(
    page:         int  = Query(default=1, ge=1),
    size:         int  = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_role("psychologist")),
):
    items, total = service.list_conversations(current_user, page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/conversations/{conversation_uuid}", response_model=ChatConversationRead)
def get_conversation(
    conversation_uuid: str,
    current_user:      dict = Depends(require_role("psychologist")),
):
    try:
        return service.get_conversation(current_user, conversation_uuid)
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/conversations/{conversation_uuid}/messages",
    response_model=ChatMessagesResponse,
)
def get_messages(
    conversation_uuid: str,
    limit:             int           = Query(default=50, ge=1, le=100),
    before:            Optional[int] = Query(default=None, ge=1),
    after:             Optional[int] = Query(default=None, ge=0),
    current_user:      dict          = Depends(require_role("psychologist")),
):
    try:
        items = service.get_messages(
            current_user, conversation_uuid,
            limit=limit, before_id=before, after_id=after,
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить сообщения",
        )
    return {"items": items}


@router.post(
    "/conversations/{conversation_uuid}/messages",
    response_model=ChatMessageRead,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    conversation_uuid: str,
    body:              ChatMessageCreate,
    current_user:      dict = Depends(require_role("psychologist")),
):
    _check_send_limit(int(current_user["id"]))
    try:
        return service.send_message(
            current_user, conversation_uuid, body.content,
            attachment_uuids=[str(u) for u in body.attachment_uuids],
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось отправить сообщение",
        )


@router.patch(
    "/conversations/{conversation_uuid}/messages/{message_uuid}",
    response_model=ChatMessageRead,
)
def edit_message(
    conversation_uuid: str,
    message_uuid:      str,
    body:              ChatMessageEdit,
    current_user:      dict = Depends(require_role("psychologist")),
):
    _check_send_limit(int(current_user["id"]))
    try:
        return service.edit_message(
            current_user, conversation_uuid, message_uuid, body.content,
            remove_attachment_uuids=[str(u) for u in body.remove_attachment_uuids],
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось изменить сообщение",
        )


@router.delete(
    "/conversations/{conversation_uuid}/messages/{message_uuid}",
    response_model=ChatMessageRead,
)
def delete_message(
    conversation_uuid: str,
    message_uuid:      str,
    current_user:      dict = Depends(require_role("psychologist")),
):
    try:
        return service.delete_message(current_user, conversation_uuid, message_uuid)
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось удалить сообщение",
        )


@router.post("/conversations/{conversation_uuid}/read", response_model=ChatReadResponse)
def mark_read(
    conversation_uuid: str,
    current_user:      dict = Depends(require_role("psychologist")),
):
    try:
        updated = service.mark_read(current_user, conversation_uuid)
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"updated_count": updated}


@router.post(
    "/conversations/{conversation_uuid}/attachments",
    response_model=ChatAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
def psychologist_upload_attachment(
    conversation_uuid: str,
    file:              UploadFile = File(...),
    current_user:      dict       = Depends(require_role("psychologist")),
):
    data = file.file.read()
    try:
        return service.upload_attachment_psychologist(current_user, conversation_uuid, file, data)
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get(
    "/conversations/{conversation_uuid}/attachments/{attachment_uuid}/download",
)
def psychologist_download_attachment(
    conversation_uuid: str,
    attachment_uuid:   str,
    current_user:      dict = Depends(require_role("psychologist")),
):
    try:
        path, filename, mime_type = service.download_attachment_psychologist(
            current_user, conversation_uuid, attachment_uuid,
        )
    except service.ChatError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return FileResponse(
        path=str(path),
        media_type=mime_type,
        headers={
            "Content-Disposition":  safe_content_disposition(filename),
            "Cache-Control":        "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ─── System conversation (Stage 29b) ────────────────────────────────────────
#
# Отдельный роутер: доступен ЛЮБОЙ авторизованной роли как получателю СВОЕЙ
# system-беседы (engagement-роутер выше ограничен student/psychologist).
# Все эндпоинты скоупятся по current_user — чужую беседу прочитать нельзя.
# Write-эндпоинта нет: system-сообщения создаёт только internal publisher.

system_router = APIRouter(
    prefix="/chat",
    tags=["chat-system"],
    dependencies=[Depends(get_current_user)],
)


@system_router.get("/system-conversation", response_model=MySystemConversationResponse)
def my_system_conversation(current_user: dict = Depends(get_current_user)):
    return service.get_my_system_conversation(current_user)


@system_router.get(
    "/system-conversation/messages", response_model=ChatMessagesResponse,
)
def my_system_messages(
    limit:        int           = Query(default=50, ge=1, le=100),
    before:       Optional[int] = Query(default=None, ge=1),
    after:        Optional[int] = Query(default=None, ge=0),
    current_user: dict          = Depends(get_current_user),
):
    try:
        items = service.get_my_system_messages(
            current_user, limit=limit, before_id=before, after_id=after,
        )
    except RuntimeError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Не удалось загрузить сообщения",
        )
    return {"items": items}


@system_router.post("/system-conversation/read", response_model=ChatReadResponse)
def my_system_read(current_user: dict = Depends(get_current_user)):
    # Идемпотентно; не падает, если беседы ещё нет (вернёт 0).
    return {"updated_count": service.mark_my_system_read(current_user)}
