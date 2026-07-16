"""
Админские эндпоинты управления allowlist почтовых доменов.
Префикс: /api/admin/email-domains
Доступ: только 'admin' через Depends(require_role("admin")).
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.email_domains import service
from app.email_domains.errors import DomainError
from app.email_domains.schemas import (
    EmailDomainCreate,
    EmailDomainRead,
    EmailDomainUpdate,
)

router = APIRouter(
    prefix="/admin/email-domains",
    tags=["admin: email domains"],
    dependencies=[Depends(require_role("admin"))],
)


def _actor(current_user: dict) -> tuple[int, str]:
    return (
        int(current_user["id"]),
        resolve_role_or_403(current_user, allowed={"admin"}, preferred="admin"),
    )


@router.get("/", response_model=list[EmailDomainRead])
def list_email_domains():
    """Все домены allowlist (активные + отключённые)."""
    return service.list_domains()


@router.post("/", response_model=EmailDomainRead, status_code=201)
def create_email_domain(
    body: EmailDomainCreate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Добавить домен в allowlist (активным)."""
    actor_id, actor_role = _actor(current_user)
    try:
        return service.create_domain(
            raw_domain=body.domain,
            comment=body.comment,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except DomainError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.patch("/{domain_id}", response_model=EmailDomainRead)
def update_email_domain(
    domain_id: int,
    body: EmailDomainUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Отключить / повторно включить домен или изменить комментарий.
    Пустое тело (ни одного поля) → 422; отключение последнего активного → 409.
    """
    provided = body.model_fields_set
    if not (provided & {"is_active", "comment"}):
        raise HTTPException(
            status_code=422,
            detail="Укажите хотя бы одно поле: is_active и/или comment",
        )
    actor_id, actor_role = _actor(current_user)
    try:
        return service.update_domain(
            domain_id=domain_id,
            new_is_active=body.is_active,
            comment_provided="comment" in provided,
            new_comment=body.comment,
            actor_id=actor_id,
            actor_role=actor_role,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except DomainError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
