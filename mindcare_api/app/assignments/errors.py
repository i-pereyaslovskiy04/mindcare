"""
Доменные ошибки заданий (ADR-033). Без текста заданий и без текста исключений:
наружу уходят только стабильные коды из закрытых множеств.
"""
from dataclasses import dataclass
from typing import Optional

# Закрытые allowlist'ы того, что вообще может попасть в тело 422.
FIELD_NAMES = frozenset({
    "text", "due_date", "article_uuid", "view", "before", "size",
    "student_uuid", "assignment_uuid",
})
ERROR_CODES = frozenset({
    # семантика (validators)
    "required", "too_long", "invalid_characters", "invalid_cursor",
    # форма запроса (sanitized_route)
    "unknown_field", "invalid_json", "invalid_type", "invalid_uuid",
    "invalid_date", "out_of_range", "invalid_value",
})


@dataclass(frozen=True)
class FieldError:
    field: Optional[str]   # ∈ FIELD_NAMES или None
    code: str              # ∈ ERROR_CODES

    def __post_init__(self):
        assert self.field is None or self.field in FIELD_NAMES
        assert self.code in ERROR_CODES

    def as_dict(self) -> dict:
        return {"field": self.field, "code": self.code}


class AssignmentError(Exception):
    code: str = "assignment_error"
    status_code: int = 500
    message: str = "Не удалось выполнить операцию"
    failure_reason: str = "internal_error"   # код *_failed-события

    def __init__(self):
        super().__init__(self.code)


class AssignmentValidationError(AssignmentError):
    code = "assignment_invalid"
    status_code = 422
    message = "Проверьте поля задания"
    failure_reason = "invalid_request"

    def __init__(self, errors: list):
        self.errors = list(errors)
        super().__init__()


class AssignmentNotAvailable(AssignmentError):
    """Нет задания / клиента / права — один и тот же ответ (существование не раскрываем)."""
    code = "assignment_not_available"
    status_code = 404
    message = "Задание недоступно"
    failure_reason = "access_denied"


class AssignmentEngagementInactive(AssignmentError):
    """Своё задание, но сопровождение завершено или передано — только история."""
    code = "assignment_engagement_inactive"
    status_code = 409
    message = (
        "Сопровождение завершено: задание доступно только для просмотра."
    )
    failure_reason = "engagement_inactive"


class AssignmentFinalized(AssignmentError):
    """Задание уже в другом конечном статусе (completed ↔ cancelled не перезаписываются)."""
    code = "assignment_finalized"
    status_code = 409
    message = "Задание уже завершено и не может быть изменено."
    failure_reason = "assignment_finalized"

    def __init__(self, current_status: str):
        self.current_status = current_status
        super().__init__()


class MaterialUnavailable(AssignmentError):
    """Материал не опубликован, удалён или не существует (не различаем)."""
    code = "assignment_material_unavailable"
    status_code = 422
    message = "Материал недоступен: выберите опубликованный материал."
    failure_reason = "material_unavailable"


class AssignmentsStorageError(RuntimeError):
    """
    Технический сбой хранилища (чтение/запись/шифрование). Создаётся ВНЕ блока
    except и поднимается `from None`: SQL, параметры и шифртекст не попадают ни в
    __cause__, ни в __context__. Не AssignmentError → route не ловит → 500.
    """

    def __init__(self):
        super().__init__("assignments storage failure")
