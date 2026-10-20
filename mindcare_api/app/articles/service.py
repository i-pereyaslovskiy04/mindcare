from typing import Optional

from app.articles import storage


def list_articles(
    page: int,
    size: int,
    search: Optional[str],
    is_published: Optional[bool],
    category_id: Optional[int],
) -> tuple[list[dict], int]:
    return storage.find_articles(
        page=page,
        size=size,
        search=search,
        is_published=is_published,
        category_id=category_id,
    )


def list_articles_public(
    page: int,
    size: int,
    search: Optional[str],
    category_id: Optional[int],
) -> tuple[list[dict], int]:
    return storage.find_articles(
        page=page, size=size, search=search,
        category_id=category_id, public_only=True,
    )


def get_article(uuid: str) -> Optional[dict]:
    return storage.get_article_by_uuid(uuid)


def get_article_public(uuid: str) -> Optional[dict]:
    return storage.get_article_by_uuid(uuid, public_only=True)


def create_article(
    data: dict,
    created_by: int,
    *,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    return storage.create_article(
        title=data["title"].strip(),
        excerpt=data.get("excerpt"),
        content=data.get("content"),
        cover_image_uuid=data.get("cover_image_uuid"),
        category_ids=data.get("category_ids", []),
        tag_uuids=data.get("tag_uuids", []),
        is_published=data.get("is_published", False),
        published_at=data.get("published_at"),
        created_by=created_by,
        actor_role=actor_role,
        ip=ip,
        user_agent=user_agent,
    )


def update_article(
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
    result = storage.update_article(
        uuid, data,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    )
    if result is None:
        raise ValueError("Материал не найден")
    return result


def delete_article(
    uuid: str,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    if not storage.delete_article(
        uuid,
        actor_id=actor_id, actor_role=actor_role, ip=ip, user_agent=user_agent,
    ):
        raise ValueError("Материал не найден")


def get_categories() -> list[dict]:
    return storage.list_categories()
