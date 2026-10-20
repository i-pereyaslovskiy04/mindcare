"""
Подтверждение студента ДонГУ — бизнес-логика без FastAPI/HTTP (ADR-029).

Расшифровка (decrypt_text) выполняется только в трёх местах:
  * собственный статус пользователя — пояснение отказа (его данные, без аудита);
  * карточка supervisor'а — номер билета и пояснение текущей заявки, а также
    пояснения прежних отказов в первой порции истории;
  * порция истории «Показать ещё» — пояснения отказов этой порции.
Ответ с номером или пояснением отдаётся СТРОГО после успешной записи
student_verification_content_read (INDEPENDENT + RAISE) — по одному событию на
КАЖДУЮ заявку, чьё содержимое раскрывается (текущая заявка карточки — одним
событием, без дубля за её строку в истории). Сбой любого из событий →
AuditError наружу, ни номер, ни пояснения не отдаются. Уже записанные события
серии остаются: фиксируют попытку чтения (перекос в сторону лишнего аудита).
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


def pending_count() -> int:
    """Число заявок в очереди. Агрегат без содержимого — без аудита."""
    return storage.count_pending()


# ── история подтверждения ─────────────────────────────────────────────────────

def _actor(full_name: Optional[str]) -> Optional[dict]:
    # None — исполнитель недоступен (проверявший удалён: reviewed_by SET NULL).
    return {"full_name": full_name} if full_name is not None else None


def _history_reasons(rows: list) -> dict:
    """{id заявки: пояснение} — только отказы с сохранённым пояснением."""
    return {
        r["id"]: decrypt_text(r["rejection_reason_enc"])
        for r in rows
        if r["status"] == "rejected" and r.get("rejection_reason_enc")
    }


def _history_request_dto(row: dict, reason: Optional[str], current_id: int) -> dict:
    # События заявки — от новых к старым: решение (если есть), затем подача.
    # У подачи и одобрения отдельной причины нет — она не выдумывается.
    events = []
    if row["status"] in ("approved", "rejected"):
        events.append({
            "type": row["status"],
            "at": row["reviewed_at"],
            "actor": _actor(row["reviewer_full_name"]),
            "reason": reason if row["status"] == "rejected" else None,
        })
    events.append({
        "type": "submitted" if row["is_first"] else "resubmitted",
        "at": row["submitted_at"],
        "actor": _actor(row["applicant_full_name"]),
        "reason": None,
    })
    return {
        "uuid": row["uuid"],
        "status": row["status"],
        "faculty": faculty_dto(row["faculty_code"]),
        "is_current": row["id"] == current_id,
        "events": events,
    }


def _history_dto(portion: dict, *, current_id: int, reasons: dict) -> dict:
    rows = portion["rows"]
    return {
        "items": [
            _history_request_dto(r, reasons.get(r["id"]), current_id) for r in rows
        ],
        "has_more": portion["has_more"],
        # Курсор — uuid последней заявки порции (keyset по submitted_at, id).
        "next_cursor": rows[-1]["uuid"] if portion["has_more"] and rows else None,
    }


def _record_content_reads(request_ids, *, reviewer_id: int, ip, user_agent) -> None:
    """content_read на каждую заявку, содержимое которой раскрывается."""
    for request_id in request_ids:
        record_event(
            event="student_verification_content_read",
            actor=Actor.user(int(reviewer_id), "supervisor"),
            target=Target(storage.ENTITY_TYPE, request_id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
        )


def get_card_for_review(
    request_uuid,
    *,
    reviewer_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Карточка с полным номером и первой порцией истории. Порядок fail-closed:
    выборка → расшифровка в памяти → content_read (INDEPENDENT + RAISE) на
    текущую заявку и на каждую ДРУГУЮ заявку порции с раскрываемым пояснением
    отказа → ответ. AuditError пробрасывается: route отдаёт 503 без номера и
    пояснений.
    """
    row = storage.get_card(request_uuid, history_size=storage.HISTORY_PAGE_SIZE)
    if row is None:
        raise errors.VerificationNotFound()

    ticket_number = decrypt_text(row["ticket_number_enc"])
    reason = None
    if row["status"] == "rejected" and row.get("rejection_reason_enc"):
        reason = decrypt_text(row["rejection_reason_enc"])
    history_reasons = _history_reasons(row["history"]["rows"])

    # Текущая заявка — одно событие карточки (номер и её пояснение, в т.ч. в
    # её строке истории); прочие — по событию на раскрытое пояснение.
    revealed = [row["id"]] + sorted(
        rid for rid in history_reasons if rid != row["id"]
    )
    _record_content_reads(
        revealed, reviewer_id=reviewer_id, ip=ip, user_agent=user_agent,
    )

    card = _list_item_dto(row)
    card.update({
        "ticket_number": ticket_number,
        "rejection_reason": reason,
        "can_review": row["status"] == "pending" and row["user_id"] != int(reviewer_id),
        "history": _history_dto(
            row["history"], current_id=row["id"], reasons=history_reasons,
        ),
    })
    return card


def get_history_for_review(
    request_uuid,
    *,
    before=None,
    size: int = storage.HISTORY_PAGE_SIZE,
    reviewer_id: int,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Следующая порция истории («Показать ещё»). Номеров билетов нет; пояснения
    отказов отдаются только после content_read на каждую заявку порции, чьё
    пояснение раскрывается (порция без пояснений — без аудита, как список).
    Отдельный ответ — отдельное раскрытие, поэтому событие пишется и за
    исходную заявку, если её пояснение попало в эту порцию.
    """
    portion = storage.get_history(request_uuid, before_uuid=before, size=size)
    if portion is None:
        raise errors.VerificationNotFound()
    reasons = _history_reasons(portion["rows"])
    _record_content_reads(
        sorted(reasons), reviewer_id=reviewer_id, ip=ip, user_agent=user_agent,
    )
    return _history_dto(portion, current_id=portion["current_id"], reasons=reasons)


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
