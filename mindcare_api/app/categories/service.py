from typing import Optional

from app.categories import storage
from app.categories.schemas import (
    AdminCategoriesListQuery,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    PaginatedCategoriesResponse,
)
from app.auth.service import AuthError


def get_categories_list(
    query: AdminCategoriesListQuery,
) -> PaginatedCategoriesResponse:
    items_raw, total = storage.find_categories(
        page=query.page,
        size=query.size,
        search=query.search,
        is_active=query.is_active,
    )
    items = [CategoryRead.model_validate(item) for item in items_raw]
    return PaginatedCategoriesResponse(
        items=items,
        total=total,
        page=query.page,
        size=query.size,
    )


def get_category(category_id: int) -> Optional[dict]:
    return storage.get_category_by_id(category_id)


def create_category(
    data: CategoryCreate,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    try:
        result = storage.create_category(
            name=data.name,
            slug=data.slug,
            description=data.description,
            display_order=data.display_order,
            is_active=data.is_active,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=ip,
            user_agent=user_agent,
        )
    except ValueError as e:
        msg = str(e)
        status = 409 if "уже используется" in msg else 400
        raise AuthError(msg, status_code=status)
    return result


def update_category(
    category_id: int,
    data: CategoryUpdate,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    try:
        result = storage.update_category(
            category_id, data.model_dump(exclude_unset=True),
            actor_id=actor_id,
            actor_role=actor_role,
            ip=ip,
            user_agent=user_agent,
        )
    except ValueError as e:
        msg = str(e)
        status = 409 if "уже используется" in msg else 400
        raise AuthError(msg, status_code=status)

    if result is None:
        raise AuthError("Категория не найдена", status_code=404)
    return result


def delete_category(
    category_id: int,
    *,
    actor_id: Optional[int] = None,
    actor_role: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    found = storage.deactivate_category(
        category_id,
        actor_id=actor_id,
        actor_role=actor_role,
        ip=ip,
        user_agent=user_agent,
    )
    if not found:
        raise AuthError("Категория не найдена", status_code=404)
