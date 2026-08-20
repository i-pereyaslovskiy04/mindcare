"""
Stage 6-0 — immutable registry журналируемых таблиц + validate_change_registry.

CHANGE_REGISTRY владеет для каждой таблицы: парным событием audit_log
(`paired_event`), допустимыми операциями, actor-политикой и ЗАКРЫТЫМ allowlist
полей с политикой значений. Caller не выбирает таблицу произвольно и не может
расширить набор полей.

Ключевой инвариант минимизации:
    policy is not NAME_ONLY  =>  not is_denylisted_key(field)
Поле, чьё имя срабатывает на denylist (full_name, phone, email, comment,
primary_concern, ...), физически НЕ МОЖЕТ получить value-политику — попытка
объявить её роняет импорт модуля.

validate_change_registry() принимает произвольный набор specs и произвольный
event-registry (для негативных тестов без изменения production-объектов) и
вызывается на импорте против CHANGE_REGISTRY (fail-fast).
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Iterable, Mapping

from app.audit.contracts import (
    USER_ROLES, ActorPolicy, Destination, EventSpec, FailurePolicy, Outcome,
    TargetPolicy, TxMode,
)
from app.audit.change_contracts import (
    PG_INT32_MAX, PG_INT32_MIN, ChangeFieldSpec, DataChangeError, Operation,
    TableSpec, ValuePolicy,
)
from app.audit.registry import REGISTRY
from app.audit.validation import is_denylisted_key

# data_change_log.table_name VARCHAR(100); имя поля ограничиваем отдельно.
_TABLE_NAME_MAX = 100
_FIELD_NAME_MAX = 64
_JUSTIFICATION_MAX = 200
_ENUM_VALUE_MAX = 64

# Стабильные машинные имена: только lowercase snake_case, начинается с буквы.
_STABLE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_VALUE_POLICIES = frozenset({ValuePolicy.ENUM, ValuePolicy.BOOL, ValuePolicy.INT})

# actor-политики, осмысленные для изменения данных. Анонимный субъект данные не
# меняет, поэтому ANONYMOUS_ONLY / USER_OR_ANONYMOUS запрещены.
_ALLOWED_ACTOR_POLICIES = frozenset({ActorPolicy.USER_REQUIRED, ActorPolicy.SYSTEM})

_SUP_ADMIN = frozenset({"supervisor", "admin"})


# ── Переиспользуемые конструкторы FieldSpec ──────────────────────────────────

def _name_only(justification: str) -> ChangeFieldSpec:
    return ChangeFieldSpec(policy=ValuePolicy.NAME_ONLY, justification=justification)


def _int(justification: str, min_value: int, max_value: int) -> ChangeFieldSpec:
    return ChangeFieldSpec(
        policy=ValuePolicy.INT, justification=justification,
        min_value=min_value, max_value=max_value,
    )


def _bool(justification: str) -> ChangeFieldSpec:
    return ChangeFieldSpec(policy=ValuePolicy.BOOL, justification=justification)


def _enum(justification: str, allowed: Iterable[str]) -> ChangeFieldSpec:
    return ChangeFieldSpec(
        policy=ValuePolicy.ENUM, justification=justification,
        allowed=frozenset(allowed),
    )


# ── Таблицы ───────────────────────────────────────────────────────────────────
#
# Границы INT сверены с реальными Pydantic Create/Update-схемами, ORM и CHECK'ами.
# Journal НЕ вводит новых бизнес-лимитов: ChangeValue.old читается ИЗ БД, поэтому
# диапазон обязан покрывать любое уже существующее значение, иначе штатный PATCH
# откатывался бы из-за журнала.

_USERS = TableSpec(
    table="users",
    entity_type="user",
    paired_event="admin_user_updated",
    allowed_operations=frozenset({Operation.UPDATE}),
    actor_policy=ActorPolicy.USER_REQUIRED,
    allowed_actor_roles=frozenset({"admin"}),
    fields=MappingProxyType({
        # is_active выведен в admin_user_activated/deactivated; email этим путём
        # не редактируется; роли — admin_role_add/remove/update.
        "full_name": _name_only("ФИО — ПДн; журналируется только факт правки"),
        "phone": _name_only("телефон — ПДн; журналируется только факт правки"),
    }),
)

_UNREGISTERED_CARDS = TableSpec(
    table="unregistered_student_cards",
    entity_type="unregistered_student_card",
    paired_event="unregistered_student_card_updated",
    allowed_operations=frozenset({Operation.UPDATE}),
    actor_policy=ActorPolicy.USER_REQUIRED,
    allowed_actor_roles=_SUP_ADMIN,
    fields=MappingProxyType({
        "full_name": _name_only("ФИО — ПДн"),
        "phone": _name_only("телефон — ПДн"),
        "email": _name_only("email — ПДн"),
        "birth_date": _name_only("дата рождения — ПДн"),
        "comment": _name_only("свободный текст, возможны псих. сведения"),
        "primary_concern": _name_only("запрос клиента — терапевтический контент"),
    }),
    # normalized_email добавляется сервисом при смене email и попадает в
    # storage-дифф. Это производный дубликат ПДн: отбрасывается явно, поэтому
    # смена email даёт changed_fields=["email"], а не ошибку.
    derived_fields=frozenset({"normalized_email"}),
)

_MEETING_TYPES = TableSpec(
    table="meeting_types",
    entity_type="meeting_type",
    paired_event="meeting_type_updated",
    allowed_operations=frozenset({Operation.UPDATE}),
    actor_policy=ActorPolicy.USER_REQUIRED,
    allowed_actor_roles=_SUP_ADMIN,
    fields=MappingProxyType({
        # is_active выведен в meeting_type_activated/deactivated.
        "name": _name_only("свободный текст справочника"),
        "description": _name_only("свободный текст"),
        "duration_minutes": _int(
            "конфигурация длительности слота, не относится к субъекту ПДн; "
            "границы повторяют Pydantic Create/Update (ge=10, le=480)",
            10, 480,
        ),
        "buffer_minutes": _int(
            "конфигурация буфера между слотами; границы повторяют Pydantic "
            "Create/Update (ge=0, le=120)",
            0, 120,
        ),
        "display_order": _int(
            "порядок сортировки в UI; прикладных границ нет ни в Pydantic, ни "
            "в ORM, ни в CHECK — берётся диапазон PostgreSQL INTEGER, чтобы не "
            "вводить новый бизнес-лимит",
            PG_INT32_MIN, PG_INT32_MAX,
        ),
        "allow_in_person": _bool("организационный флаг формата встречи"),
        "allow_online": _bool("организационный флаг формата встречи"),
        "is_group": _bool("тип проведения, не сведение о человеке"),
        "is_bookable": _bool("доступность типа для самостоятельной записи"),
    }),
)

_GROUP_SESSIONS = TableSpec(
    table="group_sessions",
    entity_type="group_session",
    paired_event="group_session_updated",
    allowed_operations=frozenset({Operation.UPDATE}),
    actor_policy=ActorPolicy.USER_REQUIRED,
    allowed_actor_roles=_SUP_ADMIN,
    fields=MappingProxyType({
        # booking_enabled/status выведены в booking_opened/closed и cancelled.
        "title": _name_only("свободный текст"),
        "description": _name_only("свободный текст"),
        "starts_at": _name_only("datetime вне {enum,bool,int} — значение не пишется"),
        "ends_at": _name_only("datetime вне {enum,bool,int} — значение не пишется"),
        "format": _enum(
            "стабильный организационный enum формата занятия",
            {"in_person", "online"},
        ),
        "capacity": _int(
            "вместимость занятия; границы повторяют Pydantic Create/Update "
            "(ge=1, le=500)",
            1, 500,
        ),
        "meeting_type_id": _int(
            "FK на справочник конфигурации meeting_types — никого не "
            "идентифицирует; > 0 гарантировано существованием FK-объекта "
            "(SERIAL id, ON DELETE RESTRICT), новый инвариант не вводится",
            1, PG_INT32_MAX,
        ),
        # FK на users: идентифицирует человека, поэтому под «неперсональные
        # технические идентификаторы» НЕ подпадает.
        "psychologist_id": _name_only("FK на users — идентифицирует человека"),
    }),
)

_ALL_TABLES: list[TableSpec] = [
    _USERS, _UNREGISTERED_CARDS, _MEETING_TYPES, _GROUP_SESSIONS,
]


# ── Валидация ────────────────────────────────────────────────────────────────

def _validate_stable_name(value, what: str, max_len: int) -> None:
    if not isinstance(value, str) or not value:
        raise DataChangeError(f"{what} must be a non-empty string")
    if len(value) > max_len:
        raise DataChangeError(f"{what} length out of bounds")
    if not _STABLE_NAME_RE.fullmatch(value):
        raise DataChangeError(f"{what} must be stable snake_case")


def _validate_field_spec(table: str, fname: str, fs: ChangeFieldSpec) -> None:
    if not isinstance(fs, ChangeFieldSpec):
        raise DataChangeError(f"{table}.{fname}: expected ChangeFieldSpec")
    if not isinstance(fs.policy, ValuePolicy):
        raise DataChangeError(f"{table}.{fname}: invalid ValuePolicy")

    if not isinstance(fs.justification, str) or not fs.justification.strip():
        raise DataChangeError(f"{table}.{fname}: justification is required")
    if len(fs.justification) > _JUSTIFICATION_MAX:
        raise DataChangeError(f"{table}.{fname}: justification too long")

    if not isinstance(fs.nullable, bool):
        raise DataChangeError(f"{table}.{fname}: nullable must be bool")

    # Ключевой инвариант минимизации: чувствительное имя ⇒ только name-only.
    if fs.policy in _VALUE_POLICIES and is_denylisted_key(fname):
        raise DataChangeError(
            f"{table}.{fname}: denylisted field name must stay NAME_ONLY"
        )

    if fs.policy is ValuePolicy.ENUM:
        if not isinstance(fs.allowed, frozenset) or not fs.allowed:
            raise DataChangeError(
                f"{table}.{fname}: ENUM requires a non-empty frozenset"
            )
        for value in fs.allowed:
            if not isinstance(value, str) or not value:
                raise DataChangeError(
                    f"{table}.{fname}: ENUM values must be non-empty str"
                )
            if len(value) > _ENUM_VALUE_MAX:
                raise DataChangeError(f"{table}.{fname}: ENUM value too long")
        if fs.min_value is not None or fs.max_value is not None:
            raise DataChangeError(f"{table}.{fname}: ENUM must not set min/max")
    elif fs.policy is ValuePolicy.INT:
        if fs.allowed is not None:
            raise DataChangeError(f"{table}.{fname}: INT must not set allowed")
        if not isinstance(fs.min_value, int) or isinstance(fs.min_value, bool):
            raise DataChangeError(f"{table}.{fname}: INT requires min_value")
        if not isinstance(fs.max_value, int) or isinstance(fs.max_value, bool):
            raise DataChangeError(f"{table}.{fname}: INT requires max_value")
        if fs.min_value > fs.max_value:
            raise DataChangeError(f"{table}.{fname}: min_value > max_value")
        if fs.min_value < PG_INT32_MIN or fs.max_value > PG_INT32_MAX:
            raise DataChangeError(
                f"{table}.{fname}: INT bounds exceed PostgreSQL INTEGER"
            )
    else:  # BOOL / NAME_ONLY
        if (fs.allowed is not None or fs.min_value is not None
                or fs.max_value is not None):
            raise DataChangeError(
                f"{table}.{fname}: {fs.policy.value} must not set allowed/min/max"
            )


def _validate_paired_event(
    spec: TableSpec, event_registry: Mapping[str, EventSpec],
) -> None:
    """Совместимость TableSpec с парным событием audit_log."""
    name = spec.paired_event
    _validate_stable_name(name, f"{spec.table}: paired_event", 100)

    event = event_registry.get(name)
    if event is None:
        raise DataChangeError(f"{spec.table}: unknown paired_event {name!r}")

    if event.destination is not Destination.AUDIT_LOG:
        raise DataChangeError(f"{spec.table}: paired_event must target audit_log")
    if event.entity_type != spec.entity_type:
        raise DataChangeError(f"{spec.table}: paired_event entity_type mismatch")
    if event.target_policy is not TargetPolicy.REQUIRED:
        raise DataChangeError(f"{spec.table}: paired_event must require a target")
    if event.allowed_outcomes != frozenset({Outcome.SUCCESS}):
        raise DataChangeError(f"{spec.table}: paired_event must be success-only")
    if event.allowed_failure_codes:
        raise DataChangeError(
            f"{spec.table}: paired_event must not declare failure codes"
        )
    if event.tx_mode is not TxMode.ATOMIC:
        raise DataChangeError(f"{spec.table}: paired_event must be ATOMIC")
    if event.failure_policy is not FailurePolicy.RAISE:
        raise DataChangeError(f"{spec.table}: paired_event must be fail-closed")
    if event.actor_policy is not spec.actor_policy:
        raise DataChangeError(f"{spec.table}: paired_event actor_policy mismatch")
    if not spec.allowed_actor_roles <= event.allowed_actor_roles:
        raise DataChangeError(
            f"{spec.table}: actor roles must not exceed paired_event roles"
        )


def validate_change_registry(
    specs: Mapping[str, TableSpec],
    *,
    event_registry: Mapping[str, EventSpec] = REGISTRY,
) -> None:
    """Валидирует произвольный набор TableSpec; бросает DataChangeError на первом
    нарушении. event_registry инъецируется, чтобы негативные тесты не трогали
    production REGISTRY."""
    seen: set = set()
    for key, spec in specs.items():
        if not isinstance(spec, TableSpec):
            raise DataChangeError(f"registry value for {key!r} is not a TableSpec")
        if key != spec.table:
            raise DataChangeError(
                f"registry key {key!r} != spec.table {spec.table!r}"
            )
        if spec.table in seen:
            raise DataChangeError(f"duplicate table {spec.table!r}")
        seen.add(spec.table)

        _validate_stable_name(spec.table, "table", _TABLE_NAME_MAX)
        _validate_stable_name(spec.entity_type, f"{spec.table}: entity_type", 100)

        if not spec.allowed_operations:
            raise DataChangeError(f"{spec.table}: allowed_operations is empty")
        for op in spec.allowed_operations:
            if not isinstance(op, Operation):
                raise DataChangeError(
                    f"{spec.table}: allowed_operations must hold Operation"
                )

        if spec.actor_policy not in _ALLOWED_ACTOR_POLICIES:
            raise DataChangeError(f"{spec.table}: unsupported actor_policy")
        if spec.actor_policy is ActorPolicy.SYSTEM:
            if spec.allowed_actor_roles:
                raise DataChangeError(f"{spec.table}: SYSTEM must have no roles")
        else:
            if not spec.allowed_actor_roles:
                raise DataChangeError(f"{spec.table}: USER_REQUIRED needs roles")
            if not spec.allowed_actor_roles <= USER_ROLES:
                raise DataChangeError(
                    f"{spec.table}: roles must be within USER_ROLES"
                )

        if not spec.fields:
            raise DataChangeError(f"{spec.table}: fields is empty")
        for fname, fs in spec.fields.items():
            _validate_stable_name(
                fname, f"{spec.table}: field name", _FIELD_NAME_MAX,
            )
            _validate_field_spec(spec.table, fname, fs)

        for dname in spec.derived_fields:
            _validate_stable_name(
                dname, f"{spec.table}: derived field name", _FIELD_NAME_MAX,
            )
        if set(spec.fields) & set(spec.derived_fields):
            raise DataChangeError(
                f"{spec.table}: fields and derived_fields must be disjoint"
            )

        _validate_paired_event(spec, event_registry)


# Единственные типы, принимаемые как исходный материал для frozenset-полей
# TableSpec. str/bytes/bytearray НЕ входят: формально они Iterable, но
# frozenset("email") молча дал бы {'e','m','a','i','l'} — тот же класс бага,
# что и changed_fields в data_change.py.
_COLLECTION_INPUT_TYPES = (frozenset, set, list, tuple)


def _normalize_collection(value, what: str) -> frozenset:
    """Проверяет тип и возвращает НОВЫЙ frozenset — независимую копию, не
    live-view поверх переданного caller'ом set/list."""
    if isinstance(value, (str, bytes, bytearray)):
        raise DataChangeError(f"{what} must be a collection, not a string")
    if not isinstance(value, _COLLECTION_INPUT_TYPES):
        raise DataChangeError(f"{what} must be a collection")
    return frozenset(value)


