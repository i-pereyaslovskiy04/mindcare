"""
Подтверждение студента ДонГУ — self-service и каталог факультетов (ADR-029).

  catalog_router — GET /api/student-verification/faculties: любой
                   аутентифицированный пользователь (наличие student не нужно),
                   без аудита (справочник).
  router         — GET/POST /api/student-verification/me: только чистый student
                   (активные роли ровно {student}) вне impersonation.

Отказы — {"detail", "code"} со стабильным code. Failure-аудит подачи
(student_verification_submit_failed) пишется ПОСЛЕ отката бизнес-транзакции;
при impersonation actor — администратор-инициатор (не пользователь-цель).
Чтение собственного статуса событий не пишет (в т.ч. отказы чтения).
"""
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.audit import Actor
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, require_role, resolve_role_or_403
from app.student_verification import errors, service
from app.student_verification.schemas import (
    FacultiesOut, MyVerificationOut, SubmitIn,
)

_NO_STORE = "no-store, private"

catalog_router = APIRouter(
    prefix="/student-verification",
    tags=["student-verification"],
    dependencies=[Depends(get_current_user)],
)

router = APIRouter(
    prefix="/student-verification",
    tags=["student-verification"],
    dependencies=[Depends(require_role("student"))],
)


def _client(request: Request) -> tuple:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def error_response(exc: errors.VerificationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
        headers={"Cache-Control": _NO_STORE},
    )


@catalog_router.get("/faculties", response_model=FacultiesOut)
def list_faculties():
    return {"items": service.faculties()}


@router.get("/me", response_model=MyVerificationOut)
def get_my_verification(
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    response.headers["Cache-Control"] = _NO_STORE
    try:
        return service.get_my_status(current_user)
    except errors.VerificationError as exc:
        return error_response(exc)


@router.post("/me", response_model=MyVerificationOut, status_code=201)
def submit_my_verification(
    body: SubmitIn,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    ip, ua = _client(request)
    context = build_request_context(ip=ip, user_agent=ua)

    impersonator_id = current_user.get("impersonator_user_id")
    if impersonator_id is not None:
        # Действие инициировал администратор «под именем»: отказ пишется от
        # НЕГО (membership admin подтверждена get_current_user в этом запросе).
        record_secondary_failure(
            event="student_verification_submit_failed",
            actor=Actor.user(int(impersonator_id), current_user["impersonator_role"]),
            failure_reason_code=errors.ImpersonationForbidden.code,
            context=context,
        )
        return error_response(errors.ImpersonationForbidden())

    # Acting-роль — primary по membership: отказ staff+student виден как отказ
    # staff, а не неявной роли student.
    actor = Actor.user(int(current_user["id"]), resolve_role_or_403(current_user))
    try:
        result = service.submit_my(
            current_user,
            faculty_code=body.faculty_code,
            ticket_number=body.ticket_number,
            ip=ip,
            user_agent=ua,
        )
    except errors.VerificationError as exc:
        record_secondary_failure(
            event="student_verification_submit_failed",
            actor=actor,
            failure_reason_code=exc.code,
            context=context,
        )
        return error_response(exc)
    response.headers["Cache-Control"] = _NO_STORE
    return result
