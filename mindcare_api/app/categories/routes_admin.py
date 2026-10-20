from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import Optional

from app.auth.deps import require_role, get_current_user, resolve_role_or_403
from app.categories import service
from app.categories.schemas import (
    AdminCategoriesListQuery,
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    PaginatedCategoriesResponse,
)

router = APIRouter(
    prefix="/admin/categories",
    tags=["admin: categories"],
    dependencies=[Depends(require_role("admin"))],
)


def _actor(current_user: dict) -> tuple[int, str]:
    return (
        int(current_user["id"]),
        resolve_role_or_403(current_user, allowed={"admin"}, preferred="admin"),
    )


@router.get("", response_model=PaginatedCategoriesResponse)
def list_categories(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=200),
    is_active: Optional[bool] = Query(default=None),
):
    """Список всех категорий с количеством связанных материалов."""
    query = AdminCategoriesListQuery(
        page=page, size=size, search=search, is_active=is_active,
    )
    return service.get_categories_list(query)


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: int):
    """Получить одну категорию по id."""
    cat = service.get_category(category_id)
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Категория не найдена",
        )
    return cat


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Создать новую категорию. Slug генерируется из name если не передан."""
    actor_id, actor_role = _actor(current_user)
    try:
        cat = service.create_category(
            body,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return cat


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Обновить категорию. Передавай только изменяемые поля."""
    actor_id, actor_role = _actor(current_user)
    try:
        cat = service.update_category(
            category_id, body,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Soft delete: устанавливает is_active=False.
    Категория скрывается из форм добавления материалов,
    но существующие привязки article_categories не трогаются.
    """
    actor_id, actor_role = _actor(current_user)
    try:
        service.delete_category(
            category_id,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
