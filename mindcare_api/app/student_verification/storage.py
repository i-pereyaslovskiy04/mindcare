"""
Подтверждение студента ДонГУ — весь SQLAlchemy (ADR-029).

Порядок блокировок (без дедлоков и без перехода FOR SHARE → UPDATE, ADR-028):

  * подача — строка users заявителя FOR UPDATE, затем чтение его заявок;
  * решение — строки users заявителя И reviewer'а FOR UPDATE в общем порядке
    по users.id, затем заявка FOR UPDATE.

Reviewer блокируется явно: FK reviewed_by и FK actor'а audit_log (user_id)
берут на его строку FOR KEY SHARE, а она несовместима с FOR UPDATE. Без явной
блокировки в общем порядке два supervisor'а, проверяющие заявки друг друга,
держали бы строку заявителя и ждали бы строку reviewer'а крест-накрест.

Минимизация SELECT. ORM-сущности User и StudentVerificationRequest здесь НЕ
загружаются: каждое чтение — явная проекция нужных колонок (Row без
lazy-загрузки, обращение к невыбранному полю — AttributeError, а не скрытый
SELECT). Список и история — только метаданные; собственный статус — без номера,
пояснение отказа читается отдельным запросом только для rejected; карточка —
ciphertext номера/пояснения, но не auth-поля users (password_hash,
deactivation_reason_enc и пр.). Блокировки users выбирают только id и признаки
lifecycle. Identity map не участвует, поэтому повторное чтение заявки под
блокировкой всегда возвращает свежее состояние БД (в т.ч. после ожидания).

Санитизация. Неожиданная SQLAlchemyError содержит SQL и параметры: при
записи (flush / UPDATE / outbox / commit) — ciphertext номера или пояснения,
при чтении — введённый supervisor'ом search (ФИО/email), uuid заявки, id
пользователя. Она перехватывается на КАЖДОМ обращении к БД модуля — чтениях
list_requests / get_latest_for_user / get_card и предварительных чтениях
(блокировках) подачи и решения (phase=read) — и при записи; транзакция
откатывается, в stderr — только операция, фаза и класс исключения, наружу —
VerificationStorageError, созданная ВНЕ блока except и поднятая `from None`
(ни __cause__, ни __context__). Доменные отказы (VerificationError) не
SQLAlchemyError и проходят как есть. Известные конфликты ограничений
(ux_svr_user_pending / ux_svr_user_approved) сохраняют typed codes.
"""
import sys
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import aliased

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.auth.roles import is_pure_student
from app.auth.storage import get_active_role_names
from app.core.encryption import encrypt_text
from app.db.models import StudentVerificationRequest as SVR, User
from app.db.session import SessionLocal
from app.notifications import storage as outbox
from app.notifications.templates import (
    STUDENT_VERIFICATION_APPROVED, STUDENT_VERIFICATION_REJECTED,
    result_event_key,
)
from app.student_verification import errors

ENTITY_TYPE = "student_verification_request"
_PENDING_CONSTRAINT = "ux_svr_user_pending"
_APPROVED_CONSTRAINT = "ux_svr_user_approved"

_DECISION_STATUS = {"approve": "approved", "reject": "rejected"}
_DECISION_EVENT = {
    "approved": "student_verification_approved",
    "rejected": "student_verification_rejected",
}
_DECISION_MESSAGE = {
    "approved": STUDENT_VERIFICATION_APPROVED,
    "rejected": STUDENT_VERIFICATION_REJECTED,
}

_Reviewer = aliased(User)

# ── Явные проекции колонок ───────────────────────────────────────────────────
# Метаданные заявки: без ticket_number_enc и rejection_reason_enc.
_META = (
    SVR.id, SVR.uuid, SVR.user_id, SVR.status, SVR.faculty_code,
    SVR.submitted_at, SVR.reviewed_at, SVR.reviewed_by,
)
# Заявитель — только то, что видит supervisor; auth-полей users нет.
_APPLICANT = (
    User.uuid.label("applicant_uuid"),
    User.full_name.label("applicant_full_name"),
    User.email.label("applicant_email"),
    User.is_active.label("applicant_is_active"),
    User.deleted_at.label("applicant_deleted_at"),
)
_REVIEWER = (_Reviewer.full_name.label("reviewer_full_name"),)
# Блокировка users — только id и признаки lifecycle.
_LOCK_USER = (User.id, User.is_active, User.deleted_at)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _constraint_name(exc: IntegrityError) -> Optional[str]:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


# ── Санитизация технических сбоев записи ──────────────────────────────────────

