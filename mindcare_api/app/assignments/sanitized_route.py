"""
Route-класс заданий (ADR-033): ответы без кеша и ошибки без значений.

Cache-Control: no-store, private ставится на КАЖДЫЙ ответ обоих роутеров
заданий — успешный, доменный отказ, 401/403 из зависимостей, 422, 503 и 500.

Порядок обработки исключений (второй рубеж после endpoint-handler'а, который
сам ловит доменные ошибки и AuditError):
  1. RequestValidationError → санитизированный 422 (поле и код только из
     allowlist'ов; input/msg/ctx не копируются — текст задания не эхоится);
  2. HTTPException (deps/route) → JSONResponse с прежними detail/headers;
  3. AuditError → 503 с безопасным текстом (страховка: сбой обязательного
     аудита никогда не превращается в 500 и не отдаёт содержимое);
  4. ResponseValidationError / AssignmentsStorageError / любое иное
     исключение → 500 без деталей (в stderr — только класс).
AuditError стоит раньше общего Exception.
"""
import sys
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.assignments.errors import ERROR_CODES, FIELD_NAMES, FieldError
from app.audit import AuditError

NO_STORE = "no-store, private"
AUDIT_UNAVAILABLE = "Не удалось зафиксировать операцию с заданием. Повторите попытку."
_MAX_ERRORS = 20

_TYPE_TO_CODE = {
    "missing": "required",
    "string_too_long": "too_long",
    "extra_forbidden": "unknown_field",
    "string_type": "invalid_type",
    "int_type": "invalid_type",
    "int_parsing": "invalid_type",
    "int_from_float": "invalid_type",
    "dict_type": "invalid_type",
    "model_type": "invalid_type",
    "model_attributes_type": "invalid_type",
    "greater_than_equal": "out_of_range",
    "less_than_equal": "out_of_range",
    "uuid_parsing": "invalid_uuid",
    "uuid_type": "invalid_uuid",
    "date_parsing": "invalid_date",
    "date_type": "invalid_date",
    "date_from_datetime_parsing": "invalid_date",
    "date_from_datetime_inexact": "invalid_date",
    "literal_error": "invalid_value",
    "json_invalid": "invalid_json",
}


def _field_error(item: dict) -> FieldError:
    code = _TYPE_TO_CODE.get(item.get("type"), "invalid_value")
    loc = tuple(item.get("loc") or ())
    field: Optional[str] = None
    if len(loc) > 1 and loc[0] in ("path", "query", "body"):
        candidate = loc[1]
        # Имя поля копируем ТОЛЬКО из allowlist (лишнее поле тела — field=null).
        if isinstance(candidate, str) and candidate in FIELD_NAMES and code != "unknown_field":
            field = candidate
    assert code in ERROR_CODES and (field is None or field in FIELD_NAMES)
    return FieldError(field, code)


def invalid_response(errors: list) -> JSONResponse:
    """422 {detail, code, errors:[{field, code}]} — только allowlist'ы."""
    safe = [e.as_dict() for e in errors[:_MAX_ERRORS]]
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Проверьте поля задания",
            "code": "assignment_invalid",
            "errors": safe,
        },
        headers={"Cache-Control": NO_STORE},
    )


def audit_unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": AUDIT_UNAVAILABLE},
        headers={"Cache-Control": NO_STORE},
    )


def _internal_error(phase: str) -> JSONResponse:
    print(f"[ASSIGNMENTS] phase={phase}", file=sys.stderr)
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка"},
        headers={"Cache-Control": NO_STORE},
    )


class AssignmentsRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except RequestValidationError as exc:
                return invalid_response([_field_error(e) for e in exc.errors()])
            except StarletteHTTPException as exc:
                headers = dict(exc.headers or {})
                headers["Cache-Control"] = NO_STORE
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=headers,
                )
            except AuditError:
                print("[ASSIGNMENTS] phase=audit error=AuditError", file=sys.stderr)
                return audit_unavailable_response()
            except Exception as exc:   # noqa: BLE001 — 500 без деталей и значений
                return _internal_error(f"unhandled error={type(exc).__name__}")
            response.headers["Cache-Control"] = NO_STORE
            return response

        return handler
