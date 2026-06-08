from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import Optional

from app.auth.audit import log_auth_event
from app.auth.deps import require_role
from app.articles import service
from app.articles.schemas import (
    ArticleCreate,
    ArticleRead,
    ArticleUpdate,
    CategoryRead,
    PaginatedArticlesResponse,
)

router = APIRouter(
    prefix="/admin/articles",
    tags=["admin-articles"],
    dependencies=[Depends(require_role("admin"))],
)


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    current_user: dict = Depends(require_role("admin")),
):
    return service.get_categories()


@router.get("", response_model=PaginatedArticlesResponse)
def list_articles(
    page:         int            = Query(default=1, ge=1),
    size:         int            = Query(default=20, ge=1, le=100),
    search:       Optional[str]  = Query(default=None),
    is_published: Optional[bool] = Query(default=None),
    category_id:  Optional[int]  = Query(default=None),
    current_user: dict = Depends(require_role("admin")),
):
    items, total = service.list_articles(
        page=page, size=size, search=search,
        is_published=is_published, category_id=category_id,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{uuid}", response_model=ArticleRead)
def get_article(
    uuid: str,
    current_user: dict = Depends(require_role("admin")),
):
    article = service.get_article(uuid)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Материал не найден")
    return article


@router.post("", response_model=ArticleRead, status_code=status.HTTP_201_CREATED)
def create_article(
    body: ArticleCreate,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    article = service.create_article(body.model_dump(), created_by=current_user["id"])
    log_auth_event(
        event=f"admin_create_article:{article['uuid']}",
        success=True,
        user_id=current_user["id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return article


@router.patch("/{uuid}", response_model=ArticleRead)
def update_article(
    uuid: str,
    body: ArticleUpdate,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    try:
        article = service.update_article(uuid, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    log_auth_event(
        event=f"admin_update_article:{uuid}",
        success=True,
        user_id=current_user["id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return article


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_article(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    try:
        service.delete_article(uuid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    log_auth_event(
        event=f"admin_delete_article:{uuid}",
        success=True,
        user_id=current_user["id"],
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
