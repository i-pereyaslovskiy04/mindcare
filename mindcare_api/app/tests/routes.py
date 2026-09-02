from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.auth.deps import require_role, resolve_role_or_403
from app.tests import service
from app.tests.service import ConsentRequired, ConfigError
from app.tests.schemas import (
    PaginatedPublicTestsResponse,
    TestTakeRead,
    SubmitIn,
    ResultRead,
    PaginatedResultsResponse,
    ConsentStatusRead,
)

router = APIRouter(
    prefix="/tests",
    tags=["tests"],
    dependencies=[Depends(require_role("student"))],
)


def _client(request: Request):
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def _acting_role(current_user: dict) -> str:
    return resolve_role_or_403(
        current_user, allowed={"student"}, preferred="student",
    )


# ── список активных тестов ────────────────────────────────────────────────────

@router.get("", response_model=PaginatedPublicTestsResponse)
def list_tests(
    page:   int           = Query(default=1, ge=1),
    size:   int           = Query(default=20, ge=1, le=100),
    search: Optional[str] = Query(default=None),
    current_user: dict = Depends(require_role("student")),
):
    items, total = service.list_active_tests(page=page, size=size, search=search)
    return {"items": items, "total": total, "page": page, "size": size}


# ── consent (ФЗ-152) ──────────────────────────────────────────────────────────

@router.get("/consent", response_model=ConsentStatusRead)
def get_consent(current_user: dict = Depends(require_role("student"))):
    try:
        return service.get_test_consent_status(current_user["id"])
    except ConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))


@router.post("/consent/accept", response_model=ConsentStatusRead)
def accept_consent(
    request: Request,
    current_user: dict = Depends(require_role("student")),
):
    ip, ua = _client(request)
    try:
        result = service.accept_test_consent(
            int(current_user["id"]), ip, ua,
            actor_role=_acting_role(current_user),
        )
    except ConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return result


# ── свои результаты ───────────────────────────────────────────────────────────

@router.get("/results", response_model=PaginatedResultsResponse)
def list_results(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_role("student")),
):
    items, total = service.list_results(current_user["id"], page=page, size=size)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/results/{result_uuid}", response_model=ResultRead)
def get_result(
    result_uuid: str,
    current_user: dict = Depends(require_role("student")),
):
    result = service.get_result(current_user["id"], result_uuid)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Результат не найден")
    return result


# ── прохождение ───────────────────────────────────────────────────────────────

@router.get("/{uuid}", response_model=TestTakeRead)
def get_test(
    uuid: str,
    current_user: dict = Depends(require_role("student")),
):
    test = service.get_test_for_take(uuid)
    if not test:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Тест не найден")
    return test


@router.post("/{uuid}/submit", response_model=ResultRead, status_code=status.HTTP_201_CREATED)
def submit_test(
    uuid: str,
    body: SubmitIn,
    request: Request,
    current_user: dict = Depends(require_role("student")),
):
    ip, ua = _client(request)
    try:
        result = service.submit_test(
            uuid, int(current_user["id"]),
            [a.model_dump() for a in body.answers],
            ip=ip, user_agent=ua,
            actor_role=_acting_role(current_user),
            timed_out=body.timed_out,
        )
    except ConsentRequired as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except ConfigError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        msg = str(exc)
        code = (
            status.HTTP_404_NOT_FOUND if "не найден" in msg
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=msg)
    return result