def _diag(operation: str, phase: str, error_class: str) -> None:
    # Только операция, фаза и класс: без SQL, параметров, id и str(exc).
    print(
        f"[STUDENT_VERIFICATION] op={operation} phase={phase} error={error_class}",
        file=sys.stderr,
    )


def _rollback_quietly(db, operation: str) -> None:
    try:
        db.rollback()
    except Exception as exc:   # noqa: BLE001 — rollback best-effort
        _diag(operation, "rollback", type(exc).__name__)


def _storage_failure(db, operation: str, phase: str, error_class: str):
    """Откат + диагностика → безопасное исключение (вызывать ВНЕ except)."""
    _rollback_quietly(db, operation)
    _diag(operation, phase, error_class)
    return errors.VerificationStorageError()


def _commit(db, operation: str) -> None:
    """Единственный commit операции; неожиданная SQLAlchemyError санитизируется."""
    error_class = None
    try:
        db.commit()
    except SQLAlchemyError as exc:
        error_class = type(exc).__name__
    if error_class is not None:
        raise _storage_failure(db, operation, "commit", error_class) from None


# ── Блокировки и DTO ──────────────────────────────────────────────────────────

def _is_inactive(user) -> bool:
    return user is None or user.deleted_at is not None or user.is_active is False


def lock_user(db, user_id: int):
    """users FOR UPDATE — проекция (id, is_active, deleted_at); soft-deleted
    тоже блокируется. Auth-поля (password_hash и пр.) не выбираются."""
    return (
        db.query(*_LOCK_USER)
        .filter(User.id == int(user_id))
        .with_for_update()
        .first()
    )


def lock_users_in_order(db, user_ids) -> dict:
    """Строки users FOR UPDATE строго по возрастанию id (общий порядок)."""
    locked = {}
    for uid in sorted({int(u) for u in user_ids}):
        locked[uid] = lock_user(db, uid)
    return locked


def lock_request(db, request_id: int):
    """Заявка FOR UPDATE — метаданные без ciphertext. Проекция (не сущность),
    поэтому после ожидания блокировки значения всегда свежие из БД."""
    return (
        db.query(*_META)
        .filter(SVR.id == int(request_id))
        .with_for_update()
        .one()
    )


def _meta_dict(row) -> dict:
    return {
        "id": row.id,
        "uuid": str(row.uuid),
        "user_id": row.user_id,
        "status": row.status,
        "faculty_code": row.faculty_code,
        "submitted_at": row.submitted_at,
        "reviewed_at": row.reviewed_at,
        "reviewed_by": row.reviewed_by,
    }


def _list_dict(row) -> dict:
    data = _meta_dict(row)
    data["student"] = {
        "uuid": str(row.applicant_uuid),
        "full_name": row.applicant_full_name,
        "email": row.applicant_email,
        # NULL is_active = активен (ADR-028); soft-deleted — не активен.
        "is_active": (
            row.applicant_is_active is not False
            and row.applicant_deleted_at is None
        ),
    }
    data["reviewer"] = (
        {"full_name": row.reviewer_full_name}
        if row.reviewer_full_name is not None else None
    )
    return data


def _with_people(query):
    return (
        query.join(User, User.id == SVR.user_id)
        .outerjoin(_Reviewer, _Reviewer.id == SVR.reviewed_by)
    )


# ── self-service ──────────────────────────────────────────────────────────────

def get_latest_for_user(user_id: int) -> Optional[dict]:
    """
    Последняя заявка пользователя: метаданные без номера билета. Пояснение
    отказа (ciphertext) читается отдельным запросом и только для rejected.
    """
    with SessionLocal() as db:
        error_class = None
        try:
            row = (
                db.query(*_META)
                .filter(SVR.user_id == int(user_id))
                .order_by(SVR.submitted_at.desc(), SVR.id.desc())
                .first()
            )
            reason_enc = None
            if row is not None and row.status == "rejected":
                reason_enc = (
                    db.query(SVR.rejection_reason_enc)
                    .filter(SVR.id == row.id)
                    .scalar()
                )
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _storage_failure(db, "status", "read", error_class) from None
    if row is None:
        return None
    data = _meta_dict(row)
    data["rejection_reason_enc"] = reason_enc
    return data


