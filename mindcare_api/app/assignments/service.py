"""
Задания психолога клиенту — бизнес-логика БЕЗ FastAPI/HTTP (ADR-033).

Service получает уже проверенный actor-контекст (context.py) и отвечает
доменными ошибками (errors.py); HTTP-зависимости, HTTPException, маппинг ошибок
в статусы и failure-события остаются в routes*. AuditError (сбой обязательного
аудита) пробрасывается как есть — route превращает его в 503.

Чтение психологом: страница выбирается и расшифровывается в памяти, затем на
КАЖДОЕ задание этой страницы записывается assignment_content_read
(INDEPENDENT + RAISE), и только потом страница возвращается: при сбое любого из
событий тексты не отдаются. Уже записанные события серии остаются (перекос в
сторону лишнего аудита, как в ADR-029). Пустая страница — без событий.

Чтение владельцем своих заданий отдельного события не пишет (свои данные).
Просроченность вычисляется на лету по московской дате и ничего не записывает.

Уведомление психолога о выполнении — system-сообщение ПОСЛЕ commit
(publish_system_message, soft-fail: сбой доставки не отменяет выполнение).
Текст — только имя клиента, без текста задания; event_key per-assignment, так
что повтор (no-op) или ретрай дубля не создают. No-op уведомления не шлёт.
Так же (Дополнение 2026-10-28) клиент получает system-сообщение о новом и об
отменённом задании — только имя психолога и ссылка на «Задания».
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from app.assignments import storage, validators
from app.assignments.context import ClientContext, PsychologistContext
from app.assignments.errors import AssignmentNotAvailable
from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.chat.system_publisher import publish_system_message

MOSCOW_TZ = timezone(timedelta(hours=3))
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50
PSYCHOLOGIST_FALLBACK_NAME = "Психолог"


def _today_moscow() -> date:
    return datetime.now(MOSCOW_TZ).date()


def _is_overdue(row: dict, today: date) -> bool:
    return (
        row["status"] == "active"
        and row["engagement_active"]
        and row["due_date"] is not None
        and row["due_date"] < today
    )


def _base_dto(row: dict, today: date) -> dict:
    return {
        "uuid":                 row["uuid"],
        "text":                 row["text"],
        "status":               row["status"],
        "due_date":             row["due_date"],
        "is_overdue":           _is_overdue(row, today),
        "created_at":           row["created_at"],
        "completed_at":         row["completed_at"],
        "cancelled_at":         row["cancelled_at"],
        "engagement_active":    row["engagement_active"],
        "material":             row["material"],
        "material_unavailable": row["material_unavailable"],
    }


def _next_cursor(page: dict) -> Optional[str]:
    if not page["has_more"] or not page["rows"]:
        return None
    last = page["rows"][-1]
    return validators.encode_cursor(last["created_at"], last["uuid"])


def _page_size(size: int) -> int:
    return max(1, min(int(size), MAX_PAGE_SIZE))


# ── владелец ──────────────────────────────────────────────────────────────────

def list_my(ctx: ClientContext, view: str, before: Optional[str], size: int) -> dict:
    cursor = validators.decode_cursor(before)          # AssignmentValidationError
    page = storage.list_client_page(ctx.user_id, view, cursor, _page_size(size))
    today = _today_moscow()
    items = []
    for row in page["rows"]:
        dto = _base_dto(row, today)
        dto["can_complete"] = row["status"] == "active" and row["engagement_active"]
        dto["psychologist_name"] = row["psychologist_name"] or PSYCHOLOGIST_FALLBACK_NAME
        items.append(dto)
    return {
        "items": items,
        "has_more": page["has_more"],
        "next_cursor": _next_cursor(page),
        "total": page["total"],
    }


def my_summary(ctx: ClientContext) -> dict:
    return storage.client_summary(ctx.user_id)


def complete_my(
    ctx: ClientContext,
    assignment_uuid,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    result = storage.complete_atomic(ctx.user_id, assignment_uuid, ip=ip, user_agent=user_agent)
    notify = result.pop("notify", None)
    if notify is not None:
        publish_system_message(
            recipient_id=notify["psychologist_id"],
            event_key=completed_event_key(result["uuid"]),
            text=completed_message_text(notify["client_name"]),
        )
    return result


def completed_event_key(assignment_uuid) -> str:
    """Ключ уведомления — один на задание (повтор/ретрай не дублирует)."""
    return f"assignment_completed:assignment:{assignment_uuid}"


def completed_message_text(client_name: str) -> str:
    """Текст без содержания задания: только кто выполнил."""
    name = (client_name or "").strip() or "клиент"
    return f"Задание выполнено. Клиент: {name}. Статус виден в карточке клиента."


# ── психолог ──────────────────────────────────────────────────────────────────

def list_for_client(
    ctx: PsychologistContext,
    client_uuid,
    before: Optional[str],
    size: int,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    cursor = validators.decode_cursor(before)          # AssignmentValidationError
    page = storage.list_psychologist_page(ctx.user_id, client_uuid, cursor, _page_size(size))
    if page is None:
        raise AssignmentNotAvailable()

    # Fail-closed: события на каждое задание страницы ДО возврата текстов.
    for row in page["rows"]:
        record_event(
            event="assignment_content_read",
            actor=Actor.user(ctx.user_id, "psychologist"),
            target=Target(storage.ENTITY_TYPE, row["id"]),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
        )

    today = _today_moscow()
    items = []
    for row in page["rows"]:
        dto = _base_dto(row, today)
        dto["can_cancel"] = row["status"] == "active"
        items.append(dto)
    return {
        "items": items,
        "has_more": page["has_more"],
        "next_cursor": _next_cursor(page),
        "total": page["total"],
    }


def create_for_client(
    ctx: PsychologistContext,
    client_uuid,
    *,
    text: str,
    due_date: Optional[date],
    article_uuid,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    normalized = validators.normalize_text(text)       # AssignmentValidationError
    result = storage.create_atomic(
        ctx.user_id, client_uuid, normalized, due_date, article_uuid,
        ip=ip, user_agent=user_agent,
    )
    _notify_client("created", result)
    return result


def cancel(
    ctx: PsychologistContext,
    assignment_uuid,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    result = storage.cancel_atomic(ctx.user_id, assignment_uuid, ip=ip, user_agent=user_agent)
    _notify_client("cancelled", result)
    return result


def _notify_client(kind: str, result: dict) -> None:
    """
    Post-commit уведомление клиента (soft-fail внутри publisher). Только при
    реальном переходе: no-op повтор отмены notify не несёт. Ключ — один на
    задание и вид события: повтор/ретрай не дублирует сообщение.
    """
    notify = result.pop("notify", None)
    if notify is None:
        return
    publish_system_message(
        recipient_id=notify["client_id"],
        event_key=f"assignment_{kind}:assignment:{result['uuid']}",
        text=client_message_text(kind, notify["psychologist_name"]),
    )


TASKS_LINK = "/student/tasks"


def client_message_text(kind: str, psychologist_name: str) -> str:
    """Без содержания задания: от кого и что произошло, плюс ссылка на «Задания»."""
    name = (psychologist_name or "").strip()
    source = f"от психолога {name}" if name else "от психолога"
    if kind == "created":
        return f"Новое задание {source}. {TASKS_LINK}"
    return f"Задание {source} отменено. {TASKS_LINK}"
