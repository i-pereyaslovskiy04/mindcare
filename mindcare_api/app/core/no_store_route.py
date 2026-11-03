"""
Route-класс для ответов с чувствительным содержимым: без кеша и без значений
в ошибках (обобщение AssignmentsRoute, ADR-033).

Cache-Control: no-store, private ставится на КАЖДЫЙ ответ роутера — успешный,
доменный отказ, 401/403 из зависимостей, 422, 503 и 500.

Порядок обработки исключений (второй рубеж после handler'а, который сам ловит
доменные ошибки и AuditError):
  1. RequestValidationError → 422 только с местом и типом ошибки (input/msg/ctx
     не копируются — тело запроса, например текст заметки, не эхоится);
  2. HTTPException (deps/route) → JSONResponse с прежними detail/headers;
  3. AuditError → 503 с безопасным текстом (сбой обязательного аудита никогда
     не превращается в 500 и не отдаёт содержимое);
  4. любое иное исключение → 500 без деталей (в stderr — только класс).
"""
import re
import sys
from typing import Callable

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.audit import AuditError

NO_STORE = "no-store, private"
AUDIT_UNAVAILABLE = "Не удалось зафиксировать доступ в журнале. Повторите попытку позже."
_MAX_ERRORS = 20
_FIELD_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def no_store_json(status_code: int, content: dict) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content=content, headers={"Cache-Control": NO_STORE},
    )


def audit_unavailable_response() -> JSONResponse:
    return no_store_json(503, {"detail": AUDIT_UNAVAILABLE})


def _safe_validation_errors(exc: RequestValidationError) -> list:
    """Место (body/query/path + имя поля вида snake_case) и тип ошибки; значения — никогда."""
    out = []
    for item in exc.errors()[:_MAX_ERRORS]:
        loc = tuple(item.get("loc") or ())
        kind = loc[0] if loc and loc[0] in ("body", "query", "path", "header") else None
        field = loc[1] if len(loc) > 1 and isinstance(loc[1], str) else None
        if field is not None and not _FIELD_RE.match(field):
            field = None
        out.append({"location": kind, "field": field,
                    "type": str(item.get("type") or "value_error")[:40]})
    return out


class NoStoreRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                response = await original(request)
            except RequestValidationError as exc:
                return no_store_json(422, {
                    "detail": "Проверьте параметры запроса",
                    "errors": _safe_validation_errors(exc),
                })
            except StarletteHTTPException as exc:
                headers = dict(exc.headers or {})
                headers["Cache-Control"] = NO_STORE
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail},
                    headers=headers,
                )
            except AuditError:
                print("[NO_STORE_ROUTE] phase=audit error=AuditError", file=sys.stderr)
                return audit_unavailable_response()
            except Exception as exc:   # noqa: BLE001 — 500 без деталей и значений
                print(
                    f"[NO_STORE_ROUTE] phase=unhandled error={type(exc).__name__}",
                    file=sys.stderr,
                )
                return no_store_json(500, {"detail": "Внутренняя ошибка"})
            response.headers["Cache-Control"] = NO_STORE
            return response

        return handler
