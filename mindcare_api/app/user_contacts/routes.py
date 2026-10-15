"""
Контакты владельца (ADR-031): GET/PUT /api/auth/profile/contacts.

Только владелец аккаунта (PUT адресуется текущему пользователю), вне
impersonation (router-level guard → 403 до разбора полей). Ответы — без кеша.
Отказы PUT: 422 (валидация, тело без значений) и 409 (конфликт версии) пишут
profile_update_failed ПОСЛЕ отката (invalid_request / contacts_version_conflict);
сбой обязательного аудита до commit → 503 без failure-события; технический или
неоднозначный сбой commit → 500 без failure-события.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.audit import Actor, AuditError
from app.audit.failsafe import record_secondary_failure
from app.audit.request_context import build_request_context
from app.auth.deps import get_current_user, resolve_role_or_403
from app.user_contacts import service
from app.user_contacts.context import OwnerContext
from app.user_contacts.errors import ContactsValidationError, ContactsVersionConflict
from app.user_contacts.guards import forbid_impersonation
from app.user_contacts.sanitized_route import NO_STORE, ContactsRoute, invalid_response
from app.user_contacts.schemas import ContactsOwnerOut, ContactsSaveIn, ContactsSaveOut

_SAVE_UNAVAILABLE = "Не удалось сохранить контакты. Повторите попытку."

router = APIRouter(
    prefix="/auth/profile/contacts",
    tags=["profile-contacts"],
    route_class=ContactsRoute,
    dependencies=[Depends(forbid_impersonation)],
)


def _client(request: Request) -> tuple:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


@router.get("", response_model=ContactsOwnerOut)
def get_my_contacts(
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    response.headers["Cache-Control"] = NO_STORE
    return service.get_my_contacts(int(current_user["id"]))


@router.put("", response_model=ContactsSaveOut)
def save_my_contacts(
    body: ContactsSaveIn,
    request: Request,
    response: Response,
    current_user: dict = Depends(get_current_user),
):
    role = resolve_role_or_403(current_user)           # по membership, не legacy role
    ctx = OwnerContext(user_id=int(current_user["id"]), role=role)
    ip, ua = _client(request)

    def record_failure(code: str) -> None:
        record_secondary_failure(
            event="profile_update_failed",
            actor=Actor.user(ctx.user_id, ctx.role),
            failure_reason_code=code,
            context=build_request_context(ip=ip, user_agent=ua),
        )

    try:
        result = service.save_my_contacts(
            ctx, body.version, [item.model_dump() for item in body.items],
            ip=ip, user_agent=ua,
        )
    except ContactsValidationError as exc:
        record_failure("invalid_request")
        return invalid_response(exc.errors)
    except ContactsVersionConflict as exc:
        record_failure("contacts_version_conflict")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.message,
                "code": exc.code,
                "current_version": exc.current_version,
            },
            headers={"Cache-Control": NO_STORE},
        )
    except AuditError:
        # Обязательный аудит не записан → запись откатена; failure-события нет.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_SAVE_UNAVAILABLE,
        ) from None
    response.headers["Cache-Control"] = NO_STORE
    return result