def submit_atomic(
    user_id: int,
    *,
    faculty_code: str,
    ticket_number: str,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """
    Подача заявки одной транзакцией:
      1. users заявителя FOR UPDATE (сериализует подачи, решения по его заявкам,
         login/lifecycle/membership);
      2. под блокировкой: аккаунт активен и не удалён, активные роли ровно
         {student}; статусы заявок: есть approved → AlreadyVerified, есть
         pending → VerificationPendingExists;
      3. INSERT pending с encrypt_text(номер) + student_verification_submitted
         (ATOMIC) → один commit. Сбой аудита/commit откатывает заявку.
    Нарушение ux_svr_user_pending / ux_svr_user_approved (недостижимо при
    сериализации, defense-in-depth) → те же typed codes; любая иная
    SQLAlchemyError flush/commit → VerificationStorageError без исходной цепочки.
    Возвращает метаданные без номера; строка после commit не перечитывается.
    """
    with SessionLocal() as db:
        error_class = None
        try:
            user = lock_user(db, user_id)
            if _is_inactive(user):
                raise errors.AccountInactive()
            if not is_pure_student(get_active_role_names(db, user.id)):
                raise errors.VerificationNotAllowed()
            statuses = {
                row.status for row in db.query(SVR.status).filter(
                    SVR.user_id == user.id,
                    SVR.status.in_(("pending", "approved")),
                ).all()
            }
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _storage_failure(db, "submit", "read", error_class) from None

        if "approved" in statuses:
            raise errors.AlreadyVerified()
        if "pending" in statuses:
            raise errors.VerificationPendingExists()

        req = SVR(
            user_id=user.id,
            faculty_code=faculty_code,
            ticket_number_enc=encrypt_text(ticket_number),
            status="pending",
        )
        db.add(req)
        error_class = None
        conflict = None
        try:
            db.flush()
        except IntegrityError as exc:
            error_class = type(exc).__name__
            conflict = _constraint_name(exc)
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            if conflict == _PENDING_CONSTRAINT:
                _rollback_quietly(db, "submit")
                raise errors.VerificationPendingExists()
            if conflict == _APPROVED_CONSTRAINT:
                _rollback_quietly(db, "submit")
                raise errors.AlreadyVerified()
            raise _storage_failure(db, "submit", "flush", error_class) from None

        # id — из INSERT … RETURNING, uuid — python-side default: без SELECT.
        result = {
            "id": req.id,
            "uuid": str(req.uuid),
            "user_id": user.id,
            "status": "pending",
            "faculty_code": faculty_code,
        }
        record_event(
            event="student_verification_submitted",
            actor=Actor.user(user.id, "student"),
            target=Target(ENTITY_TYPE, result["id"]),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )
        _commit(db, "submit")
        return result


# ── проверка supervisor'ом ─────────────────────────────────────────────────────

def list_requests(
    *, status: Optional[str], page: int, size: int, search: Optional[str] = None,
) -> tuple[list, int]:
    """
    Пагинированный список для supervisor — только метаданные (без номера и
    пояснения, без auth-полей users). Поиск — только по ФИО/email заявителя
    (по номеру билета не ищем: он зашифрован и в списке не раскрывается).
    pending — очередь FIFO, прочее — сначала новые.
    """
    filters = []
    if status is not None:
        filters.append(SVR.status == status)
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(or_(User.email.ilike(pattern), User.full_name.ilike(pattern)))

    with SessionLocal() as db:
        error_class = None
        try:
            total = (
                db.query(func.count(SVR.id))
                .select_from(SVR)
                .join(User, User.id == SVR.user_id)
                .filter(*filters)
                .scalar()
            ) or 0
            q = _with_people(
                db.query(*_META, *_APPLICANT, *_REVIEWER),
            ).filter(*filters)
            if status == "pending":
                q = q.order_by(SVR.submitted_at.asc(), SVR.id.asc())
            else:
                q = q.order_by(SVR.submitted_at.desc(), SVR.id.desc())
            rows = q.offset((page - 1) * size).limit(size).all()
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _storage_failure(db, "list", "read", error_class) from None
    return [_list_dict(row) for row in rows], total


def get_card(request_uuid) -> Optional[dict]:
    """
    Карточка: метаданные + ciphertext номера и пояснения (расшифровывает
    service после аудита) + история прочих заявок того же пользователя (только
    метаданные). Auth-поля users не выбираются.
    """
    with SessionLocal() as db:
        error_class = None
        history = []
        try:
            row = (
                _with_people(db.query(
                    *_META, SVR.ticket_number_enc, SVR.rejection_reason_enc,
                    *_APPLICANT, *_REVIEWER,
                ))
                .filter(SVR.uuid == request_uuid)
                .first()
            )
            if row is not None:
                history = (
                    db.query(*_META)
                    .filter(SVR.user_id == row.user_id, SVR.id != row.id)
                    .order_by(SVR.submitted_at.desc(), SVR.id.desc())
                    .all()
                )
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _storage_failure(db, "card", "read", error_class) from None
        if row is None:
            return None
        data = _list_dict(row)
        data["ticket_number_enc"] = row.ticket_number_enc
        data["rejection_reason_enc"] = row.rejection_reason_enc
        data["history"] = [
            {
                "uuid": str(h.uuid),
                "status": h.status,
                "faculty_code": h.faculty_code,
                "submitted_at": h.submitted_at,
                "reviewed_at": h.reviewed_at,
            }
            for h in history
        ]
        return data


def _reviewer_allowed(db, reviewer) -> bool:
    if _is_inactive(reviewer):
        return False
    return "supervisor" in get_active_role_names(db, reviewer.id)


def decide_atomic(
    request_uuid,
    *,
    decision: str,
    reviewer_id: int,
    reason: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[dict, bool]:
    """
    Решение по КОНКРЕТНОЙ заявке (uuid) одной транзакцией. Возвращает
    (метаданные заявки, changed). changed=False — истинный no-op (повтор того
    же решения): без события, намерения и уведомления.

      1. предварительное чтение (id, user_id) без блокировки → нет → NotFound;
         заявитель == reviewer → SelfReviewForbidden (ранний);
      2. users заявителя и reviewer'а FOR UPDATE в порядке users.id;
      3. ПОСЛЕ ожидания блокировок: reviewer активен, не удалён и имеет
         активную роль supervisor, иначе ReviewerNotAllowed;
      4. заявка FOR UPDATE (свежая проекция); заявитель == reviewer →
         SelfReviewForbidden (авторитетно);
      5. статус уже решён: тем же решением → no-op; другим →
         VerificationAlreadyDecided;
      6. approve при отключённом/удалённом заявителе → AccountInactive
         (reject допустим — очередь не должна зависать);
      7. условный UPDATE (… WHERE status='pending') + success-событие (ATOMIC)
         + outbox-намерение результата → один commit. Сбой аудита, намерения
         или commit откатывает всё вместе; неожиданная SQLAlchemyError →
         VerificationStorageError без исходной цепочки.
    """
    target_status = _DECISION_STATUS[decision]
    reviewer_id = int(reviewer_id)
    with SessionLocal() as db:
        error_class = None
        try:
            pre = (
                db.query(SVR.id, SVR.user_id)
                .filter(SVR.uuid == request_uuid)
                .first()
            )
            if pre is None:
                raise errors.VerificationNotFound()
            if pre.user_id == reviewer_id:
                raise errors.SelfReviewForbidden()

            locked = lock_users_in_order(db, (pre.user_id, reviewer_id))
            if not _reviewer_allowed(db, locked.get(reviewer_id)):
                raise errors.ReviewerNotAllowed()

            req = lock_request(db, pre.id)
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _storage_failure(db, "decide", "read", error_class) from None

        if req.user_id == reviewer_id:
            raise errors.SelfReviewForbidden()

        if req.status != "pending":
            if req.status == target_status:
                return _meta_dict(req), False
            raise errors.VerificationAlreadyDecided()

        if target_status == "approved" and _is_inactive(locked.get(req.user_id)):
            raise errors.AccountInactive()

        reviewed_at = _utcnow()
        values = {
            "status": target_status,
            "reviewed_by": reviewer_id,
            "reviewed_at": reviewed_at,
        }
        if target_status == "rejected":
            values["rejection_reason_enc"] = encrypt_text(reason)

        error_class = None
        updated = 0
        try:
            updated = db.execute(
                update(SVR)
                .where(SVR.id == req.id, SVR.status == "pending")
                .values(**values)
                .execution_options(synchronize_session=False)
            ).rowcount
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is None and updated != 1:
            error_class = "UnexpectedRowcount"   # под блокировкой недостижимо
        if error_class is not None:
            raise _storage_failure(db, "decide", "update", error_class) from None

        record_event(
            event=_DECISION_EVENT[target_status],
            actor=Actor.user(reviewer_id, "supervisor"),
            target=Target(ENTITY_TYPE, req.id),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
            db=db,
        )

        try:
            outbox.enqueue_in_tx(
                db,
                recipient_id=req.user_id,
                event_key=result_event_key(req.uuid),
                message_code=_DECISION_MESSAGE[target_status],
            )
        except SQLAlchemyError as exc:
            error_class = type(exc).__name__
        if error_class is not None:
            raise _storage_failure(db, "decide", "enqueue", error_class) from None

        _commit(db, "decide")
        data = _meta_dict(req)
        data.update(
            status=target_status, reviewed_by=reviewer_id, reviewed_at=reviewed_at,
        )
        return data, True
