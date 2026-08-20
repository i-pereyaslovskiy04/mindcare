"""
Stage 4A — типы контракта единого audit facade.

Immutable enums + frozen dataclasses. Ничего не импортирует из app.* (кроме stdlib),
чтобы избежать циклов. Модели/сессия/валидация подключаются в service.py.

Терминология:
  - actor  — действующее лицо (audit_log.user_id / auth_log.user_id).
  - target — объект действия (audit_log.entity_type/entity_id).
  - system actor — user_id=NULL, user_role="system" (только SYSTEM-события).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Literal, Mapping, Optional

# Пользовательские роли — БЕЗ "system" (system — не пользовательская роль).
USER_ROLES: frozenset = frozenset({"student", "psychologist", "supervisor", "admin"})
SYSTEM_ROLE: str = "system"


class Destination(enum.Enum):
    AUTH_LOG = "auth_log"
    AUDIT_LOG = "audit_log"
    # DATA_CHANGE_LOG — намеренно отсутствует в Stage 4A (Stage 6).


class Outcome(enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"


class ActorPolicy(enum.Enum):
    USER_REQUIRED = "user_required"
    USER_OR_ANONYMOUS = "user_or_anonymous"
    ANONYMOUS_ONLY = "anonymous_only"
    SYSTEM = "system"


class TargetPolicy(enum.Enum):
    REQUIRED = "required"
    FORBIDDEN = "forbidden"


class TxMode(enum.Enum):
    ATOMIC = "atomic"            # caller db; только db.add; caller коммитит
    INDEPENDENT = "independent"  # своя SessionLocal; add+commit+close


class FailurePolicy(enum.Enum):
    RAISE = "raise"   # fail-closed
    SOFT = "soft"     # fail-open


class DescriptionPolicy(enum.Enum):
    NONE = "none"
    STATIC = "static"


class WriteState(enum.Enum):
    STAGED = "staged"          # ATOMIC: добавлено в caller-session; commit за caller'ом
    PERSISTED = "persisted"    # INDEPENDENT: свой commit завершён
    SOFT_FAILED = "soft_failed"  # storage-сбой при SOFT


class StringFormat(enum.Enum):
    ENUM = "enum"
    MIME_TYPE = "mime_type"


# ── Ошибки ────────────────────────────────────────────────────────────────────

class AuditError(Exception):
    """Базовая ошибка контракта/валидации facade (единый catch для caller'ов)."""


class AuditStorageError(AuditError):
    """Санитизированный сбой записи журнала (подтип AuditError)."""


# ── Спецификация metadata-поля ────────────────────────────────────────────────

@dataclass(frozen=True)
class FieldSpec:
    type: Literal["str", "int", "bool", "str_list", "int_list"]
    fmt: Optional[StringFormat] = None      # обязателен для str / str_list
    enum: Optional[frozenset] = None        # при fmt=ENUM
    max_len: Optional[int] = None           # str / элементы str_list
    min_value: Optional[int] = None         # int / элементы int_list
    max_value: Optional[int] = None
    nullable: bool = False


@dataclass(frozen=True)
class EventSpec:
    name: str
    destination: Destination
    actor_policy: ActorPolicy
    allowed_actor_roles: frozenset          # ⊆ USER_ROLES; пусто для SYSTEM/ANONYMOUS_ONLY
    target_policy: TargetPolicy
    entity_type: Optional[str]
    allowed_outcomes: frozenset             # {Outcome...}
    allowed_failure_codes: frozenset        # стабильные коды; пусто для success-only
    metadata_schema: Mapping[str, FieldSpec]  # allowlist (immutable через MappingProxyType)
    tx_mode: TxMode                          # ровно один режим (без caller-override)
    failure_policy: FailurePolicy
    description_policy: DescriptionPolicy = DescriptionPolicy.NONE
    static_description: Optional[str] = None
    user_email_allowed: bool = False         # только AUTH_LOG


# ── Actor / Target / контекст / результат ─────────────────────────────────────

@dataclass(frozen=True)
class Actor:
    kind: Literal["user", "system", "anonymous"]
    user_id: Optional[int] = None
    role: Optional[str] = None

    @classmethod
    def user(cls, user_id: int, role: str) -> "Actor":
        return cls(kind="user", user_id=user_id, role=role)

    @classmethod
    def system(cls) -> "Actor":
        return cls(kind="system")

    @classmethod
    def anonymous(cls) -> "Actor":
        return cls(kind="anonymous")


@dataclass(frozen=True)
class Target:
    entity_type: str
    entity_id: int


@dataclass(frozen=True)
class RequestContext:
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    session_id_hash: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    # correlation_id намеренно отсутствует (нет симметричной колонки; отложено).


@dataclass(frozen=True)
class AuditResult:
    state: WriteState
    event: str
    error_class: Optional[str] = None
