"""
Эндпоинты управления слайдами баннера главной страницы.
Доступ: admin и supervisor (ADR-015: /api/supervisor/*, не /api/admin/*).
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.banner_slides import service
from app.banner_slides.schemas import (
    BannerSlideCreate,
    BannerSlideRead,
    BannerSlideUpdate,
)

router = APIRouter(
    prefix="/supervisor/banner-slides",
    tags=["supervisor: banner-slides"],
    dependencies=[Depends(require_role("admin", "supervisor"))],
)


def _sup_role(current_user: dict) -> str:
    return resolve_role_or_403(
        current_user, allowed={"admin", "supervisor"}, preferred="supervisor",
    )


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("", response_model=list[BannerSlideRead])
def list_banner_slides(
    include_inactive: bool = Query(default=False),
    placement: Optional[str] = Query(default=None),
):
    return service.list_banner_slides(
        include_inactive=include_inactive, placement=placement
    )


@router.post("", response_model=BannerSlideRead, status_code=201)
def create_banner_slide(
    body: BannerSlideCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = _sup_role(current_user)
    return service.create_banner_slide(
        body.model_dump(),
        actor_id=int(current_user["id"]), actor_role=role,
        ip=_ip(request), user_agent=request.headers.get("user-agent"),
    )


@router.patch("/{slide_id}", response_model=BannerSlideRead)
def update_banner_slide(
    slide_id: int,
    body: BannerSlideUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = _sup_role(current_user)
    try:
        return service.update_banner_slide(
            slide_id, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.BannerSlideError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/{slide_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_banner_slide(
    slide_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = _sup_role(current_user)
    try:
        service.delete_banner_slide(
            slide_id,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.BannerSlideError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
