from fastapi import APIRouter, HTTPException, Query, status
from typing import Optional

from app.news import service
from app.news.schemas import NewsRead, NewsListItem, PaginatedNewsResponse

router = APIRouter(prefix="/news", tags=["news"])


@router.get("", response_model=PaginatedNewsResponse)
def list_news_public(
    page:   int           = Query(default=1, ge=1),
    size:   int           = Query(default=10, ge=1, le=100),
    search: Optional[str] = Query(default=None),
):
    items, total = service.list_news_public(page=page, size=size, search=search)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{uuid}", response_model=NewsRead)
def get_news_public(uuid: str):
    news = service.get_news_public(uuid)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Новость не найдена")
    return news
