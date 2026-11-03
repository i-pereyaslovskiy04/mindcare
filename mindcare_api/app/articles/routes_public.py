from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional
from uuid import UUID

from app.articles import service
from app.articles.schemas import (
    ArticleRead, ArticleTagOption, CategoryRead, PaginatedArticlesResponse,
)

router = APIRouter(prefix="/articles", tags=["articles"])


@router.get("/categories", response_model=list[CategoryRead])
def list_categories_public():
    return service.get_categories()


# Статический маршрут — ДО /{uuid}.
@router.get("/tags", response_model=list[ArticleTagOption])
def list_article_tags_public():
    """Темы опубликованных статей — варианты фильтра «Тема» библиотеки."""
    return service.get_public_article_tags()


@router.get("", response_model=PaginatedArticlesResponse)
def list_articles_public(
    page:        int            = Query(default=1, ge=1),
    size:        int            = Query(default=10, ge=1, le=100),
    search:      Optional[str]  = Query(default=None),
    category_id: Optional[int]  = Query(default=None),
    tag_uuid:    Optional[UUID] = Query(default=None),
):
    items, total = service.list_articles_public(
        page=page, size=size, search=search, category_id=category_id, tag_uuid=tag_uuid,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{uuid}", response_model=ArticleRead)
def get_article_public(uuid: str):
    article = service.get_article_public(uuid)
    if not article:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Материал не найден")
    return article
