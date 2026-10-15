"""
Доменные ошибки контактов (ADR-031). Без значений контактов и без текста
исключений: наружу уходят только стабильные коды из закрытых множеств.
"""
from dataclasses import dataclass
from typing import Optional

# Закрытые allowlist'ы того, что вообще может попасть в тело 422.
FIELD_NAMES = frozenset({
    "version", "items", "id", "type", "service", "value", "label", "user_uuid",
})
ERROR_CODES = frozenset({
    # семантика (validators)
    "required", "too_long", "too_many", "invalid_id", "duplicate_id",
    "invalid_type", "invalid_service", "service_required", "service_not_allowed",
    "label_required", "invalid_phone", "invalid_email", "invalid_url",
    "unsafe_url", "invalid_value", "invalid_characters", "duplicate",
    # форма тела (sanitized_route)
    "unknown_field", "invalid_json", "invalid_uuid", "out_of_range",
})


@dataclass(frozen=True)
class FieldError:
    index: Optional[int]   # номер элемента в отправленном списке
    field: Optional[str]   # ∈ FIELD_NAMES или None
    code: str              # ∈ ERROR_CODES

    def __post_init__(self):
        assert self.field is None or self.field in FIELD_NAMES
        assert self.code in ERROR_CODES

    def as_dict(self) -> dict:
        return {"index": self.index, "field": self.field, "code": self.code}


class ContactsError(Exception):
    code: str = "contacts_error"
    status_code: int = 500
    message: str = "Не удалось выполнить операцию"

    def __init__(self):
        super().__init__(self.code)


class ContactsValidationError(ContactsError):
    code = "contacts_invalid"
    status_code = 422
    message = "Проверьте поля контактов"

    def __init__(self, errors: list):
        self.errors = list(errors)
        super().__init__()


class ContactsVersionConflict(ContactsError):
    code = "contacts_version_conflict"
    status_code = 409
    message = (
        "Контакты были изменены в другом окне или на другом устройстве. "
        "Ваши правки не потеряны."
    )

    def __init__(self, current_version: int):
        self.current_version = int(current_version)
        super().__init__()


class ContactsNotAvailable(ContactsError):
    """Нет доступа / цель не найдена — один и тот же ответ (не раскрываем существование)."""
    code = "contacts_not_available"
    status_code = 404
    message = "Контакты недоступны"


class ContactsStorageError(RuntimeError):
    """
    Технический сбой хранилища (чтение/запись/шифрование). Создаётся ВНЕ блока
    except и поднимается `from None`: SQL, параметры и шифртекст не попадают ни в
    __cause__, ни в __context__. Не ContactsError → route не ловит → 500.
    """

    def __init__(self):
        super().__init__("user contacts storage failure")
