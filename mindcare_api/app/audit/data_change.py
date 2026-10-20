"""
Stage 6-0 — record_data_change: минимизированный field-level журнал изменений.

Контракт (полностью fail-closed, режим ТОЛЬКО ATOMIC):
  - строка стейджится в caller-сессию через db.add; commit/rollback/close — за
    владельцем бизнес-транзакции. Своя SessionLocal НЕ открывается, поэтому
    успешное изменение и его journal-запись физически неразделимы;
  - любое нарушение контракта → DataChangeError ДО db.add (частичной записи не
    бывает); сбой самого db.add → DataChangeStorageError;
  - диагностика содержит только имя таблицы, фазу и класс исключения — без
    str(exc), actor, record_id, значений полей, SQL и URL БД.

Минимизация ПДн:
  - changed_fields несёт ТОЛЬКО имена полей из закрытого allowlist таблицы;
  - old_values/new_values заполняются лишь для полей с value-политикой и всегда
    ОДНИМ И ТЕМ ЖЕ набором ключей (частичный old-only/new-only diff невозможен);
  - при отсутствии value-полей обе колонки пишутся как NULL, а не как {}.

data_change_log не имеет колонок user_agent/session_id/request_url/
request_method/outcome, поэтому из RequestContext берётся только ip_address —
остальной контекст живёт на парной строке audit_log.
"""
from __future__ import annotations

import sys
from collections.abc import Iterable as _IterableABC
from typing import Iterable, Mapping, Optional, Sequence

from sqlalchemy.orm import Session

from app.db.models import DataChangeLog

from app.audit.contracts import (
    SYSTEM_ROLE, USER_ROLES, Actor, ActorPolicy, AuditError, RequestContext,
    WriteState,
)
from app.audit.change_contracts import (
    ChangeFieldSpec, ChangeValue, DataChangeError, DataChangeResult,
    DataChangeStorageError, Operation, TableSpec, ValuePolicy,
)
from app.audit.change_registry import get_table_spec, is_value_allowed
from app.audit import validation

# Верхняя граница на размер одной journal-строки. changed_fields шире этого
# набора быть не может: ни одна таблица allowlist'а не имеет столько полей.
_MAX_CHANGED_FIELDS = 32
_ENUM_VALUE_MAX = 64


# ── Вспомогательное ───────────────────────────────────────────────────────────

def _is_int(v) -> bool:
    return type(v) is int   # bool исключён (type(True) is bool)


def _diag(table: str, phase: str, error_class: str) -> None:
    # Только имя таблицы, фаза и класс исключения — без actor/record_id/значений/
    # metadata/SQL/URL БД/raw exception text.
    print(f"[AUDIT] table={table} phase={phase} error={error_class}", file=sys.stderr)


# ── Проекция изменённых полей ─────────────────────────────────────────────────

def project_changed_fields(table: str, changed_keys: Iterable[str]) -> list[str]:
    """Сводит произвольный storage-дифф к публичной проекции журнала.

    Ключи из `fields`   → сохраняются;
    ключи из `derived_fields` → ОТБРАСЫВАЮТСЯ (производные дубликаты, например
                                normalized_email);
    любой прочий ключ   → DataChangeError (fail closed, не тихий drop).

    Возвращает отсортированный список (детерминизм строки журнала).
    """
    spec = get_table_spec(table)

    # str/bytes формально итерируемы посимвольно — принять их означало бы молча
    # превратить "email" в ['e','m','a','i','l'].
    if isinstance(changed_keys, (str, bytes, bytearray)):
        raise DataChangeError("changed_keys must be a collection of names, not a string")
    # Явная проверка типа ДО итерации: None/int/иное не-Iterable иначе даёт
    # необработанный TypeError ("... is not iterable"), а не DataChangeError.
    # Сама итерация (и любые исключения ИЗ пользовательского iterable) ниже —
    # не перехватываются, только вход type-checked заранее.
    if not isinstance(changed_keys, _IterableABC):
        raise DataChangeError("changed_keys must be an iterable of field names")

    kept: set = set()
    for key in changed_keys:
        if not isinstance(key, str):
            raise DataChangeError("changed field names must be strings")
        if key in spec.fields:
            kept.add(key)
        elif key in spec.derived_fields:
            continue    # производная колонка: не журналируется
        else:
            raise DataChangeError("unknown field for this table")
    return sorted(kept)


# ── Валидация входа ───────────────────────────────────────────────────────────

def _validate_operation(spec: TableSpec, operation) -> Operation:
    if not isinstance(operation, Operation):
        raise DataChangeError("operation must be an Operation member")
    if operation not in spec.allowed_operations:
        raise DataChangeError("operation is not permitted for this table")
    return operation


