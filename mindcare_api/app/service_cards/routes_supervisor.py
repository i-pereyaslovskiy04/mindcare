"""
Эндпоинты управления карточками услуг страницы /services.
Доступ: admin и supervisor (ADR-015: /api/supervisor/*, не /api/admin/*).
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.service_cards import service
from app.service_cards.schemas import (
    ServiceCardCreate,
    ServiceCardRead,
    ServiceCardUpdate,
)

router = APIRouter(
    prefix="/supervisor/service-cards",
    tags=["supervisor: service-cards"],
    dependencies=[Depends(require_role("admin", "supervisor"))],
)


def _sup_role(current_user: dict) -> str:
    return resolve_role_or_403(
        current_user, allowed={"admin", "supervisor"}, preferred="supervisor",
    )


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("", response_model=list[ServiceCardRead])
def list_service_cards(include_inactive: bool = Query(default=False)):
    return service.list_service_cards(include_inactive=include_inactive)


@router.post("", response_model=ServiceCardRead, status_code=201)
def create_service_card(
    body: ServiceCardCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = _sup_role(current_user)
    return service.create_service_card(
        body.model_dump(),
        actor_id=int(current_user["id"]), actor_role=role,
        ip=_ip(request), user_agent=request.headers.get("user-agent"),
    )


@router.patch("/{card_id}", response_model=ServiceCardRead)
def update_service_card(
    card_id: int,
    body: ServiceCardUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = _sup_role(current_user)
    try:
        return service.update_service_card(
            card_id, body.model_dump(exclude_unset=True),
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.ServiceCardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service_card(
    card_id: int,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    role = _sup_role(current_user)
    try:
        service.delete_service_card(
            card_id,
            actor_id=int(current_user["id"]), actor_role=role,
            ip=_ip(request), user_agent=request.headers.get("user-agent"),
        )
    except service.ServiceCardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
