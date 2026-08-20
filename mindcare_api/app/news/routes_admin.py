from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from typing import Optional

from app.auth.deps import require_role, resolve_role_or_403
from app.news import service
from app.news.schemas import (
    NewsCreate,
    NewsRead,
    NewsUpdate,
    PaginatedNewsResponse,
)

router = APIRouter(
    prefix="/admin/news",
    tags=["admin-news"],
    dependencies=[Depends(require_role("admin"))],
)


def _acting_role(current_user: dict) -> str:
    return resolve_role_or_403(current_user, allowed={"admin"}, preferred="admin")


@router.get("", response_model=PaginatedNewsResponse)
def list_news(
    page:         int            = Query(default=1, ge=1),
    size:         int            = Query(default=20, ge=1, le=100),
    search:       Optional[str]  = Query(default=None),
    is_published: Optional[bool] = Query(default=None),
    current_user: dict = Depends(require_role("admin")),
):
    items, total = service.list_news(
        page=page, size=size, search=search, is_published=is_published,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{uuid}", response_model=NewsRead)
def get_news(
    uuid: str,
    current_user: dict = Depends(require_role("admin")),
):
    news = service.get_news(uuid)
    if not news:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Новость не найдена")
    return news


@router.post("", response_model=NewsRead, status_code=status.HTTP_201_CREATED)
def create_news(
    body: NewsCreate,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    news = service.create_news(
        body.model_dump(),
        created_by=int(current_user["id"]),
        actor_role=_acting_role(current_user),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return news


@router.patch("/{uuid}", response_model=NewsRead)
def update_news(
    uuid: str,
    body: NewsUpdate,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    try:
        news = service.update_news(
            uuid, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return news


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_news(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("admin")),
):
    try:
        service.delete_news(
            uuid,
            actor_id=int(current_user["id"]),
            actor_role=_acting_role(current_user),
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
