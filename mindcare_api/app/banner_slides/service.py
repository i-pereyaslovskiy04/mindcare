from typing import Optional

from app.audit import Actor
from app.audit.request_context import build_request_context
from app.banner_slides import storage
from app.db.session import SessionLocal


def _audit_actor_ctx(actor_id, actor_role, ip, user_agent):
    return (
        Actor.user(int(actor_id), actor_role),
        build_request_context(ip=ip, user_agent=user_agent),
    )


class BannerSlideError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


def list_banner_slides(
    include_inactive: bool = False, placement: Optional[str] = None
) -> list[dict]:
    with SessionLocal() as db:
        return storage.get_banner_slides(
            db, include_inactive=include_inactive, placement=placement
        )


def list_public_banner_slides(placement: str = "home") -> list[dict]:
    with SessionLocal() as db:
        return storage.get_banner_slides(db, include_inactive=False, placement=placement)


def create_banner_slide(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_banner_slide(data, db, actor=actor, context=ctx)
        db.commit()
    return result


def update_banner_slide(
    slide_id: int, updates: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        slide = storage.get_banner_slide(slide_id, db)
        if slide is None:
            raise BannerSlideError("Слайд не найден", status_code=404)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.update_banner_slide(slide, updates, db, actor=actor, context=ctx)
        db.commit()
    return result


def delete_banner_slide(
    slide_id: int, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> None:
    with SessionLocal() as db:
        slide = storage.get_banner_slide(slide_id, db)
        if slide is None:
            raise BannerSlideError("Слайд не найден", status_code=404)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        storage.delete_banner_slide(slide, db, actor=actor, context=ctx)
        db.commit()
