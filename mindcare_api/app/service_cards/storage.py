"""
Storage layer для модуля service_cards.
Все запросы к БД изолированы здесь.
"""

import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from app.audit import Actor, Outcome, RequestContext, Target, record_event
from app.db.models import MediaFile, ServiceCard


def _require_actor(actor, context) -> None:
    """Fail-closed guard: audit требует подтверждённый user-actor + context
    (готовые объекты строит service). Проверка ДО любой мутации."""
    if (
        not isinstance(actor, Actor)
        or actor.kind != "user"
        or not isinstance(actor.user_id, int)
        or isinstance(actor.user_id, bool)
        or actor.user_id <= 0
        or not isinstance(actor.role, str)
        or not actor.role
        or not isinstance(context, RequestContext)
    ):
        raise RuntimeError(
            "service_cards audit requires authenticated user actor context"
        )


def _resolve_image(uuid_str: Optional[str], db) -> Optional[int]:
    """Резолвит UUID картинки в integer FK или возвращает None."""
    if not uuid_str:
        return None
    try:
        uuid_obj = _uuid.UUID(uuid_str)
    except ValueError:
        return None
    mf = db.query(MediaFile).filter(
        MediaFile.uuid == uuid_obj,
        MediaFile.is_active.is_(True),
    ).first()
    return mf.id if mf else None


def _card_to_dict(card: ServiceCard, db) -> dict:
    image_url = None
    image_uuid = None
    if card.image_id:
        mf = db.query(MediaFile).filter(MediaFile.id == card.image_id).first()
        if mf:
            image_url = mf.file_path
            image_uuid = str(mf.uuid)

    return {
        "id":            card.id,
        "uuid":          str(card.uuid),
        "title":         card.title,
        "description":   card.description,
        "benefits":      card.benefits or [],
        "image_uuid":    image_uuid,
        "image_url":     image_url,
        "link_url":      card.link_url,
        "display_order": card.display_order,
        "is_active":     card.is_active,
        "created_at":    card.created_at,
        "updated_at":    card.updated_at,
    }


def get_service_cards(db, include_inactive: bool = False) -> list[dict]:
    q = db.query(ServiceCard)
    if not include_inactive:
        q = q.filter(ServiceCard.is_active.is_(True))
    rows = q.order_by(ServiceCard.display_order, ServiceCard.id).all()
    return [_card_to_dict(c, db) for c in rows]


def get_service_card(card_id: int, db) -> Optional[ServiceCard]:
    return db.query(ServiceCard).filter(ServiceCard.id == card_id).first()


def create_service_card(
    data: dict, db, *, actor: Actor, context: RequestContext
) -> dict:
    _require_actor(actor, context)
    now = datetime.now(timezone.utc)
    image_uuid = data.pop("image_uuid", None)
    card = ServiceCard(
        **data,
        image_id=_resolve_image(image_uuid, db),
        created_at=now,
        updated_at=now,
    )
    db.add(card)
    db.flush()
    db.refresh(card)
    record_event(
        event="service_card_created", actor=actor,
        target=Target("service_card", card.id), outcome=Outcome.SUCCESS,
        metadata={}, context=context, db=db,
    )
    return _card_to_dict(card, db)


def update_service_card(
    card: ServiceCard, updates: dict, db, *, actor: Actor, context: RequestContext
) -> dict:
    """is_active — семантически значимый boolean-переход, поэтому выделен в
    отдельные события (activated/deactivated), не тонет в generic updated.
    Combined PATCH (обычные поля + is_active) пишет ДВЕ непересекающиеся
    строки. Identical PATCH (нет реального diff нигде) — no-op: без мутации,
    без сдвига updated_at, без audit."""
    _require_actor(actor, context)

    resolved = dict(updates)
    if "image_uuid" in resolved:
        resolved["image_id"] = _resolve_image(resolved.pop("image_uuid"), db)

    is_active_before = card.is_active
    non_status_diff = {
        k: v for k, v in resolved.items()
        if k != "is_active" and getattr(card, k) != v
    }
    is_active_after = resolved.get("is_active", is_active_before)
    is_active_changed = "is_active" in resolved and is_active_after != is_active_before

    if not non_status_diff and not is_active_changed:
        return _card_to_dict(card, db)   # no-op: ORM/updated_at/audit не трогаем

    for k, v in resolved.items():
        setattr(card, k, v)
    card.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(card)

    if non_status_diff:
        record_event(
            event="service_card_updated", actor=actor,
            target=Target("service_card", card.id), outcome=Outcome.SUCCESS,
            metadata={}, context=context, db=db,
        )
    if is_active_changed:
        record_event(
            event=("service_card_activated" if is_active_after
                   else "service_card_deactivated"),
            actor=actor, target=Target("service_card", card.id),
            outcome=Outcome.SUCCESS, metadata={}, context=context, db=db,
        )
    return _card_to_dict(card, db)


def delete_service_card(
    card: ServiceCard, db, *, actor: Actor, context: RequestContext
) -> None:
    """Физическое удаление — не soft-delete. У service_cards нет входящих FK
    (никто на неё не ссылается), в отличие от meeting_types/categories, так
    что запись без последствий для другой строки; is_active остаётся
    отдельным, обратимым способом временно скрыть карточку."""
    _require_actor(actor, context)
    card_id = card.id
    record_event(
        event="service_card_deleted", actor=actor,
        target=Target("service_card", card_id), outcome=Outcome.SUCCESS,
        metadata={}, context=context, db=db,
    )
    db.delete(card)
    db.flush()