def _normalize_fields(value, table_hint: str) -> Mapping[str, ChangeFieldSpec]:
    """Проверяет тип и возвращает НОВЫЙ MappingProxyType поверх СВЕЖЕГО dict.

    MappingProxyType(d) — это live-view поверх ЧУЖОГО d: если построить
    registry прямо из d caller'а, мутация d ПОСЛЕ build() продолжает быть
    видна через прокси. Копия (dict(value)) разрывает эту связь.
    """
    if not isinstance(value, Mapping):
        raise DataChangeError(f"{table_hint}: fields must be a mapping")
    return MappingProxyType(dict(value))


def _normalize_table_spec(spec: TableSpec) -> TableSpec:
    """Строит НОВЫЙ TableSpec с защитно скопированными контейнерами.

    Без этого шага registry не является глубоко immutable: caller, сохранивший
    ссылку на исходный dict/set/list, переданный в TableSpec(...), мог бы
    изменить allowlist ПОСЛЕ построения CHANGE_REGISTRY. Копирование выполняется
    ЗДЕСЬ, ДО дальнейшей валидации, и с явными isinstance-проверками — неверный
    тип даёт DataChangeError, а не TypeError/AttributeError где-то глубже в
    validate_change_registry (например `for op in 5` или `spec.fields.items()`
    на int).
    """
    table_hint = spec.table if isinstance(spec.table, str) else "<table>"

    operations = _normalize_collection(
        spec.allowed_operations, f"{table_hint}: allowed_operations",
    )
    roles = _normalize_collection(
        spec.allowed_actor_roles, f"{table_hint}: allowed_actor_roles",
    )
    fields = _normalize_fields(spec.fields, table_hint)
    derived = _normalize_collection(
        spec.derived_fields, f"{table_hint}: derived_fields",
    )

    return TableSpec(
        table=spec.table,
        entity_type=spec.entity_type,
        paired_event=spec.paired_event,
        allowed_operations=operations,
        actor_policy=spec.actor_policy,
        allowed_actor_roles=roles,
        fields=fields,
        derived_fields=derived,
    )


