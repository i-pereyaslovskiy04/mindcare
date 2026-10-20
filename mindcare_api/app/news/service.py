from typing import Optional

from app.news import storage


def list_news(
    page: int,
    size: int,
    search: Optional[str],
    is_published: Optional[bool],
) -> tuple[list[dict], int]:
    return storage.find_news(
        page=page,
        size=size,
        search=search,
        is_published=is_published,
    )


def list_news_public(page: int, size: int, search: Optional[str]) -> tuple[list[dict], int]:
    return storage.find_news(page=page, size=size, search=search, public_only=True)


def get_news(uuid: str) -> Optional[dict]:
    return storage.get_news_by_uuid(uuid)


def get_news_public(uuid: str) -> Optional[dict]:
    return storage.get_news_by_uuid(uuid, public_only=True)


def create_news(
    data: dict,
    created_by: int,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    return storage.create_news(
        title=data["title"].strip(),
        content=data.get("content"),
        cover_image_uuid=data.get("cover_image_uuid"),
        tag_uuids=data.get("tag_uuids", []),
        is_published=data.get("is_published", False),
        published_at=data.get("published_at"),
        created_by=created_by,
        actor_role=actor_role,
        ip=ip,
        user_agent=user_agent,
    )


def update_news(
    uuid: str,
    data: dict,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[dict]:
    if "title" in data and data["title"]:
        stripped = data["title"].strip()
        if not stripped:
            raise ValueError("Заголовок не может быть пустым")
        data["title"] = stripped
    result = storage.update_news(
        uuid, data,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if result is None:
        raise ValueError("Новость не найдена")
    return result


def delete_news(
    uuid: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not storage.delete_news(
        uuid,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    ):
        raise ValueError("Новость не найдена")
