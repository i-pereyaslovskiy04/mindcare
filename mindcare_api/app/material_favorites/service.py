"""
Избранные материалы — бизнес-логика без FastAPI/HTTP (ADR-034).

Аудит: отдельных событий нет. Отметка «в избранном» — собственные настройки
пользователя без чужого доступа (как чтение своих контактов/заданий); журналы
не пополняются ни при добавлении, ни при чтении. Решение зафиксировано в ADR-034.
"""
from typing import Optional

from app.articles import storage as articles_storage
from app.material_favorites import storage


def favorite_ids(user_id: int) -> dict:
    uuids = storage.favorite_uuids(user_id)
    return {"uuids": uuids, "count": len(uuids)}


def list_favorites(
    user_id: int, *, page: int, size: int,
    search: Optional[str] = None, category_id: Optional[int] = None,
) -> dict:
    items, total = articles_storage.find_articles(
        page=page, size=size, search=search, category_id=category_id,
        public_only=True, favorite_user_id=user_id,
    )
    return {"items": items, "total": total, "page": page, "size": size}


def add_favorite(user_id: int, article_uuid) -> bool:
    return storage.add(user_id, article_uuid)


def remove_favorite(user_id: int, article_uuid) -> bool:
    return storage.remove(user_id, article_uuid)
