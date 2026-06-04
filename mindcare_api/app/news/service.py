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


def create_news(data: dict, created_by: int) -> dict:
    return storage.create_news(
        title=data["title"].strip(),
        content=data.get("content"),
        cover_image_uuid=data.get("cover_image_uuid"),
        tag_uuids=data.get("tag_uuids", []),
        is_published=data.get("is_published", False),
        published_at=data.get("published_at"),
        created_by=created_by,
    )


def update_news(uuid: str, data: dict) -> Optional[dict]:
    if "title" in data and data["title"]:
        stripped = data["title"].strip()
        if not stripped:
            raise ValueError("Заголовок не может быть пустым")
        data["title"] = stripped
    result = storage.update_news(uuid, data)
    if result is None:
        raise ValueError("Новость не найдена")
    return result


def delete_news(uuid: str) -> None:
    if not storage.delete_news(uuid):
        raise ValueError("Новость не найдена")
