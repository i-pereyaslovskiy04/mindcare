"""
Подтверждение студента ДонГУ — бизнес-логика без FastAPI/HTTP (ADR-029).

Расшифровка (decrypt_text) выполняется только в двух местах:
  * собственный статус пользователя — пояснение отказа (его данные, без аудита);
  * карточка supervisor'а — номер билета и пояснение, СТРОГО после успешной
    записи student_verification_content_read (INDEPENDENT + RAISE): сбой аудита
    → AuditError наружу, номер не отдаётся.
Post-commit доставка уведомления о решении — soft-fail (outbox добирает).
"""
from typing import Optional

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.auth.roles import is_pure_student
from app.core.encryption import decrypt_text
from app.notifications.service import deliver_by_key_soft
from app.notifications.templates import result_event_key
from app.student_verification import errors, storage
from app.student_verification.faculties import FACULTIES, faculty_dto


def faculties() -> list[dict]:
    return [{"code": code, "label": label} for code, label in FACULTIES]


def ensure_self_service(current_user: dict) -> None:
    """
    Ранняя проверка self-service: не impersonation и активные роли ровно
    {student}. require_role("student") мало — student есть у всех staff
    (ADR-024). Авторитетная повторная проверка — в storage под блокировкой.
    """
    if current_user.get("impersonator_user_id") is not None:
        raise errors.ImpersonationForbidden()
    if not is_pure_student(current_user.get("roles") or []):
        raise errors.VerificationNotAllowed()


def _my_request_dto(row: dict) -> dict:
    reason = None
    if row["status"] == "rejected" and row.get("rejection_reason_enc"):
        reason = decrypt_text(row["rejection_reason_enc"])
    return {
        "uuid": row["uuid"],
        "status": row["status"],
        "faculty": faculty_dto(row["faculty_code"]),
        "submitted_at": row["submitted_at"],
        "reviewed_at": row["reviewed_at"],
        "rejection_reason": reason,
    }


def get_my_status(current_user: dict) -> dict:
    """Собственный статус: последняя заявка. Чтение своих данных не аудируется."""
    ensure_self_service(current_user)
    row = storage.get_latest_for_user(int(current_user["id"]))
    if row is None:
        return {"status": "not_submitted", "can_submit": True, "current": None}
    return {
        "status": row["status"],
        # Одобрение финально; pending неизменяема; после отказа — новая заявка.
        "can_submit": row["status"] == "rejected",
        "current": _my_request_dto(row),
    }


def submit_my(
    current_user: dict,
    *,
    faculty_code: str,
    ticket_number: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    ensure_self_service(current_user)
    storage.submit_atomic(
        int(current_user["id"]),
        faculty_code=faculty_code,
        ticket_number=ticket_number,
        ip=ip,
        user_agent=user_agent,
    )
    return get_my_status(current_user)


# ── supervisor ────────────────────────────────────────────────────────────────

def _list_item_dto(row: dict) -> dict:
    return {
        "uuid": row["uuid"],
        "status": row["status"],
        "faculty": faculty_dto(row["faculty_code"]),
        "submitted_at": row["submitted_at"],
        "reviewed_at": row["reviewed_at"],
        "student": row["student"],
        "reviewer": row["reviewer"],
    }


def list_for_review(
    *, status: str, page: int, size: int, search: Optional[str] = None,
) -> tuple[list, int]:
    items, total = storage.list_requests(
        status=None if status == "all" else status, page=page, size=size,
        search=search,
    )
    return [_list_item_dto(i) for i in items], total


def get_card_for_review(
    request_uuid,
    *,
    reviewer_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Карточка с полным номером. Порядок fail-closed: выборка → расшифровка в
    памяти → content_read (INDEPENDENT + RAISE) → ответ. AuditError
    пробрасывается: route отдаёт 503 без номера.
    """
    row = storage.get_card(request_uuid)
    if row is None:
        raise errors.VerificationNotFound()

    ticket_number = decrypt_text(row["ticket_number_enc"])
    reason = None
    if row["status"] == "rejected" and row.get("rejection_reason_enc"):
        reason = decrypt_text(row["rejection_reason_enc"])

    record_event(
        event="student_verification_content_read",
        actor=Actor.user(int(reviewer_id), "supervisor"),
        target=Target(storage.ENTITY_TYPE, row["id"]),
        outcome=Outcome.SUCCESS,
        metadata={},
        context=build_request_context(ip=ip, user_agent=user_agent),
    )

    card = _list_item_dto(row)
    card.update({
        "ticket_number": ticket_number,
        "rejection_reason": reason,
        "can_review": row["status"] == "pending" and row["user_id"] != int(reviewer_id),
        "history": [
            {
                "uuid": h["uuid"],
                "status": h["status"],
                "faculty": faculty_dto(h["faculty_code"]),
                "submitted_at": h["submitted_at"],
                "reviewed_at": h["reviewed_at"],
            }
            for h in row["history"]
        ],
    })
    return card


def decide(
    request_uuid,
    *,
    decision: str,
    reviewer_id: int,
    reason: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Решение по заявке. После commit — soft-fail доставка уведомления (только
    при реальном переходе: no-op повтор не создаёт ни события, ни намерения).
    Возвращает метаданные заявки без номера билета.
    """
    if decision == "reject" and not (reason or "").strip():
        raise ValueError("rejection reason is required")
    row, changed = storage.decide_atomic(
        request_uuid,
        decision=decision,
        reviewer_id=reviewer_id,
        reason=reason,
        ip=ip,
        user_agent=user_agent,
    )
    if changed:
        deliver_by_key_soft(row["user_id"], result_event_key(row["uuid"]))
    return {
        "uuid": row["uuid"],
        "status": row["status"],
        "faculty": faculty_dto(row["faculty_code"]),
        "submitted_at": row["submitted_at"],
        "reviewed_at": row["reviewed_at"],
    }