def build_change_registry(
    specs: Iterable[TableSpec],
    *,
    event_registry: Mapping[str, EventSpec] = REGISTRY,
) -> Mapping[str, TableSpec]:
    """Строит ГЛУБОКО immutable registry.

    Каждый TableSpec нормализуется в НОВЫЙ экземпляр с независимо
    скопированными allowed_operations/allowed_actor_roles/fields/
    derived_fields (см. _normalize_table_spec) — построенный registry не
    разделяет мутируемое состояние ни с исходными specs, ни друг с другом.
    Дубликаты таблиц обнаруживаются ДО создания итогового dict; затем
    полученный mapping валидируется (fail-fast).
    """
    seen: set = set()
    mapping: dict = {}
    for spec in specs:
        if not isinstance(spec, TableSpec):
            raise DataChangeError("registry build expects TableSpec instances")
        normalized = _normalize_table_spec(spec)
        if normalized.table in seen:
            raise DataChangeError(
                f"duplicate table in registry build: {normalized.table!r}"
            )
        seen.add(normalized.table)
        mapping[normalized.table] = normalized
    frozen: Mapping[str, TableSpec] = MappingProxyType(mapping)
    validate_change_registry(frozen, event_registry=event_registry)
    return frozen


def get_table_spec(table: str) -> TableSpec:
    if not isinstance(table, str):
        raise DataChangeError("table must be a string")
    spec = CHANGE_REGISTRY.get(table)
    if spec is None:
        raise DataChangeError(f"unknown data-change table: {table!r}")
    return spec


def is_value_allowed(table: str, field_name: str) -> bool:
    """True, если для поля разрешено сохранять old/new значение.

    Используется caller'ами, чтобы снимать snapshot ТОЛЬКО по value-enabled
    полям и не тянуть ПДн в audit-слой даже временно.
    """
    spec = get_table_spec(table)
    fs = spec.fields.get(field_name)
    if fs is None:
        raise DataChangeError("unknown field for this table")
    return fs.policy in _VALUE_POLICIES


# Production registry: дубликаты ловятся в build_change_registry ДО создания
# dict; validate_change_registry вызывается изнутри — fail-fast при импорте.
CHANGE_REGISTRY: Mapping[str, TableSpec] = build_change_registry(_ALL_TABLES)
