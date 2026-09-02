"""
Stage 8 — справочник фильтров выводится из ЖИВЫХ registry, а не из констант.

Важнейший практический случай: все четыре текущих `TableSpec` допускают только
`UPDATE`, поэтому `/options` обязан отдавать `["UPDATE"]`, а не три литерала
`Operation`. Аналогично `system` не должен предлагаться как `actor_kind` для
`data_change_log`, пока ни одна таблица не объявлена `ActorPolicy.SYSTEM`.
"""
from __future__ import annotations

from types import MappingProxyType

import pytest

from app.audit import admin_policy as pol
from app.audit import admin_service as svc
from app.audit.change_contracts import ChangeFieldSpec, Operation, TableSpec, ValuePolicy
from app.audit.contracts import ActorPolicy, Destination
from app.audit.registry import REGISTRY


@pytest.fixture
def options():
    return svc.build_options()


# ── Операции ──────────────────────────────────────────────────────────────────

def test_operations_are_the_union_of_real_allowed_operations(options):
    from app.audit.change_registry import CHANGE_REGISTRY

    expected = sorted({
        op.value for spec in CHANGE_REGISTRY.values()
        for op in spec.allowed_operations
    })
    assert options.operations == expected


def test_operations_today_are_update_only(options):
    assert options.operations == ["UPDATE"]


def test_operations_are_not_hardcoded_to_the_operation_enum(monkeypatch, options):
    """Если завтра появится TableSpec с INSERT, справочник обязан измениться сам."""
    monkeypatch.setattr(pol, "CHANGE_OPERATIONS", frozenset({"UPDATE", "INSERT"}))
    assert svc.build_options().operations == ["INSERT", "UPDATE"]


# ── Классы актора по журналам ─────────────────────────────────────────────────

def test_actor_kinds_cover_exactly_the_three_journals(options):
    assert set(options.actor_kinds) == set(pol.JOURNALS)


def test_data_change_log_does_not_offer_system_today(options):
    assert options.actor_kinds["data_change_log"] == ["user", "unavailable"]


def test_audit_log_offers_system_because_maintenance_jobs_write_it(options):
    assert options.actor_kinds["audit_log"] == ["user", "system", "unavailable"]


def test_auth_log_offers_anonymous_but_not_system(options):
    assert options.actor_kinds["auth_log"] == ["user", "anonymous", "unavailable"]


def _table_spec(*, actor_policy, roles, operations):
    return TableSpec(
        table="synthetic_table",
        entity_type="synthetic_entity",
        paired_event="meeting_type_updated",
        allowed_operations=frozenset(operations),
        actor_policy=actor_policy,
        allowed_actor_roles=frozenset(roles),
        fields=MappingProxyType({
            "flag": ChangeFieldSpec(
                policy=ValuePolicy.BOOL, justification="синтетическое поле",
            ),
        }),
    )


def test_system_kind_appears_when_a_table_declares_a_system_actor():
    """Набор классов — производная от политики, а не список в коде."""
    specs = {"synthetic_table": _table_spec(
        actor_policy=ActorPolicy.SYSTEM, roles=frozenset(),
        operations={Operation.INSERT},
    )}
    policy = pol._build_policy("synthetic", specs, role_aware=True)
    assert policy.kinds == (pol.KIND_SYSTEM, pol.KIND_UNAVAILABLE)


def test_user_kind_appears_for_a_user_required_table():
    specs = {"synthetic_table": _table_spec(
        actor_policy=ActorPolicy.USER_REQUIRED, roles={"admin"},
        operations={Operation.UPDATE},
    )}
    policy = pol._build_policy("synthetic", specs, role_aware=True)
    assert policy.kinds == (pol.KIND_USER, pol.KIND_UNAVAILABLE)


def test_unavailable_is_always_producible():
    specs = {"synthetic_table": _table_spec(
        actor_policy=ActorPolicy.USER_REQUIRED, roles={"admin"},
        operations={Operation.UPDATE},
    )}
    policy = pol._build_policy("synthetic", specs, role_aware=True)
    assert pol.KIND_UNAVAILABLE in policy.kinds


# ── Событийные группы ─────────────────────────────────────────────────────────

def test_event_groups_match_the_registry_partition(options):
    audit = {n for n, s in REGISTRY.items() if s.destination is Destination.AUDIT_LOG}
    auth = {n for n, s in REGISTRY.items() if s.destination is Destination.AUTH_LOG}

    assert options.audit_events == sorted(audit)
    assert options.auth_events == sorted(auth)
    assert len(options.audit_events) == 103
    assert len(options.auth_events) == 7


def test_access_event_is_offered_as_a_filter_value(options):
    assert "audit_logs_viewed" in options.audit_events


def test_legacy_code_is_not_a_filter_value(options):
    """`legacy_unknown_event` — выходной код проекции, а не имя события."""
    assert pol.LEGACY_EVENT_CODE not in options.audit_events
    assert pol.LEGACY_EVENT_CODE not in options.auth_events


def test_entity_types_come_from_target_required_specs(options):
    assert "user" in options.entity_types
    assert set(options.entity_types) == set(pol.EVENTS_BY_ENTITY_TYPE)


def test_tables_come_from_change_registry(options):
    assert options.tables == [
        "group_sessions", "meeting_types", "unregistered_student_cards", "users",
    ]


def test_roles_and_outcomes(options):
    assert options.actor_roles == ["admin", "psychologist", "student", "supervisor"]
    assert options.outcomes == ["success", "failure"]


# ── Лимиты ────────────────────────────────────────────────────────────────────

def test_limits_expose_every_boundary_the_client_needs(options):
    limits = options.limits
    assert limits.default_range_days == svc.DEFAULT_RANGE_DAYS == 7
    assert limits.max_range_days == svc.MAX_RANGE_DAYS == 90
    assert limits.default_page_size == svc.DEFAULT_PAGE_SIZE == 20
    assert limits.max_page_size == svc.MAX_PAGE_SIZE == 100
    assert limits.max_result_window == svc.MAX_RESULT_WINDOW
    assert limits.orders == ["asc", "desc"]


# ── Что справочник НЕ отдаёт ──────────────────────────────────────────────────

def test_options_expose_no_spec_internals_and_no_log_content(options):
    payload = options.model_dump_json()
    for forbidden in (
        "metadata_schema", "allowed_failure_codes", "tx_mode", "failure_policy",
        "description", "ip_address", "user_agent", "session_id",
        "USER_REQUIRED", "ATOMIC", "INDEPENDENT",
    ):
        assert forbidden not in payload, forbidden


def test_options_field_set_is_closed(options):
    assert set(options.model_dump()) == {
        "audit_events", "auth_events", "actor_roles", "outcomes", "entity_types",
        "tables", "operations", "actor_kinds", "limits",
    }
