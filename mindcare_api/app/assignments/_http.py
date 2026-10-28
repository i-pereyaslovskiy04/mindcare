"""Общие HTTP-помощники роутеров заданий (service их не импортирует)."""
from fastapi import Request
from fastapi.responses import JSONResponse

from app.assignments.errors import AssignmentError, AssignmentFinalized
from app.assignments.sanitized_route import NO_STORE


def client_meta(request: Request) -> tuple:
    ip = request.client.host if request.client else None
    return ip, request.headers.get("user-agent")


def domain_response(exc: AssignmentError) -> JSONResponse:
    """Доменный отказ: стабильный код и фиксированный текст, без значений."""
    content = {"detail": exc.message, "code": exc.code}
    if isinstance(exc, AssignmentFinalized):
        content["current_status"] = exc.current_status
    return JSONResponse(
        status_code=exc.status_code, content=content,
        headers={"Cache-Control": NO_STORE},
    )
