"""
Outbox system-сообщений — весь SQLAlchemy (ADR-029).

enqueue_in_tx пишет намерение в ПЕРЕДАННУЮ транзакцию бизнес-операции без
commit; остальные функции — короткие собственные транзакции доставки.
Ошибки БД здесь не глотаются: решение «soft-fail или ненулевой код» принимает
вызывающий (post-commit шаг операции или retry-job).
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import SystemMessageIntent
from app.db.session import SessionLocal
from app.notifications.templates import MESSAGE_TEMPLATES


def _intent_to_dict(row: SystemMessageIntent) -> dict:
    return {
        "id": row.id,
        "recipient_id": row.recipient_id,
        "event_key": row.event_key,
        "message_code": row.message_code,
    }


def enqueue_in_tx(db, *, recipient_id: int, event_key: str, message_code: str) -> None:
    """
    Добавляет намерение доставки в транзакцию вызывающего (commit — его).

    ON CONFLICT (recipient_id, event_key) DO NOTHING: повтор того же ключа не
    порождает IntegrityError и не ломает UoW (регистрация/решение), а второе
    намерение не создаётся. Неизвестный код — ошибка программирования (до
    записи): иначе намерение никогда не было бы доставлено.
    """
    if message_code not in MESSAGE_TEMPLATES:
        raise ValueError("unknown system message code")
    db.execute(
        pg_insert(SystemMessageIntent)
        .values(
            recipient_id=int(recipient_id),
            event_key=event_key,
            message_code=message_code,
        )
        .on_conflict_do_nothing(constraint="ux_system_message_intents_key")
    )


def get_undelivered(limit: int) -> list[dict]:
    """Недоставленные намерения по возрастанию id (старые — первыми)."""
    with SessionLocal() as db:
        rows = (
            db.query(SystemMessageIntent)
            .filter(SystemMessageIntent.delivered_at.is_(None))
            .order_by(SystemMessageIntent.id)
            .limit(int(limit))
            .all()
        )
        return [_intent_to_dict(r) for r in rows]


def count_undelivered() -> int:
    with SessionLocal() as db:
        return db.query(func.count(SystemMessageIntent.id)).filter(
            SystemMessageIntent.delivered_at.is_(None),
        ).scalar() or 0


def get_undelivered_by_key(recipient_id: int, event_key: str) -> Optional[dict]:
    with SessionLocal() as db:
        row = (
            db.query(SystemMessageIntent)
            .filter(
                SystemMessageIntent.recipient_id == int(recipient_id),
                SystemMessageIntent.event_key == event_key,
                SystemMessageIntent.delivered_at.is_(None),
            )
            .first()
        )
        return _intent_to_dict(row) if row is not None else None


def mark_delivered(intent_id: int) -> bool:
    """delivered_at — только один раз (условный UPDATE). True — отметили сейчас."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        updated = (
            db.query(SystemMessageIntent)
            .filter(
                SystemMessageIntent.id == int(intent_id),
                SystemMessageIntent.delivered_at.is_(None),
            )
            .update({"delivered_at": now}, synchronize_session=False)
        )
        db.commit()
        return bool(updated)


def record_attempt(intent_id: int) -> None:
    """Счётчик неудачных попыток публикации (без текста ошибки)."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.query(SystemMessageIntent).filter(
            SystemMessageIntent.id == int(intent_id),
            SystemMessageIntent.delivered_at.is_(None),
        ).update(
            {
                "attempts": SystemMessageIntent.attempts + 1,
                "last_attempt_at": now,
            },
            synchronize_session=False,
        )
        db.commit()
