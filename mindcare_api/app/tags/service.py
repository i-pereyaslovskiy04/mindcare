from typing import Optional

from app.tags import storage
from app.tags.schemas import (
    AdminTagListQuery,
    TagCreate,
    TagUpdate,
    TagRead,
    PaginatedTagsResponse,
)
from app.auth.service import AuthError


def _normalize(name: str) -> str:
    """
    Нормализует имя тега: обрезает пробелы, первая буква заглавная, остальные строчные.
    "ТРЕВОГА" → "Тревога", "управление стрессом" → "Управление стрессом"
    """
    name = name.strip()
    if not name:
        return name
    return name[0].upper() + name[1:].lower()


def get_tags_list(query: AdminTagListQuery) -> PaginatedTagsResponse:
    items_raw, total = storage.find_tags(
        page=query.page,
        size=query.size,
        search=query.search,
    )
    items = [TagRead.model_validate(item) for item in items_raw]
    return PaginatedTagsResponse(items=items, total=total, page=query.page, size=query.size)


def create_tag(
    data: TagCreate,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    name = _normalize(data.name)
    if not name:
        raise AuthError("Название тега не может быть пустым", status_code=400)
    try:
        return storage.create_tag(
            name,
            actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
        )
    except ValueError as e:
        raise AuthError(str(e), status_code=409)


def update_tag(
    uuid: str,
    data: TagUpdate,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    name = _normalize(data.name)
    if not name:
        raise AuthError("Название тега не может быть пустым", status_code=400)
    try:
        return storage.update_tag(
            uuid, name,
            actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
        )
    except ValueError as e:
        msg = str(e)
        status = 404 if "не найден" in msg else 409
        raise AuthError(msg, status_code=status)


def delete_tag(
    uuid: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    found = storage.delete_tag(
        uuid,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if not found:
        raise AuthError("Тег не найден", status_code=404)


def get_tags_public(search=None, limit=20):
    return storage.find_tags_public(search=search, limit=limit)