def _validate_record_id(record_id) -> int:
    if not _is_int(record_id) or record_id <= 0:
        raise DataChangeError("record_id must be a positive integer")
    return record_id


def _validate_actor(spec: TableSpec, actor) -> None:
    if not isinstance(actor, Actor):
        raise DataChangeError("actor must be an Actor instance")

    if spec.actor_policy is ActorPolicy.SYSTEM:
        if actor.kind != "system":
            raise DataChangeError("table requires the system actor")
        if actor.user_id is not None or actor.role is not None:
            raise DataChangeError("system actor must not carry user_id or role")
        return

    # USER_REQUIRED — единственная оставшаяся политика (registry её гарантирует).
    if actor.kind != "user":
        raise DataChangeError("table requires an authenticated user actor")
    if not _is_int(actor.user_id) or actor.user_id <= 0:
        raise DataChangeError("actor user_id must be a positive integer")
    # В отличие от AUTH_LOG, здесь роль ВСЕГДА записывается (actor_role), поэтому
    # исключения для аккаунта без активных ролей нет.
    #
    # isinstance(str) ПЕРВЫМ, до membership: list/dict/иной unhashable role
    # иначе роняет `in USER_ROLES` необработанным TypeError (unhashable type),
    # а не DataChangeError. После этой проверки role гарантированно str —
    # безопасно хешировать её в membership-проверках ниже.
    role = actor.role
    if not isinstance(role, str) or not role or role not in USER_ROLES:
        raise DataChangeError("actor role is not a valid user role")
    if role not in spec.allowed_actor_roles:
        raise DataChangeError("actor role is not permitted for this table")


def _validate_changed_fields(spec: TableSpec, changed_fields) -> list[str]:
    # Type-strict: строка — тоже Sequence[str], и молча развалилась бы на буквы.
    if isinstance(changed_fields, (str, bytes, bytearray)):
        raise DataChangeError("changed_fields must be a list or tuple, not a string")
    if not isinstance(changed_fields, (list, tuple)):
        raise DataChangeError("changed_fields must be a list or tuple")
    if not changed_fields:
        raise DataChangeError("changed_fields must not be empty")
    if len(changed_fields) > _MAX_CHANGED_FIELDS:
        raise DataChangeError("changed_fields is too long")

    seen: set = set()
    for name in changed_fields:
        if not isinstance(name, str):
            raise DataChangeError("changed field names must be strings")
        if name in seen:
            raise DataChangeError("changed_fields must not contain duplicates")
        seen.add(name)
        if name not in spec.fields:
            raise DataChangeError("unknown field for this table")
    return sorted(seen)


def _validate_scalar(fname: str, fs: ChangeFieldSpec, value):
    """Проверяет ОДНО значение (old или new) по общей для обоих спецификации."""
    if value is None:
        if fs.nullable:
            return None
        raise DataChangeError(f"value for {fname}: null not allowed")

    if fs.policy is ValuePolicy.BOOL:
        if type(value) is not bool:
            raise DataChangeError(f"value for {fname}: expected bool")
        return value

    if fs.policy is ValuePolicy.INT:
        if not _is_int(value):
            raise DataChangeError(f"value for {fname}: expected integer (bool rejected)")
        if fs.min_value is not None and value < fs.min_value:
            raise DataChangeError(f"value for {fname}: below min_value")
        if fs.max_value is not None and value > fs.max_value:
            raise DataChangeError(f"value for {fname}: above max_value")
        return value

    if fs.policy is ValuePolicy.ENUM:
        if not isinstance(value, str):
            raise DataChangeError(f"value for {fname}: expected string")
        if len(value) > _ENUM_VALUE_MAX:
            raise DataChangeError(f"value for {fname}: string too long")
        if fs.allowed is None or value not in fs.allowed:
            raise DataChangeError(f"value for {fname}: value not in allowed enum")
        return value

    # NAME_ONLY сюда не доходит — отсекается раньше в _validate_values.
    raise DataChangeError(f"value for {fname}: unsupported value policy")


