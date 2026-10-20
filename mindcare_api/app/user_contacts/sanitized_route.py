"""
Route-класс контактов: ошибки валидации без значений (ADR-032).

В приложении нет кастомного обработчика RequestValidationError, а стандартный
422 FastAPI возвращает `input` — введённые значения (и имена лишних полей,
которыми может оказаться чьё-то значение). Для маршрутов контактов тело 422
строится ЗАНОВО из закрытых allowlist'ов:

  * field — только из FIELD_NAMES; любое другое имя из `loc` (лишнее поле
    верхнего уровня или внутри элемента) НЕ копируется → field=null;
  * code  — только из ERROR_CODES, по фиксированной таблице типов pydantic
    (по умолчанию invalid_value);
  * index — целое в разумных пределах;
  * msg / input / ctx / url / body не используются; ничего не логируется.

Порядок FastAPI: разбор JSON → зависимости (guards: 403 побеждает ошибки полей)
→ ошибки полей. Битый JSON даёт тот же санитизированный 422.
"""
import sys
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.user_contacts.catalog import HARD_ITEMS_CAP
from app.user_contacts.errors import (
    ERROR_CODES, FIELD_NAMES, FieldError,
)

NO_STORE = "no-store, private"
_ITEM_FIELDS = frozenset({"id", "type", "service", "value", "label"})
_MAX_ERRORS = 50
_MAX_INDEX = HARD_ITEMS_CAP * 2

_TYPE_TO_CODE = {
    "missing": "required",
    "string_too_long": "too_long",
    "too_long": "too_many",
    "extra_forbidden": "unknown_field",
    "string_type": "invalid_type",
    "int_type": "invalid_type",
    "int_parsing": "invalid_type",
    "int_from_float": "invalid_type",
    "list_type": "invalid_type",
    "dict_type": "invalid_type",
    "model_type": "invalid_type",
    "model_attributes_type": "invalid_type",
    "greater_than_equal": "out_of_range",
    "less_than_equal": "out_of_range",
    "uuid_parsing": "invalid_uuid",
    "uuid_type": "invalid_uuid",
    "json_invalid": "invalid_json",
}


def _field_error(item: dict) -> FieldError:
    code = _TYPE_TO_CODE.get(item.get("type"), "invalid_value")
    loc = tuple(item.get("loc") or ())
    index: Optional[int] = None
    field: Optional[str] = None
    if loc and loc[0] == "path":
        candidate = loc[1] if len(loc) > 1 else None
        field = candidate if isinstance(candidate, str) and candidate in FIELD_NAMES else None
    elif loc and loc[0] == "body":
        elems = loc[1:]
        if elems and elems[0] == "items":
            field = "items"
            if len(elems) > 1 and isinstance(elems[1], int) and 0 <= elems[1] < _MAX_INDEX:
                index = elems[1]
                # Имя поля элемента копируем ТОЛЬКО если оно из allowlist.
                name = elems[2] if len(elems) > 2 else None
                field = name if isinstance(name, str) and name in _ITEM_FIELDS else None
        elif elems and elems[0] == "version":
            field = "version"
    assert code in ERROR_CODES and (field is None or field in FIELD_NAMES)
    return FieldError(index, field, code)


def invalid_response(errors: list) -> JSONResponse:
    """422 {detail, code, errors:[{index, field, code}]} — только allowlist'ы."""
    safe = [e.as_dict() for e in errors[:_MAX_ERRORS]]
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Проверьте поля контактов",
            "code": "contacts_invalid",
            "errors": safe,
        },
        headers={"Cache-Control": NO_STORE},
    )


class ContactsRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                return invalid_response([_field_error(e) for e in exc.errors()])
            except ResponseValidationError:
                # Сообщение pydantic содержит значения ответа — наружу и в лог не идёт.
                print("[USER_CONTACTS] phase=response error=ResponseValidationError",
                      file=sys.stderr)
                return JSONResponse(
                    status_code=500,
                    content={"detail": "Внутренняя ошибка"},
                    headers={"Cache-Control": NO_STORE},
                )

        return handler
