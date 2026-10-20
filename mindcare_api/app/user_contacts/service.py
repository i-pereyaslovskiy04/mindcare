"""
Контакты пользователя — бизнес-логика БЕЗ FastAPI/HTTP (ADR-032).

Service получает уже проверенный actor-контекст (context.py) и отвечает
доменными ошибками (errors.py); HTTP-зависимости, HTTPException, определение
роли по membership и маппинг ошибок в статусы остаются в routes*. AuditError
(сбой обязательного аудита) пробрасывается как есть — route превращает его в 503.

Чтение сотрудником: значения читаются и расшифровываются в памяти, затем
записывается user_contacts_content_read (INDEPENDENT + RAISE), и только потом
они возвращаются: при сбое аудита данные не отдаются. Если раскрывать нечего
(нет ни контактов, ни основного телефона) — события нет. Чтение владельцем своих
контактов отдельного события не пишет (свои данные).
"""
from typing import Optional

from app.audit import Actor, Outcome, Target, record_event
from app.audit.request_context import build_request_context
from app.user_contacts import catalog, storage, validators
from app.user_contacts.context import OwnerContext, StaffContext
from app.user_contacts.errors import ContactsNotAvailable


def _owner_dto(version: int, updated_at, items: list, **extra) -> dict:
    return {
        "version": version,
        "updated_at": updated_at,
        "items": items,
        "limits": catalog.limits_dto(),
        "catalog": catalog.catalog_dto(),
        **extra,
    }


def get_my_contacts(user_id: int) -> dict:
    snapshot = storage.read_snapshot(user_id)
    if snapshot is None:
        return _owner_dto(0, None, [])
    return _owner_dto(snapshot["version"], snapshot["updated_at"], snapshot["items"])


def save_my_contacts(
    ctx: OwnerContext,
    version: int,
    raw_items: list,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    items = validators.normalize_items(raw_items)   # ContactsValidationError
    result = storage.save_atomic(                    # ContactsVersionConflict
        ctx.user_id, version, items,
        actor_role=ctx.role, ip=ip, user_agent=user_agent,
    )
    return _owner_dto(
        result["version"], result["updated_at"], result["items"],
        changed=result["changed"],
    )


def read_for_staff(
    ctx: StaffContext,
    target_uuid,
    *,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    grant = storage.resolve_staff_grant(ctx.user_id, ctx.roles, target_uuid)
    if grant is None:
        raise ContactsNotAvailable()

    snapshot = storage.read_snapshot(grant["target_id"])
    items = snapshot["items"] if snapshot else []
    primary_phone = grant["primary_phone"] or None

    if items or primary_phone:
        record_event(
            event="user_contacts_content_read",
            actor=Actor.user(ctx.user_id, grant["acting_role"]),
            target=Target("user", grant["target_id"]),
            outcome=Outcome.SUCCESS,
            metadata={},
            context=build_request_context(ip=ip, user_agent=user_agent),
        )
    return {
        "primary_phone": primary_phone,
        "updated_at": snapshot["updated_at"] if snapshot else None,
        "items": items,
        "catalog": catalog.catalog_dto(),
    }
