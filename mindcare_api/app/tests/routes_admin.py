from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.audit import log_auth_event
from app.auth.deps import require_role
from app.tests import service
from app.tests.schemas import (
    TestCreate,
    TestUpdate,
    TestRead,
    PaginatedTestsResponse,
)

router = APIRouter(
    prefix="/admin/tests",
    tags=["admin-tests"],
    dependencies=[Depends(require_role("admin", "supervisor"))],
)


def _client(request: Request) -> tuple[Optional[str], Optional[str]]:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


@router.get("", response_model=PaginatedTestsResponse)
def list_tests(
    page:      int            = Query(default=1, ge=1),
    size:      int            = Query(default=20, ge=1, le=100),
    search:    Optional[str]  = Query(default=None),
    is_active: Optional[bool] = Query(default=None),
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    items, total = service.list_tests(
        page=page, size=size, search=search, is_active=is_active,
    )
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/{uuid}", response_model=TestRead)
def get_test(
    uuid: str,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    test = service.get_test(uuid)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    return test


@router.post("", response_model=TestRead, status_code=status.HTTP_201_CREATED)
def create_test(
    body: TestCreate,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    try:
        test = service.create_test(body.model_dump(), created_by=current_user["id"])
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    ip, ua = _client(request)
    log_auth_event(
        event=f"admin_create_test:{test['uuid']}",
        success=True, user_id=current_user["id"], ip_address=ip, user_agent=ua,
    )
    return test


@router.patch("/{uuid}", response_model=TestRead)
def update_test(
    uuid: str,
    body: TestUpdate,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    try:
        test = service.update_test(uuid, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND
            if "не найден" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=msg)
    ip, ua = _client(request)
    log_auth_event(
        event=f"admin_update_test:{uuid}",
        success=True, user_id=current_user["id"], ip_address=ip, user_agent=ua,
    )
    return test


@router.delete("/{uuid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_test(
    uuid: str,
    request: Request,
    current_user: dict = Depends(require_role("admin", "supervisor")),
):
    try:
        service.delete_test(uuid)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    ip, ua = _client(request)
    log_auth_event(
        event=f"admin_delete_test:{uuid}",
        success=True, user_id=current_user["id"], ip_address=ip, user_agent=ua,
    )
