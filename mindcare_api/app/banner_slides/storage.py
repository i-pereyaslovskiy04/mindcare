"""
Storage layer для модуля banner_slides.
Все запросы к БД изолированы здесь.
"""

import uuid as _uuid
from datetime import datetime, timezone
from typing import Optional

from app.audit import Actor, Outcome, RequestContext, Target, record_event
from app.db.models import BannerSlide, MediaFile


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
            "banner_slides audit requires authenticated user actor context"
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


def _slide_to_dict(slide: BannerSlide, db) -> dict:
    image_url = None
    image_uuid = None
    if slide.image_id:
        mf = db.query(MediaFile).filter(MediaFile.id == slide.image_id).first()
        if mf:
            image_url = mf.file_path
            image_uuid = str(mf.uuid)

    return {
        "id":            slide.id,
        "uuid":          str(slide.uuid),
        "label":         slide.label,
        "title":         slide.title,
        "highlight":     slide.highlight,
        "sub":           slide.sub,
        "image_uuid":    image_uuid,
        "image_url":     image_url,
        "link_url":      slide.link_url,
        "placement":     slide.placement,
        "display_order": slide.display_order,
        "is_active":     slide.is_active,
        "created_at":    slide.created_at,
        "updated_at":    slide.updated_at,
    }


def get_banner_slides(
    db, include_inactive: bool = False, placement: Optional[str] = None
) -> list[dict]:
    q = db.query(BannerSlide)
    if not include_inactive:
        q = q.filter(BannerSlide.is_active.is_(True))
    if placement is not None:
        q = q.filter(BannerSlide.placement == placement)
    rows = q.order_by(BannerSlide.display_order, BannerSlide.id).all()
    return [_slide_to_dict(s, db) for s in rows]


def get_banner_slide(slide_id: int, db) -> Optional[BannerSlide]:
    return db.query(BannerSlide).filter(BannerSlide.id == slide_id).first()


def create_banner_slide(
    data: dict, db, *, actor: Actor, context: RequestContext
) -> dict:
    _require_actor(actor, context)
    now = datetime.now(timezone.utc)
    image_uuid = data.pop("image_uuid", None)
    slide = BannerSlide(
        **data,
        image_id=_resolve_image(image_uuid, db),
        created_at=now,
        updated_at=now,
    )
    db.add(slide)
    db.flush()
    db.refresh(slide)
    record_event(
        event="banner_slide_created", actor=actor,
        target=Target("banner_slide", slide.id), outcome=Outcome.SUCCESS,
        metadata={}, context=context, db=db,
    )
    return _slide_to_dict(slide, db)


def update_banner_slide(
    slide: BannerSlide, updates: dict, db, *, actor: Actor, context: RequestContext
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

    is_active_before = slide.is_active
    non_status_diff = {
        k: v for k, v in resolved.items()
        if k != "is_active" and getattr(slide, k) != v
    }
    is_active_after = resolved.get("is_active", is_active_before)
    is_active_changed = "is_active" in resolved and is_active_after != is_active_before

    if not non_status_diff and not is_active_changed:
        return _slide_to_dict(slide, db)   # no-op: ORM/updated_at/audit не трогаем

    for k, v in resolved.items():
        setattr(slide, k, v)
    slide.updated_at = datetime.now(timezone.utc)
    db.flush()
    db.refresh(slide)

    if non_status_diff:
        record_event(
            event="banner_slide_updated", actor=actor,
            target=Target("banner_slide", slide.id), outcome=Outcome.SUCCESS,
            metadata={}, context=context, db=db,
        )
    if is_active_changed:
        record_event(
            event=("banner_slide_activated" if is_active_after
                   else "banner_slide_deactivated"),
            actor=actor, target=Target("banner_slide", slide.id),
            outcome=Outcome.SUCCESS, metadata={}, context=context, db=db,
        )
    return _slide_to_dict(slide, db)


def delete_banner_slide(
    slide: BannerSlide, db, *, actor: Actor, context: RequestContext
) -> None:
    """Физическое удаление — не soft-delete. У banner_slides нет входящих FK
    (никто на неё не ссылается), в отличие от meeting_types/categories, так
    что запись без последствий для другой строки; is_active остаётся
    отдельным, обратимым способом временно скрыть слайд."""
    _require_actor(actor, context)
    slide_id = slide.id
    record_event(
        event="banner_slide_deleted", actor=actor,
        target=Target("banner_slide", slide_id), outcome=Outcome.SUCCESS,
        metadata={}, context=context, db=db,
    )
    db.delete(slide)
    db.flush()
