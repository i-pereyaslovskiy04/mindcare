from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

from app.articles import service
from app.articles.schemas import ArticleRead, CategoryRead, PaginatedArticlesResponse

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/categories", response_model=list[CategoryRead])
def list_categories_public():
    return service.get_categories()


@router.get("", response_model=PaginatedArticlesResponse)
def list_articles_public(
    page:        int           = Query(default=1, ge=1),
    size:        int           = Query(default=10, ge=1, le=100),
    search:      Optional[str] = Query(default=None),
    category_id: Optional[int] = Query(default=None),
):
    items, total = service.list_articles_public(
        page=page, size=size, search=search, category_id=category_id,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{uuid}", response_model=ArticleRead)
def get_article_public(uuid: str):
    article = service.get_article_public(uuid)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Материал не найден")
    return article
