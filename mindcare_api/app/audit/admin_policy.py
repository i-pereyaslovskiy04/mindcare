"""
Stage 8 — производные от registry множества для read-only admin viewer журналов.

Лист-модуль: импортирует только `app.audit.contracts` / `registry` /
`change_registry` / `change_contracts`. Его импортируют и `admin_storage`
(SQL-предикаты), и `admin_service` (проекция DTO) — это и есть структурная
гарантия того, что фильтр и отображение классифицируют одну и ту же строку
одинаково. Дублировать эти множества где-либо ещё запрещено.

Ключевой момент — классификация actor. Наивное правило «user_id IS NULL ⇒
anonymous» НЕВЕРНО: FK всех трёх журналов объявлен `ON DELETE SET NULL`
(`app/db/models/audit.py`), поэтому после физического удаления пользователя
строки `login` / `logout` / `password_change` тоже получают `user_id = NULL`,
хотя actor изначально был пользовательским. Класс выводится из `ActorPolicy`
конкретной спеки, а для `audit_log` / `data_change_log` дополнительно
проверяется, что роль строки входит в `allowed_actor_roles` этой спеки.
`auth_log` роль не хранит вообще, поэтому там такой проверки нет.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional

from app.audit.change_contracts import Operation
from app.audit.change_registry import CHANGE_REGISTRY
from app.audit.contracts import (
    SYSTEM_ROLE, USER_ROLES, ActorPolicy, Destination, EventSpec, TargetPolicy,
)
from app.audit.registry import REGISTRY

# ── Имена журналов ────────────────────────────────────────────────────────────
JOURNAL_AUDIT: str = "audit_log"
JOURNAL_AUTH: str = "auth_log"
JOURNAL_DCL: str = "data_change_log"
JOURNALS: tuple = (JOURNAL_AUDIT, JOURNAL_AUTH, JOURNAL_DCL)

# ── Классы актора ─────────────────────────────────────────────────────────────
KIND_USER: str = "user"
KIND_SYSTEM: str = "system"
KIND_ANONYMOUS: str = "anonymous"
KIND_UNAVAILABLE: str = "unavailable"
# Канонический порядок для UI/OpenAPI (НЕ алфавитный: «неизвестно» — последним).
KIND_ORDER: tuple = (KIND_USER, KIND_SYSTEM, KIND_ANONYMOUS, KIND_UNAVAILABLE)

# Стабильный код, которым подменяется любое неизвестное/legacy имя события.
# Raw-имя наружу не отдаётся; допустимым значением фильтра этот код НЕ является.
LEGACY_EVENT_CODE: str = "legacy_unknown_event"

_USER_CAPABLE = frozenset({ActorPolicy.USER_REQUIRED, ActorPolicy.USER_OR_ANONYMOUS})
_ANON_CAPABLE = frozenset({ActorPolicy.ANONYMOUS_ONLY, ActorPolicy.USER_OR_ANONYMOUS})


@dataclass(frozen=True)
class JournalPolicy:
    """Разбиение ключей одного журнала по actor-политике.

    `key` — то, что идентифицирует спеку строки: имя события для `audit_log` /
    `auth_log` и имя таблицы для `data_change_log`.

    `names_by_roleset` — те же user-capable ключи, сгруппированные по
    одинаковому набору допустимых ролей. Нужен только для компактного SQL:
    вместо 87 веток `OR` получается несколько (различных наборов ролей единицы).
    `roles_by_name` — та же информация для построчной проекции.
    """
    journal: str
    role_aware: bool                       # audit_log / DCL — да, auth_log — нет
    all_names: frozenset
    user_names: frozenset
    anon_names: frozenset
    system_names: frozenset
    roles_by_name: Mapping[str, frozenset]
    names_by_roleset: Mapping[frozenset, frozenset]
    kinds: tuple                           # producible kinds в KIND_ORDER


def _group_by_roleset(
    roles_by_name: Mapping[str, frozenset],
) -> Mapping[frozenset, frozenset]:
    grouped: dict = {}
    for name, roles in roles_by_name.items():
        grouped.setdefault(roles, set()).add(name)
    return MappingProxyType({k: frozenset(v) for k, v in grouped.items()})


def _build_policy(
    journal: str, specs: Mapping[str, object], *, role_aware: bool,
) -> JournalPolicy:
    user_names, anon_names, system_names = set(), set(), set()
    roles_by_name: dict = {}
    for name, spec in specs.items():
        policy = spec.actor_policy
        if policy in _USER_CAPABLE:
            user_names.add(name)
            roles_by_name[name] = frozenset(spec.allowed_actor_roles)
        if policy in _ANON_CAPABLE:
            anon_names.add(name)
        if policy is ActorPolicy.SYSTEM:
            system_names.add(name)

    producible = set()
    if user_names:
        producible.add(KIND_USER)
    if system_names:
        producible.add(KIND_SYSTEM)
    if anon_names:
        producible.add(KIND_ANONYMOUS)
    # unavailable producible ВСЕГДА: неизвестное имя, отсутствующий User и
    # противоречие строки собственной спеке возможны в любом журнале.
    producible.add(KIND_UNAVAILABLE)

    return JournalPolicy(
        journal=journal,
        role_aware=role_aware,
        all_names=frozenset(specs),
        user_names=frozenset(user_names),
        anon_names=frozenset(anon_names),
        system_names=frozenset(system_names),
        roles_by_name=MappingProxyType(dict(roles_by_name)),
        names_by_roleset=_group_by_roleset(roles_by_name),
        kinds=tuple(k for k in KIND_ORDER if k in producible),
    )


def _by_destination(destination: Destination) -> Mapping[str, EventSpec]:
    return MappingProxyType({
        n: s for n, s in REGISTRY.items() if s.destination is destination
    })


AUDIT_EVENT_SPECS: Mapping[str, EventSpec] = _by_destination(Destination.AUDIT_LOG)
AUTH_EVENT_SPECS: Mapping[str, EventSpec] = _by_destination(Destination.AUTH_LOG)

AUDIT_EVENT_NAMES: frozenset = frozenset(AUDIT_EVENT_SPECS)
AUTH_EVENT_NAMES: frozenset = frozenset(AUTH_EVENT_SPECS)

AUDIT_POLICY = _build_policy(JOURNAL_AUDIT, AUDIT_EVENT_SPECS, role_aware=True)
AUTH_POLICY = _build_policy(JOURNAL_AUTH, AUTH_EVENT_SPECS, role_aware=False)
DCL_POLICY = _build_policy(JOURNAL_DCL, CHANGE_REGISTRY, role_aware=True)

POLICY_BY_JOURNAL: Mapping[str, JournalPolicy] = MappingProxyType({
    JOURNAL_AUDIT: AUDIT_POLICY,
    JOURNAL_AUTH: AUTH_POLICY,
    JOURNAL_DCL: DCL_POLICY,
})

# ── Target: какие события над каким типом сущности вообще законны ─────────────
# Используется и фильтрами (отбираем только семантически корректный target), и
# проекцией (несогласованная legacy-строка редактируется целиком).
_events_by_entity: dict = {}
for _name, _spec in AUDIT_EVENT_SPECS.items():
    if _spec.target_policy is TargetPolicy.REQUIRED and _spec.entity_type:
        _events_by_entity.setdefault(_spec.entity_type, set()).add(_name)

EVENTS_BY_ENTITY_TYPE: Mapping[str, frozenset] = MappingProxyType({
    et: frozenset(names) for et, names in _events_by_entity.items()
})
ENTITY_TYPES: frozenset = frozenset(EVENTS_BY_ENTITY_TYPE)
USER_ENTITY_TYPE: str = "user"
USER_TARGET_EVENTS: frozenset = EVENTS_BY_ENTITY_TYPE.get(
    USER_ENTITY_TYPE, frozenset(),
)

# ── data_change_log ───────────────────────────────────────────────────────────
CHANGE_TABLE_NAMES: frozenset = frozenset(CHANGE_REGISTRY)
# Union реальных allowed_operations, а НЕ все три литерала Operation: сегодня
# все четыре TableSpec допускают только UPDATE, и фильтр обязан это отражать.
CHANGE_OPERATIONS: frozenset = frozenset(
    op.value for spec in CHANGE_REGISTRY.values() for op in spec.allowed_operations
)
USERS_TABLE: str = "users"

# ── Прочие фильтруемые множества ──────────────────────────────────────────────
ACTOR_ROLES: frozenset = USER_ROLES
OUTCOMES: tuple = ("success", "failure")
ORDERS: tuple = ("asc", "desc")

ACCESS_EVENT: str = "audit_logs_viewed"


def classify_actor(
    policy: JournalPolicy,
    *,
    key: Optional[str],
    actor_id: Optional[int],
    role: Optional[str],
    user_found: bool,
) -> str:
    """Класс актора строки журнала. Зеркало SQL-предикатов `admin_storage`.

    `user_found` — найдена ли физически строка `users` по actor_id. Soft-deleted
    пользователь СЧИТАЕТСЯ найденным: он остаётся `user`, а факт удаления
    передаётся отдельным полем DTO.
    """
    if key is None or key not in policy.all_names:
        return KIND_UNAVAILABLE

    if actor_id is not None:
        if key not in policy.user_names:
            return KIND_UNAVAILABLE          # id есть там, где его быть не может
        if not user_found:
            return KIND_UNAVAILABLE
        if policy.role_aware:
            allowed = policy.roles_by_name.get(key, frozenset())
            if role is None or role not in allowed:
                return KIND_UNAVAILABLE      # роль противоречит собственной спеке
        return KIND_USER

    # actor_id IS NULL — либо изначально безакторное событие, либо FK обнулён
    # при физическом удалении пользователя (ON DELETE SET NULL).
    if key in policy.anon_names:
        return KIND_ANONYMOUS
    if key in policy.system_names and role == SYSTEM_ROLE:
        return KIND_SYSTEM
    return KIND_UNAVAILABLE


def role_at_event(
    policy: JournalPolicy, kind: str, role: Optional[str],
) -> Optional[str]:
    """Роль на момент события. `auth_log` роль не хранит — там всегда None.

    Для прочих журналов возвращается только валидная пользовательская роль и
    только у actor'а класса `user`: строка, чья роль противоречит спеке, уже
    классифицирована как `unavailable`, и показывать её роль нельзя.
    """
    if not policy.role_aware or kind != KIND_USER:
        return None
    return role if role in USER_ROLES else None


def audit_spec(event: Optional[str]) -> Optional[EventSpec]:
    """EventSpec строки `audit_log` или None (unknown / destination-mismatch)."""
    if not event:
        return None
    return AUDIT_EVENT_SPECS.get(event)


def auth_spec(event: Optional[str]) -> Optional[EventSpec]:
    """EventSpec строки `auth_log` или None (unknown / destination-mismatch)."""
    if not event:
        return None
    return AUTH_EVENT_SPECS.get(event)


# ── Fail-fast инварианты (в стиле build_registry / build_change_registry) ─────

def _validate_derived() -> None:
    if not AUDIT_EVENT_NAMES or not AUTH_EVENT_NAMES:
        raise AssertionError("admin_policy: empty event partition")
    if AUDIT_EVENT_NAMES & AUTH_EVENT_NAMES:
        raise AssertionError("admin_policy: destination partition overlaps")
    if ACCESS_EVENT not in AUDIT_EVENT_NAMES:
        raise AssertionError("admin_policy: access event is not registered")
    if LEGACY_EVENT_CODE in AUDIT_EVENT_NAMES or LEGACY_EVENT_CODE in AUTH_EVENT_NAMES:
        raise AssertionError("admin_policy: legacy code collides with a real event")
    if not CHANGE_OPERATIONS <= frozenset(op.value for op in Operation):
        raise AssertionError("admin_policy: unknown data-change operation")
    for policy in POLICY_BY_JOURNAL.values():
        if KIND_UNAVAILABLE not in policy.kinds:
            raise AssertionError(f"{policy.journal}: unavailable must be producible")
        for roles in policy.roles_by_name.values():
            if not roles <= USER_ROLES:
                raise AssertionError(f"{policy.journal}: roles outside USER_ROLES")


_validate_derived()