def _validate_values(
    spec: TableSpec, changed: list[str], values,
) -> tuple[Optional[dict], Optional[dict]]:
    """Возвращает (old_values, new_values) с ОДИНАКОВЫМ набором ключей либо
    (None, None), если значения не передавались."""
    if values is None:
        return None, None
    if not isinstance(values, Mapping):
        raise DataChangeError("values must be a mapping")
    if not values:
        return None, None

    changed_set = set(changed)
    old_map: dict = {}
    new_map: dict = {}

    for key, pair in values.items():
        if not isinstance(key, str):
            raise DataChangeError("value keys must be strings")
        if key not in changed_set:
            raise DataChangeError("value key is not present in changed_fields")

        fs = spec.fields.get(key)
        if fs is None:                       # defense-in-depth
            raise DataChangeError("unknown field for this table")
        if fs.policy is ValuePolicy.NAME_ONLY:
            raise DataChangeError("field is name-only and must not carry values")

        if not isinstance(pair, ChangeValue):
            raise DataChangeError("values must map to ChangeValue instances")

        old = _validate_scalar(key, fs, pair.old)
        new = _validate_scalar(key, fs, pair.new)
        if old is None and new is None:
            raise DataChangeError(f"value for {key}: old and new must not both be null")
        if old == new and type(old) is type(new):
            # Поле объявлено изменённым, значит значения обязаны отличаться.
            # Заодно это детектор snapshot'а, снятого ПОСЛЕ мутации ORM.
            raise DataChangeError(f"value for {key}: old and new must differ")

        old_map[key] = old
        new_map[key] = new

    # Ключи строятся из одного источника — асимметрия невозможна по конструкции.
    return old_map, new_map


def _validate_context(context) -> Optional[RequestContext]:
    if context is None:
        return None
    if not isinstance(context, RequestContext):
        raise DataChangeError("context must be a RequestContext or None")
    try:
        # Та же строгая проверка, что у record_event: IP парсится, UA ≤ 512 без
        # control-chars, session hash — sha256 hex, path без ?/#, method из списка.
        validation.validate_context(context)
    except AuditError as exc:
        # Сообщения validation.py по построению не содержат исходных значений.
        raise DataChangeError(str(exc)) from None
    return context


# ── Публичная точка входа ─────────────────────────────────────────────────────

def record_data_change(
    *,
    table: str,
    record_id: int,
    operation: Operation,
    actor: Actor,
    changed_fields: Sequence[str],
    values: Optional[Mapping[str, ChangeValue]] = None,
    context: Optional[RequestContext] = None,
    db: Session,
) -> DataChangeResult:
    """Стейджит строку data_change_log в caller-транзакцию.

    Вызывается ТОЛЬКО рядом с успешным `TableSpec.paired_event` в той же сессии
    (caller-инвариант, см. AST-тест call sites). Контрактные нарушения →
    DataChangeError до db.add; сбой хранилища → DataChangeStorageError. Обе
    ошибки откатывают бизнес-транзакцию — журнал fail-closed.
    """
    spec = get_table_spec(table)                       # unknown → DataChangeError

    _validate_operation(spec, operation)
    record_id = _validate_record_id(record_id)
    _validate_actor(spec, actor)
    sorted_fields = _validate_changed_fields(spec, changed_fields)
    old_map, new_map = _validate_values(spec, sorted_fields, values)
    ctx = _validate_context(context)

    if db is None:
        raise DataChangeError("atomic write requires a caller db session")

    row = _build_row(spec, record_id, operation, actor, sorted_fields,
                     old_map, new_map, ctx)
    return _write_atomic(spec, row, db)


# ── ORM mapping / запись ──────────────────────────────────────────────────────

def _actor_id(actor: Actor) -> Optional[int]:
    return actor.user_id if actor.kind == "user" else None


def _actor_role(actor: Actor) -> Optional[str]:
    if actor.kind == "user":
        return actor.role
    if actor.kind == "system":
        return SYSTEM_ROLE
    return None


def _build_row(spec, record_id, operation, actor, sorted_fields,
               old_map, new_map, ctx) -> DataChangeLog:
    return DataChangeLog(
        actor_id=_actor_id(actor),
        actor_role=_actor_role(actor),
        table_name=spec.table,
        record_id=record_id,
        operation=operation.value,
        old_values=old_map,
        new_values=new_map,
        changed_fields=sorted_fields,
        # Единственное поле контекста, для которого в таблице есть колонка.
        ip_address=(ctx.ip_address if ctx else None),
    )


def _write_atomic(spec: TableSpec, row: DataChangeLog, db: Session) -> DataChangeResult:
    # ATOMIC: только db.add; caller коммитит. Сбой всегда fail-closed —
    # SOFT-режима у этого журнала не существует.
    try:
        db.add(row)
    except Exception as exc:
        _diag(spec.table, "add", type(exc).__name__)
        raise DataChangeStorageError(
            f"data change storage failure for {spec.table}"
        ) from None
    return DataChangeResult(state=WriteState.STAGED, table=spec.table)


__all__ = ["record_data_change", "project_changed_fields", "is_value_allowed"]
