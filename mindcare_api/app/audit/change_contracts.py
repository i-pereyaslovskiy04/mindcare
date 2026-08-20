"""
Stage 6-0 — типы контракта минимизированного data_change_log.

Строка `data_change_log` — НЕ событие: у неё нет имени события, outcome,
metadata, description и user_email. Поэтому она не проходит через
`record_event`/`EventSpec`, а имеет собственный набор типов; общие примитивы
(`Actor`, `RequestContext`, `ActorPolicy`, `WriteState`, `AuditError`) при этом
переиспользуются из `app.audit.contracts` без дублирования.

Терминология:
  - actor  — действующее лицо (data_change_log.actor_id / actor_role).
  - table / record_id — физическая таблица и INTEGER identity изменённой строки.
  - paired_event — событие `audit_log`, которое несёт СЕМАНТИКУ действия; DCL
    несёт только перечень изменённых безопасных полей (см. change_registry).

Минимизация:
  - по умолчанию журналируются ТОЛЬКО имена полей (`ValuePolicy.NAME_ONLY`);
  - значения допускаются лишь для явно размеченных нечувствительных
    enum/bool/int полей и валидируются одной и той же ChangeFieldSpec;
  - `ChangeFieldSpec.justification` обязателен — каждое исключение обосновано.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Mapping, Optional, Union

from app.audit.contracts import ActorPolicy, AuditError, WriteState

# Диапазон физического типа колонок PostgreSQL INTEGER. Используется для полей,
# у которых НЕТ прикладного инварианта (ни в Pydantic, ни в ORM, ни в CHECK):
# journal-контракт не имеет права вводить новый бизнес-лимит, потому что
# ChangeValue.old читается ИЗ БД, а не из запроса.
PG_INT32_MIN: int = -2_147_483_648
PG_INT32_MAX: int = 2_147_483_647


class Operation(enum.Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class ValuePolicy(enum.Enum):
    NAME_ONLY = "name_only"   # в журнал попадает только ИМЯ поля
    ENUM = "enum"             # стабильный строковый enum
    BOOL = "bool"             # boolean-переход
    INT = "int"               # неперсональное целое


# ── Ошибки ────────────────────────────────────────────────────────────────────

class DataChangeError(AuditError):
    """Нарушение контракта/валидации data-change writer'а (подтип AuditError)."""


class DataChangeStorageError(DataChangeError):
    """Санитизированный сбой записи строки data_change_log."""


# ── Значение изменённого поля ─────────────────────────────────────────────────

_ScalarValue = Union[str, int, bool, None]


@dataclass(frozen=True)
class ChangeValue:
    """Пара before/after для ОДНОГО поля.

    Оба значения валидируются одной и той же ChangeFieldSpec — отдельных
    спецификаций для old и new не существует. `old` обязан быть снят ДО мутации
    ORM: снятый после мутации snapshot даёт old == new и отвергается writer'ом.
    """
    old: _ScalarValue
    new: _ScalarValue


# ── Спецификация поля / таблицы ───────────────────────────────────────────────

@dataclass(frozen=True)
class ChangeFieldSpec:
    """Политика журналирования одного поля.

    `justification` обязателен и непуст: любое отступление от name-only должно
    быть обосновано в коде, а не в комментарии ревью.
    """
    policy: ValuePolicy
    justification: str
    allowed: Optional[frozenset] = None   # обязателен при ENUM
    min_value: Optional[int] = None       # обязателен при INT
    max_value: Optional[int] = None       # обязателен при INT
    nullable: bool = False


@dataclass(frozen=True)
class TableSpec:
    """Закрытая спецификация одной журналируемой таблицы.

    `fields` — публичная проекция журнала: только эти имена могут попасть в
    changed_fields. `derived_fields` — служебные/производные колонки, которые
    caller может передать в диффе, но которые ЯВНО отбрасываются и никогда не
    журналируются (например normalized_email). Всё, что не входит ни туда, ни
    туда, — ошибка, а не тихий drop.
    """
    table: str
    entity_type: str
    paired_event: str
    allowed_operations: frozenset
    actor_policy: ActorPolicy
    allowed_actor_roles: frozenset
    fields: Mapping[str, ChangeFieldSpec]
    derived_fields: frozenset = field(default_factory=frozenset)


# ── Результат записи ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class DataChangeResult:
    """Итог записи. Режим всегда ATOMIC, поэтому state всегда WriteState.STAGED:
    строка добавлена в caller-сессию, commit — за владельцем транзакции."""
    state: WriteState
    table: str
