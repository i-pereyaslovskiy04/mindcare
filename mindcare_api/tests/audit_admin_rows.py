"""
Синтетические строки журналов для unit-тестов admin viewer (Stage 8).

Не тест-модуль (имя не начинается с `test_`), поэтому pytest его не собирает.
Проекция обращается к результату запроса только по именам атрибутов, поэтому
`SimpleNamespace` полностью заменяет SQLAlchemy `Row` и позволяет проверять
безопасность DTO вообще без БД.

Все значения синтетические. Реальные ПДн, токены и секреты в фикстурах
запрещены — см. `AGENTS.md`, раздел Sensitive data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

OCCURRED_AT = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)

ACTOR_UUID = UUID("11111111-1111-4111-8111-111111111111")
TARGET_UUID = UUID("22222222-2222-4222-8222-222222222222")

ACTOR_EMAIL = "synthetic.actor@example.test"
TARGET_EMAIL = "synthetic.target@example.test"
ACTOR_NAME = "Синтетический Актор"
TARGET_NAME = "Синтетическая Цель"


def _actor_columns(*, found=True, deleted_at=None):
    """Колонки OUTER JOIN с `users` по актору.

    `found=False` воспроизводит физическое отсутствие строки `users`: join не
    дал совпадения, поэтому все колонки алиаса — NULL.
    """
    if not found:
        return {
            "actor_row_id": None,
            "actor_user_uuid": None,
            "actor_full_name": None,
            "actor_email": None,
            "actor_deleted_at": None,
        }
    return {
        "actor_row_id": 42,
        "actor_user_uuid": ACTOR_UUID,
        "actor_full_name": ACTOR_NAME,
        "actor_email": ACTOR_EMAIL,
        "actor_deleted_at": deleted_at,
    }


def _target_columns(*, found=False, deleted_at=None):
    if not found:
        return {
            "target_user_uuid": None,
            "target_full_name": None,
            "target_email": None,
            "target_deleted_at": None,
        }
    return {
        "target_user_uuid": TARGET_UUID,
        "target_full_name": TARGET_NAME,
        "target_email": TARGET_EMAIL,
        "target_deleted_at": deleted_at,
    }


def audit_row(
    *,
    entry_id=9007199254740993,   # > 2^53: проверяет BIGINT → decimal string
    event_type="admin_role_add",
    actor_id=42,
    actor_role="admin",
    entity_type="user",
    entity_id=77,
    outcome="success",
    failure_code=None,
    raw_metadata=None,
    actor_found=True,
    actor_deleted_at=None,
    target_found=False,
    target_deleted_at=None,
    occurred_at=OCCURRED_AT,
):
    return SimpleNamespace(
        entry_id=entry_id,
        occurred_at=occurred_at,
        event_type=event_type,
        actor_id=actor_id,
        actor_role=actor_role,
        entity_type=entity_type,
        entity_id=entity_id,
        outcome=outcome,
        failure_code=failure_code,
        raw_metadata=raw_metadata,
        **_actor_columns(found=actor_found, deleted_at=actor_deleted_at),
        **_target_columns(found=target_found, deleted_at=target_deleted_at),
    )


def auth_row(
    *,
    entry_id=9007199254740994,
    event="login",
    actor_id=42,
    event_email=ACTOR_EMAIL,
    success=True,
    failure_reason=None,
    actor_found=True,
    actor_deleted_at=None,
    occurred_at=OCCURRED_AT,
):
    return SimpleNamespace(
        entry_id=entry_id,
        occurred_at=occurred_at,
        event=event,
        actor_id=actor_id,
        event_email=event_email,
        success=success,
        failure_reason=failure_reason,
        **_actor_columns(found=actor_found, deleted_at=actor_deleted_at),
    )


def dcl_row(
    *,
    entry_id=9007199254740995,
    table_name="meeting_types",
    record_id=15,
    operation="UPDATE",
    changed_fields=None,
    actor_id=42,
    actor_role="admin",
    actor_found=True,
    actor_deleted_at=None,
    target_found=False,
    target_deleted_at=None,
    occurred_at=OCCURRED_AT,
):
    return SimpleNamespace(
        entry_id=entry_id,
        occurred_at=occurred_at,
        actor_id=actor_id,
        actor_role=actor_role,
        table_name=table_name,
        record_id=record_id,
        operation=operation,
        changed_fields=["duration_minutes"] if changed_fields is None else changed_fields,
        **_actor_columns(found=actor_found, deleted_at=actor_deleted_at),
        **_target_columns(found=target_found, deleted_at=target_deleted_at),
    )
