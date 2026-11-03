"""
Область «клиент психолога» для карточки клиента (storage-уровень, SQLAlchemy).

Право психолога на данные клиента — строгое активное сопровождение
(status = 'active' AND ended_at IS NULL, NULL-безопасно) с существующим
активным клиентом (deleted_at IS NULL AND is_active IS TRUE). Роли клиента не
проверяются: клиент может иметь staff-роли (тот же предикат, что у карточки,
контактов ADR-032 и заданий ADR-033).

lock_client_scope берёт строку сопровождения И строку клиента
SELECT … FOR SHARE OF therapy_engagements, users в транзакции вызывающего —
до чтения содержимого. Пока транзакция открыта, закрытие/передача
сопровождения (UPDATE therapy_engagements) и отключение клиента (ADR-028:
users FOR UPDATE → UPDATE) ждут её конца; изменение, зафиксированное раньше,
FOR SHARE видит после ожидания (свежая версия строки) → None. Блокировки
разделяемые, последующих UPDATE этих строк в путях чтения нет — цикла нет
(та же схема, что assignments.storage.list_psychologist_page).
"""
from typing import Optional

from sqlalchemy import and_, select

from app.db.models import TherapyEngagement as TE, User

STRICT_ACTIVE = and_(
    TE.status.is_not(None), TE.status == "active", TE.ended_at.is_(None),
)
CLIENT_AVAILABLE = and_(User.deleted_at.is_(None), User.is_active.is_(True))


def lock_client_scope(
    db,
    psychologist_id: int,
    *,
    client_uuid=None,
    client_id: Optional[int] = None,
) -> Optional[tuple[int, int]]:
    """
    (engagement_id, client_id) текущего строгого сопровождения psychologist →
    клиент (по uuid ИЛИ id), строки сопровождения и клиента под FOR SHARE.
    Нет клиента / сопровождения / клиент отключён → None (один результат).
    """
    if (client_uuid is None) == (client_id is None):
        raise ValueError("lock_client_scope: укажите ровно один из client_uuid/client_id")
    stmt = (
        select(TE.id, User.id)
        .join(User, User.id == TE.client_id)
        .where(TE.psychologist_id == int(psychologist_id), STRICT_ACTIVE, CLIENT_AVAILABLE)
    )
    if client_uuid is not None:
        stmt = stmt.where(User.uuid == client_uuid)
    else:
        stmt = stmt.where(User.id == int(client_id))
    row = db.execute(
        stmt.order_by(TE.id).limit(1).with_for_update(read=True, of=(TE, User))
    ).first()
    if row is None:
        return None
    return int(row[0]), int(row[1])
