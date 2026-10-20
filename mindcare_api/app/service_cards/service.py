from typing import Optional

from app.audit import Actor
from app.audit.request_context import build_request_context
from app.service_cards import storage
from app.db.session import SessionLocal


def _audit_actor_ctx(actor_id, actor_role, ip, user_agent):
    return (
        Actor.user(int(actor_id), actor_role),
        build_request_context(ip=ip, user_agent=user_agent),
    )


class ServiceCardError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


# Явный null в generic PATCH на NOT NULL-поле должен быть отклонён 422 ДО
# мутации (mindcare_api/CLAUDE.md: "не отправлять в generic PATCH явный null
# для NOT NULL-поля").
_NOT_NULLABLE_FIELDS = {"title", "description", "benefits", "display_order", "is_active"}


def list_service_cards(include_inactive: bool = False) -> list[dict]:
    with SessionLocal() as db:
        return storage.get_service_cards(db, include_inactive=include_inactive)


def list_public_service_cards() -> list[dict]:
    with SessionLocal() as db:
        return storage.get_service_cards(db, include_inactive=False)


def create_service_card(
    data: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    with SessionLocal() as db:
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.create_service_card(data, db, actor=actor, context=ctx)
        db.commit()
    return result


def update_service_card(
    card_id: int, updates: dict, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> dict:
    for f in _NOT_NULLABLE_FIELDS:
        if f in updates and updates[f] is None:
            raise ServiceCardError(f"Поле «{f}» не может быть пустым.", status_code=422)

    with SessionLocal() as db:
        card = storage.get_service_card(card_id, db)
        if card is None:
            raise ServiceCardError("Карточка не найдена", status_code=404)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        result = storage.update_service_card(card, updates, db, actor=actor, context=ctx)
        db.commit()
    return result


def delete_service_card(
    card_id: int, *, actor_id, actor_role: str,
    ip: Optional[str] = None, user_agent: Optional[str] = None,
) -> None:
    with SessionLocal() as db:
        card = storage.get_service_card(card_id, db)
        if card is None:
            raise ServiceCardError("Карточка не найдена", status_code=404)
        actor, ctx = _audit_actor_ctx(actor_id, actor_role, ip, user_agent)
        storage.delete_service_card(card, db, actor=actor, context=ctx)
        db.commit()
