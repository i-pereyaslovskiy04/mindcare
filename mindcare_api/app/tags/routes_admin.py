from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Optional

from app.auth.deps import require_role, get_current_user, resolve_role_or_403
from app.tags import service
from app.tags.schemas import (
    AdminTagListQuery,
    PaginatedTagsResponse,
    TagCreate,
    TagUpdate,
    TagRead,
)

router = APIRouter(
    prefix="/admin/tags",
    tags=["admin: tags"],
    dependencies=[Depends(require_role("admin"))],
)


def _actor(current_user: dict) -> tuple[int, str]:
    return (
        int(current_user["id"]),
        resolve_role_or_403(current_user, allowed={"admin"}, preferred="admin"),
    )


@router.get("/", response_model=PaginatedTagsResponse)
def list_tags(
    page:   int = Query(default=1, ge=1),
    size:   int = Query(default=50, ge=1, le=100),
    search: Optional[str] = Query(default=None, max_length=200),
):
    """Список всех тегов с количеством использований."""
    query = AdminTagListQuery(page=page, size=size, search=search)
    return service.get_tags_list(query)


@router.post("/", response_model=TagRead, status_code=201)
def create_tag(
    request: Request,
    body: TagCreate,
    current_user: dict = Depends(get_current_user),
):
    """Создать новый тег. Имя нормализуется: первая буква заглавная."""
    actor_id, actor_role = _actor(current_user)
    try:
        tag = service.create_tag(
            body,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return tag


@router.patch("/{uuid}", response_model=TagRead)
def update_tag(
    request: Request,
    uuid: str,
    body: TagUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Переименовать тег."""
    actor_id, actor_role = _actor(current_user)
    try:
        tag = service.update_tag(
            uuid, body,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return tag


@router.delete("/{uuid}", status_code=204)
def delete_tag(
    request: Request,
    uuid: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Удалить тег. Все связи с материалами удаляются каскадно.
    Возвращает 204 No Content при успехе.
    """
    actor_id, actor_role = _actor(current_user)
    try:
        service.delete_tag(
            uuid,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except service.AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
