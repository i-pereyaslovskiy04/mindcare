"""
Stage 8 — DTO read-only admin viewer журналов.

Гарантия отсутствия утечки здесь СТРУКТУРНАЯ: полей, которых нет в этих схемах,
не существует в JSON физически — их не «прячет» фронт и не отфильтровывает
сериализатор. Поэтому в модуле НЕТ и не должно появиться:

  * `description`, `log_metadata` в сыром виде;
  * `ip_address`, `user_agent`, `session_id`, `mfa_method`;
  * `request_url`, `request_method`;
  * `old_values` / `new_values`;
  * полного email (только `mask_email`);
  * внутреннего `users.id` (идентичность человека — только `uuid`).

`entry_id` — строка: `id` всех трёх журналов имеет тип BIGINT, а JSON-число в
JavaScript теряет точность за пределами 2^53.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

ActorKind = Literal["user", "system", "anonymous", "unavailable"]
OperationLiteral = Literal["INSERT", "UPDATE", "DELETE"]
OutcomeLiteral = Literal["success", "failure"]


class ActorOut(BaseModel):
    """Действующее лицо строки журнала.

    `display_name_current` / `email_masked` / `is_deleted_current` — ТЕКУЩЕЕ
    состояние связанного аккаунта, а не снимок на момент события; суффикс
    `_current` в имени поля обязателен именно поэтому. `role_at_event`, наоборот,
    берётся из самой строки журнала и для `auth_log` всегда `None` — этот журнал
    роль не хранит.
    """
    kind: ActorKind
    user_uuid: Optional[UUID] = None
    display_name_current: Optional[str] = None
    email_masked: Optional[str] = None
    role_at_event: Optional[str] = None
    is_deleted_current: Optional[bool] = None


class TargetUserOut(BaseModel):
    """Безопасная сводка пользователя-цели. Внутренний `users.id` не входит."""
    user_uuid: UUID
    display_name_current: str
    email_masked: str
    is_deleted_current: bool


class TargetOut(BaseModel):
    """Объект действия.

    `entity_ref` — внутренний технический идентификатор строки-цели. Для
    `entity_type == "user"` он ВСЕГДА `None`: идентичность человека передаётся
    только через `user.user_uuid` (правило проекта «внешний API использует
    users.uuid, не users.id»).
    """
    entity_type: str
    entity_ref: Optional[int] = None
    user: Optional[TargetUserOut] = None


class AuditEventOut(BaseModel):
    """Строка `audit_log`.

    `details_redacted=true` означает, что хотя бы одна часть строки была
    отброшена проекцией: metadata не прошла повторную валидацию, код отказа не
    зарегистрирован для этого события, target противоречит EventSpec, роль
    актора вне allowlist, ключ metadata не классифицирован в DTO-политике либо
    пользователь-цель не найден.
    """
    entry_id: str
    source: Literal["audit_log"] = "audit_log"
    occurred_at: datetime
    event_code: str
    known_event: bool
    actor: ActorOut
    target: Optional[TargetOut] = None
    outcome: Optional[OutcomeLiteral] = None
    failure_code: Optional[str] = None
    details: dict = Field(default_factory=dict)
    details_redacted: bool


class AuthEventOut(BaseModel):
    """Строка `auth_log`.

    `email_masked` — маскированный email, ЗАПИСАННЫЙ в момент события
    (денормализация `auth_log.user_email`). Это не то же самое, что
    `actor.email_masked`: там текущий email связанного аккаунта.
    """
    entry_id: str
    source: Literal["auth_log"] = "auth_log"
    occurred_at: datetime
    event_code: str
    known_event: bool
    actor: ActorOut
    success: bool
    failure_code: Optional[str] = None
    email_masked: Optional[str] = None
    details_redacted: bool


class DataChangeOut(BaseModel):
    """Строка `data_change_log` — только ИМЕНА изменённых allowlisted полей.

    `record_id` равен `None`, когда `table_name == "users"`: идентичность
    человека передаётся только через `target_user.user_uuid`.
    """
    entry_id: str
    source: Literal["data_change_log"] = "data_change_log"
    occurred_at: datetime
    known_change: bool
    actor: ActorOut
    table_name: Optional[str] = None
    record_id: Optional[int] = None
    operation: Optional[OperationLiteral] = None
    changed_fields: list[str] = Field(default_factory=list)
    target_user: Optional[TargetUserOut] = None
    details_redacted: bool


# ── Страницы (канон проекта: items / total / page / size) ─────────────────────

class AuditEventsPage(BaseModel):
    items: list[AuditEventOut]
    total: int = Field(description="Общее число строк с учётом фильтров")
    page: int
    size: int


class AuthEventsPage(BaseModel):
    items: list[AuthEventOut]
    total: int = Field(description="Общее число строк с учётом фильтров")
    page: int
    size: int


class DataChangesPage(BaseModel):
    items: list[DataChangeOut]
    total: int = Field(description="Общее число строк с учётом фильтров")
    page: int
    size: int


# ── Справочник фильтров ───────────────────────────────────────────────────────

class AuditLimitsOut(BaseModel):
    default_range_days: int
    max_range_days: int
    default_page_size: int
    max_page_size: int
    max_result_window: int
    orders: list[str]


class AuditOptionsOut(BaseModel):
    """Безопасные значения фильтров, вычисленные из живых REGISTRY /
    CHANGE_REGISTRY. Не содержит EventSpec internals, metadata schemas, строк
    журналов и каких-либо пользовательских данных.
    """
    audit_events: list[str]
    auth_events: list[str]
    actor_roles: list[str]
    outcomes: list[str]
    entity_types: list[str]
    tables: list[str]
    operations: list[str]
    actor_kinds: dict[str, list[str]]
    limits: AuditLimitsOut
