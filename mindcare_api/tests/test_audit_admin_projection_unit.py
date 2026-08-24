"""
Stage 8 — безопасная проекция строки журнала в DTO (без БД).

Проверяется главное свойство viewer: всё, что противоречит собственной спеке
строки, редактируется, а не показывается «как есть», и ни один внутренний
`users.id` не выходит наружу.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.audit import admin_policy as pol
from app.audit import admin_service as svc
from tests.audit_admin_rows import (
    ACTOR_EMAIL, ACTOR_NAME, ACTOR_UUID, TARGET_EMAIL, TARGET_UUID,
    audit_row, auth_row, dcl_row,
)


def _one(row):
    items = svc._project_audit_rows([row])
    assert len(items) == 1
    return items[0]


def _one_auth(row):
    """Проекция auth-строки без обращения к БД и без access-события."""
    spec = pol.auth_spec(row.event)
    actor, actor_redacted = svc._project_actor(
        pol.AUTH_POLICY, key=row.event, actor_id=row.actor_id, role=None, row=row,
    )
    failure_code, failure_redacted = svc._project_auth_failure(
        spec, bool(row.success), row.failure_reason,
    )
    return actor, failure_code, actor_redacted or failure_redacted


# ── Идентификатор строки ──────────────────────────────────────────────────────

def test_bigint_entry_id_is_serialised_as_decimal_string():
    """`id` журналов — BIGINT; JSON-число в JavaScript теряет точность после
    2^53, поэтому наружу идёт строка."""
    item = _one(audit_row(entry_id=9007199254740993))
    assert item.entry_id == "9007199254740993"
    assert isinstance(item.entry_id, str)


# ── Известность события ───────────────────────────────────────────────────────

def test_known_event_keeps_its_stable_name():
    item = _one(audit_row(event_type="admin_role_add"))
    assert item.known_event is True
    assert item.event_code == "admin_role_add"


@pytest.mark.parametrize("event_type", [
    "no_such_event_at_all",
    "login",                 # AUTH_LOG-событие в строке audit_log
    "",
    None,
])
def test_unknown_or_mismatched_event_is_fully_redacted(event_type):
    item = _one(audit_row(event_type=event_type, outcome="success",
                          failure_code="internal_error",
                          raw_metadata={"anything": "at all"}))
    assert item.known_event is False
    assert item.event_code == pol.LEGACY_EVENT_CODE
    # Спеки нет — сверять не с чем, поэтому не показываем ничего.
    assert item.outcome is None
    assert item.failure_code is None
    assert item.target is None
    assert item.details == {}
    assert item.details_redacted is True


def test_raw_unknown_event_name_never_leaves_the_backend():
    item = _one(audit_row(event_type="totally_made_up_legacy_event"))
    assert "totally_made_up_legacy_event" not in item.model_dump_json()


# ── Исход и код отказа ────────────────────────────────────────────────────────

def test_failure_code_registered_for_the_event_is_returned():
    item = _one(audit_row(
        event_type="admin_user_create_failed", entity_type=None, entity_id=None,
        outcome="failure", failure_code="email_already_exists",
    ))
    assert item.outcome == "failure"
    assert item.failure_code == "email_already_exists"
    assert item.details_redacted is False


def test_failure_code_outside_the_event_contract_is_dropped():
    item = _one(audit_row(
        event_type="admin_user_create_failed", entity_type=None, entity_id=None,
        outcome="failure", failure_code="something_invented_later",
    ))
    assert item.outcome == "failure"
    assert item.failure_code is None
    assert item.details_redacted is True


def test_outcome_outside_the_event_contract_is_dropped():
    """`admin_role_add` объявлен success-only — строка с failure противоречива."""
    item = _one(audit_row(event_type="admin_role_add", outcome="failure",
                          failure_code="internal_error"))
    assert item.outcome is None
    assert item.failure_code is None
    assert item.details_redacted is True


def test_success_carrying_a_failure_code_is_redacted():
    item = _one(audit_row(event_type="admin_role_add", outcome="success",
                          failure_code="internal_error"))
    assert item.outcome == "success"
    assert item.failure_code is None
    assert item.details_redacted is True


@pytest.mark.parametrize("raw", ["partial", "SUCCESS", "", None])
def test_non_literal_outcome_is_dropped(raw):
    item = _one(audit_row(event_type="admin_role_add", outcome=raw))
    assert item.outcome is None
    assert item.details_redacted is True


# ── Target против конкретного EventSpec ───────────────────────────────────────

def test_user_target_exposes_uuid_and_never_the_internal_id():
    item = _one(audit_row(event_type="admin_role_add", entity_type="user",
                          entity_id=77, target_found=True))
    assert item.target.entity_type == "user"
    assert item.target.entity_ref is None          # users.id наружу не идёт
    assert item.target.user.user_uuid == TARGET_UUID
    assert "77" not in item.model_dump_json()


def test_non_user_target_exposes_a_technical_reference():
    item = _one(audit_row(event_type="appointment_created",
                          entity_type="appointment", entity_id=501,
                          actor_role="student"))
    assert item.target.entity_type == "appointment"
    assert item.target.entity_ref == 501
    assert item.target.user is None
    assert item.details_redacted is False


def test_user_target_without_an_account_is_redacted():
    item = _one(audit_row(event_type="admin_role_add", entity_type="user",
                          entity_id=77, target_found=False))
    assert item.target.entity_type == "user"
    assert item.target.entity_ref is None
    assert item.target.user is None
    assert item.details_redacted is True


def test_target_on_an_event_that_forbids_targets_is_dropped():
    item = _one(audit_row(
        event_type="admin_user_create_failed", entity_type="user", entity_id=77,
        outcome="failure", failure_code="internal_error",
    ))
    assert item.target is None
    assert item.details_redacted is True


def test_event_without_target_and_with_forbidden_policy_is_not_redacted():
    item = _one(audit_row(
        event_type="admin_user_create_failed", entity_type=None, entity_id=None,
        outcome="failure", failure_code="internal_error",
    ))
    assert item.target is None
    assert item.details_redacted is False


def test_foreign_entity_type_for_the_event_is_dropped():
    item = _one(audit_row(event_type="admin_role_add", entity_type="article",
                          entity_id=77))
    assert item.target is None
    assert item.details_redacted is True


@pytest.mark.parametrize("entity_id", [0, -1, None])
def test_non_positive_entity_id_is_dropped(entity_id):
    item = _one(audit_row(event_type="admin_role_add", entity_type="user",
                          entity_id=entity_id))
    assert item.target is None
    assert item.details_redacted is True


# ── Actor ─────────────────────────────────────────────────────────────────────

def test_user_actor_reports_current_account_state():
    item = _one(audit_row(actor_id=42, actor_role="admin", actor_found=True))
    assert item.actor.kind == pol.KIND_USER
    assert item.actor.user_uuid == ACTOR_UUID
    assert item.actor.display_name_current == ACTOR_NAME
    assert item.actor.role_at_event == "admin"
    assert item.actor.is_deleted_current is False


def test_soft_deleted_actor_stays_a_user():
    deleted_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    item = _one(audit_row(actor_deleted_at=deleted_at))
    assert item.actor.kind == pol.KIND_USER
    assert item.actor.is_deleted_current is True


def test_actor_email_is_masked_and_never_full():
    item = _one(audit_row())
    assert item.actor.email_masked == "s***@example.test"
    assert ACTOR_EMAIL not in item.model_dump_json()


def test_missing_account_yields_unavailable_without_identity():
    item = _one(audit_row(actor_found=False))
    assert item.actor.kind == pol.KIND_UNAVAILABLE
    assert item.actor.user_uuid is None
    assert item.actor.display_name_current is None
    assert item.actor.email_masked is None
    assert item.actor.role_at_event is None
    assert item.details_redacted is True


def test_role_outside_allowlist_hides_identity_and_role():
    item = _one(audit_row(event_type="admin_role_add", actor_role="student"))
    assert item.actor.kind == pol.KIND_UNAVAILABLE
    assert item.actor.role_at_event is None
    assert item.actor.user_uuid is None
    assert item.details_redacted is True


def test_nulled_actor_on_a_user_required_event_is_redacted():
    """`admin_role_add` объявлен USER_REQUIRED, значит actor обязан быть.
    NULL здесь — след `ON DELETE SET NULL` после физического удаления аккаунта,
    то есть потеря сведений, и строка должна нести признак редактирования."""
    item = _one(audit_row(
        event_type="admin_role_add", actor_id=None, actor_role="admin",
        actor_found=False, target_found=True,
    ))
    assert item.actor.kind == pol.KIND_UNAVAILABLE
    assert item.actor.user_uuid is None
    assert item.details_redacted is True


def test_anonymous_actor_is_not_treated_as_redacted():
    """Контраст к предыдущему: для ANONYMOUS_ONLY-события отсутствие актора —
    штатное, полностью определённое состояние, а не потеря сведений."""
    actor, failure_code, redacted = _one_auth(auth_row(
        event="failed_login", actor_id=None, success=False,
        failure_reason="invalid_credentials", actor_found=False,
    ))
    assert actor.kind == pol.KIND_ANONYMOUS
    assert redacted is False


def test_system_actor_is_recognised():
    item = _one(audit_row(
        event_type="group_session_completed", actor_id=None, actor_role="system",
        entity_type="group_session", entity_id=9, actor_found=False,
    ))
    assert item.actor.kind == pol.KIND_SYSTEM
    assert item.actor.user_uuid is None
    assert item.actor.role_at_event is None
    assert item.details_redacted is False


# ── auth_log ──────────────────────────────────────────────────────────────────

def test_auth_anonymous_actor_for_failed_login():
    actor, failure_code, redacted = _one_auth(auth_row(
        event="failed_login", actor_id=None, success=False,
        failure_reason="invalid_credentials", actor_found=False,
    ))
    assert actor.kind == pol.KIND_ANONYMOUS
    assert failure_code == "invalid_credentials"
    assert redacted is False


def test_auth_free_text_failure_reason_is_dropped():
    """`auth_log.failure_reason` — VARCHAR(255); в legacy-строках там мог
    оказаться свободный текст, и наружу он идти не должен."""
    secret = "Traceback: password=hunter2 at /srv/app.py:1"
    actor, failure_code, redacted = _one_auth(auth_row(
        event="failed_login", actor_id=None, success=False,
        failure_reason=secret, actor_found=False,
    ))
    assert failure_code is None
    assert redacted is True


def test_auth_never_reports_role_at_event():
    actor, _, _ = _one_auth(auth_row(event="login", actor_id=42))
    assert actor.kind == pol.KIND_USER
    assert actor.role_at_event is None


def test_auth_success_with_a_failure_reason_is_redacted():
    _, failure_code, redacted = _one_auth(auth_row(
        event="login", success=True, failure_reason="invalid_credentials",
    ))
    assert failure_code is None
    assert redacted is True


def test_auth_unknown_event_is_redacted():
    _, failure_code, redacted = _one_auth(auth_row(event="legacy_auth_thing"))
    assert failure_code is None
    assert redacted is True


# ── data_change_log ───────────────────────────────────────────────────────────

def test_known_table_keeps_only_allowlisted_field_names():
    item = svc._project_data_change_row(dcl_row(
        table_name="meeting_types",
        changed_fields=["duration_minutes", "buffer_minutes"],
    ))
    assert item.known_change is True
    assert item.table_name == "meeting_types"
    assert item.changed_fields == ["buffer_minutes", "duration_minutes"]
    assert item.record_id == 15
    assert item.details_redacted is False


def test_field_outside_the_table_allowlist_is_dropped():
    item = svc._project_data_change_row(dcl_row(
        table_name="meeting_types",
        changed_fields=["duration_minutes", "password_hash", "secret_notes"],
    ))
    assert item.changed_fields == ["duration_minutes"]
    assert item.details_redacted is True


@pytest.mark.parametrize("changed_fields", [[123, "duration_minutes"], [None], []])
def test_non_string_or_empty_changed_fields_are_handled(changed_fields):
    item = svc._project_data_change_row(dcl_row(
        table_name="meeting_types", changed_fields=changed_fields,
    ))
    assert all(isinstance(f, str) for f in item.changed_fields)


def test_unknown_table_is_fully_redacted():
    item = svc._project_data_change_row(dcl_row(
        table_name="session_notes", record_id=5, changed_fields=["content"],
    ))
    assert item.known_change is False
    assert item.table_name is None
    assert item.record_id is None
    assert item.operation is None
    assert item.changed_fields == []
    assert item.target_user is None
    assert item.details_redacted is True


def test_operation_outside_table_contract_is_dropped_not_displayed():
    """Все четыре TableSpec допускают только UPDATE. Legacy-строка с INSERT не
    должна показывать литерал: иначе фильтр (422 на INSERT) и проекция
    разошлись бы."""
    item = svc._project_data_change_row(dcl_row(
        table_name="meeting_types", operation="INSERT",
    ))
    assert item.operation is None
    assert item.details_redacted is True


def test_users_table_hides_internal_id_and_exposes_uuid():
    item = svc._project_data_change_row(dcl_row(
        table_name="users", record_id=77, changed_fields=["full_name"],
        target_found=True,
    ))
    assert item.table_name == "users"
    assert item.record_id is None                  # users.id наружу не идёт
    assert item.target_user.user_uuid == TARGET_UUID
    assert item.target_user.email_masked == "s***@example.test"
    assert TARGET_EMAIL not in item.model_dump_json()
    assert "77" not in item.model_dump_json()


def test_users_row_without_an_account_is_redacted():
    item = svc._project_data_change_row(dcl_row(
        table_name="users", record_id=77, changed_fields=["full_name"],
        target_found=False,
    ))
    assert item.record_id is None
    assert item.target_user is None
    assert item.details_redacted is True
