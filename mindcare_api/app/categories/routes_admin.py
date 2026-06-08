from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import Optional

from app.auth.audit import log_auth_event
from app.auth.deps import require_role, get_current_user
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
    try:
        cat = service.create_category(body)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    log_auth_event(
        event=f"admin_create_category:{cat['id']}",
        success=True,
        user_id=current_user["id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return cat


@router.patch("/{category_id}", response_model=CategoryRead)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Обновить категорию. Передавай только изменяемые поля."""
    try:
        cat = service.update_category(category_id, body)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    log_auth_event(
        event=f"admin_update_category:{category_id}",
        success=True,
        user_id=current_user["id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
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
    try:
        service.delete_category(category_id)
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    log_auth_event(
        event=f"admin_delete_category:{category_id}",
        success=True,
        user_id=current_user["id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
