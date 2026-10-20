"""
Stage 6-0 — no-DB тесты CHANGE_REGISTRY: состав, immutability, fail-fast
валидация и совместимость paired_event с событийным REGISTRY.

Негативные кейсы строятся на ОТДЕЛЬНЫХ наборах specs и отдельном event-registry:
production CHANGE_REGISTRY/REGISTRY не мутируются.
"""
from types import MappingProxyType

import pytest

from app.audit.contracts import (
    ActorPolicy, Destination, EventSpec, FailurePolicy, Outcome,
    TargetPolicy, TxMode,
)
from app.audit.change_contracts import (
    PG_INT32_MAX, PG_INT32_MIN, ChangeFieldSpec, DataChangeError, Operation,
    TableSpec, ValuePolicy,
)
from app.audit.change_registry import (
    CHANGE_REGISTRY, build_change_registry, get_table_spec, is_value_allowed,
    validate_change_registry,
)
from app.audit.registry import REGISTRY
from app.audit.validation import is_denylisted_key


# ── Точный состав registry ────────────────────────────────────────────────────

_EXPECTED_TABLES = frozenset({
    "users", "unregistered_student_cards", "meeting_types", "group_sessions",
})

_EXPECTED_FIELDS = {
    "users": frozenset({"full_name", "phone"}),
    "unregistered_student_cards": frozenset({
        "full_name", "phone", "email", "birth_date", "comment",
        "primary_concern",
    }),
    "meeting_types": frozenset({
        "name", "description", "duration_minutes", "buffer_minutes",
        "display_order", "allow_in_person", "allow_online", "is_group",
        "is_bookable",
    }),
    "group_sessions": frozenset({
        "title", "description", "starts_at", "ends_at", "format", "capacity",
        "meeting_type_id", "psychologist_id",
    }),
}

_EXPECTED_VALUE_ENABLED = frozenset({
    ("meeting_types", "duration_minutes"),
    ("meeting_types", "buffer_minutes"),
    ("meeting_types", "display_order"),
    ("meeting_types", "allow_in_person"),
    ("meeting_types", "allow_online"),
    ("meeting_types", "is_group"),
    ("meeting_types", "is_bookable"),
    ("group_sessions", "format"),
    ("group_sessions", "capacity"),
    ("group_sessions", "meeting_type_id"),
})

_EXPECTED_PAIRED = {
    "users": ("user", "admin_user_updated"),
    "unregistered_student_cards": (
        "unregistered_student_card", "unregistered_student_card_updated",
    ),
    "meeting_types": ("meeting_type", "meeting_type_updated"),
    "group_sessions": ("group_session", "group_session_updated"),
}


def test_registry_tables_and_counts():
    assert set(CHANGE_REGISTRY) == _EXPECTED_TABLES
    assert len(CHANGE_REGISTRY) == 4
    assert sum(len(s.fields) for s in CHANGE_REGISTRY.values()) == 25


def test_registry_field_sets_are_exact():
    for table, expected in _EXPECTED_FIELDS.items():
        assert set(CHANGE_REGISTRY[table].fields) == expected


def test_value_enabled_set_is_exact():
    actual = {
        (table, fname)
        for table, spec in CHANGE_REGISTRY.items()
        for fname, fs in spec.fields.items()
        if fs.policy is not ValuePolicy.NAME_ONLY
    }
    assert actual == _EXPECTED_VALUE_ENABLED
    assert len(actual) == 10
    name_only = sum(
        1 for spec in CHANGE_REGISTRY.values()
        for fs in spec.fields.values()
        if fs.policy is ValuePolicy.NAME_ONLY
    )
    assert name_only == 15


def test_paired_event_and_entity_type_are_exact():
    for table, (entity_type, event) in _EXPECTED_PAIRED.items():
        spec = CHANGE_REGISTRY[table]
        assert spec.entity_type == entity_type
        assert spec.paired_event == event


def test_only_update_operation_in_stage_6():
    for spec in CHANGE_REGISTRY.values():
        assert spec.allowed_operations == frozenset({Operation.UPDATE})


def test_derived_fields_only_for_cards():
    assert CHANGE_REGISTRY["unregistered_student_cards"].derived_fields == (
        frozenset({"normalized_email"})
    )
    for table in ("users", "meeting_types", "group_sessions"):
        assert CHANGE_REGISTRY[table].derived_fields == frozenset()


def test_transition_fields_are_absent_from_allowlist():
    """Поля с выделенными событиями не могут дублироваться в DCL."""
    assert "is_active" not in CHANGE_REGISTRY["users"].fields
    assert "is_active" not in CHANGE_REGISTRY["meeting_types"].fields
    assert "booking_enabled" not in CHANGE_REGISTRY["group_sessions"].fields
    assert "status" not in CHANGE_REGISTRY["group_sessions"].fields
    # роли и email пользователя редактируются другими путями
    assert "roles" not in CHANGE_REGISTRY["users"].fields
    assert "email" not in CHANGE_REGISTRY["users"].fields


def test_key_minimization_invariant_denylisted_names_stay_name_only():
    for table, spec in CHANGE_REGISTRY.items():
        for fname, fs in spec.fields.items():
            if fs.policy is not ValuePolicy.NAME_ONLY:
                assert not is_denylisted_key(fname), (table, fname)


def test_every_field_has_justification():
    for spec in CHANGE_REGISTRY.values():
        for fs in spec.fields.values():
            assert fs.justification.strip()
            assert len(fs.justification) <= 200


def test_registry_is_immutable():
    assert isinstance(CHANGE_REGISTRY, MappingProxyType)
    with pytest.raises(TypeError):
        CHANGE_REGISTRY["x"] = None                   # type: ignore[index]
    with pytest.raises(TypeError):
        CHANGE_REGISTRY["users"].fields["y"] = None   # type: ignore[index]


def test_get_table_spec_unknown_and_non_string():
    with pytest.raises(DataChangeError):
        get_table_spec("session_notes")
    with pytest.raises(DataChangeError):
        get_table_spec(123)                           # type: ignore[arg-type]


def test_is_value_allowed_helper():
    assert is_value_allowed("group_sessions", "capacity") is True
    assert is_value_allowed("group_sessions", "psychologist_id") is False
    assert is_value_allowed("users", "full_name") is False
    with pytest.raises(DataChangeError):
        is_value_allowed("users", "nope")


# ── Изолированные фикстуры для негативных кейсов ─────────────────────────────
#
# Собственный event-registry: production REGISTRY не трогается.

def _event(
    name="probe_updated",
    destination=Destination.AUDIT_LOG,
    entity_type="probe",
    target_policy=TargetPolicy.REQUIRED,
    outcomes=frozenset({Outcome.SUCCESS}),
    failure_codes=frozenset(),
    tx_mode=TxMode.ATOMIC,
    failure_policy=FailurePolicy.RAISE,
    actor_policy=ActorPolicy.USER_REQUIRED,
    roles=frozenset({"admin"}),
):
    return EventSpec(
        name=name, destination=destination, actor_policy=actor_policy,
        allowed_actor_roles=frozenset(roles), target_policy=target_policy,
        entity_type=entity_type, allowed_outcomes=frozenset(outcomes),
        allowed_failure_codes=frozenset(failure_codes),
        metadata_schema=MappingProxyType({}), tx_mode=tx_mode,
        failure_policy=failure_policy,
    )


def _table(**over):
    base = dict(
        table="probe_table",
        entity_type="probe",
        paired_event="probe_updated",
        allowed_operations=frozenset({Operation.UPDATE}),
        actor_policy=ActorPolicy.USER_REQUIRED,
        allowed_actor_roles=frozenset({"admin"}),
        fields=MappingProxyType({
            "capacity": ChangeFieldSpec(
                policy=ValuePolicy.INT, justification="probe",
                min_value=1, max_value=10,
            ),
        }),
    )
    base.update(over)
    return TableSpec(**base)


def _build(spec, events=None):
    registry = MappingProxyType({e.name: e for e in (events or [_event()])})
    return build_change_registry([spec], event_registry=registry)


def test_isolated_baseline_builds():
    assert set(_build(_table())) == {"probe_table"}


# ── paired_event: негативные кейсы ───────────────────────────────────────────

def test_paired_event_must_exist():
    with pytest.raises(DataChangeError, match="unknown paired_event"):
        _build(_table(paired_event="missing_event"))


def test_paired_event_must_target_audit_log():
    events = [_event(destination=Destination.AUTH_LOG, entity_type=None,
                     target_policy=TargetPolicy.FORBIDDEN)]
    with pytest.raises(DataChangeError, match="must target audit_log"):
        _build(_table(), events)


def test_paired_event_entity_type_must_match():
    with pytest.raises(DataChangeError, match="entity_type mismatch"):
        _build(_table(entity_type="other"), [_event(entity_type="probe")])


def test_paired_event_must_require_target():
    events = [_event(target_policy=TargetPolicy.FORBIDDEN, entity_type=None)]
    with pytest.raises(DataChangeError):
        _build(_table(), events)


def test_paired_event_must_be_success_only():
    events = [_event(outcomes=frozenset({Outcome.SUCCESS, Outcome.FAILURE}),
                     failure_codes=frozenset({"internal_error"}))]
    with pytest.raises(DataChangeError, match="success-only"):
        _build(_table(), events)


def test_paired_event_must_be_atomic_and_fail_closed():
    events = [_event(tx_mode=TxMode.INDEPENDENT,
                     failure_policy=FailurePolicy.SOFT)]
    with pytest.raises(DataChangeError, match="must be ATOMIC"):
        _build(_table(), events)


def test_paired_event_actor_policy_must_match():
    events = [_event(actor_policy=ActorPolicy.SYSTEM, roles=frozenset())]
    with pytest.raises(DataChangeError, match="actor_policy mismatch"):
        _build(_table(), events)


def test_table_roles_must_not_exceed_paired_event_roles():
    events = [_event(roles=frozenset({"admin"}))]
    spec = _table(allowed_actor_roles=frozenset({"admin", "supervisor"}))
    with pytest.raises(DataChangeError, match="must not exceed"):
        _build(spec, events)


def test_table_roles_may_be_narrower_than_paired_event():
    events = [_event(roles=frozenset({"admin", "supervisor"}))]
    built = _build(_table(allowed_actor_roles=frozenset({"admin"})), events)
    assert built["probe_table"].allowed_actor_roles == frozenset({"admin"})


# ── Структурная валидация ────────────────────────────────────────────────────

def test_denylisted_name_cannot_be_value_enabled():
    spec = _table(fields=MappingProxyType({
        "email": ChangeFieldSpec(
            policy=ValuePolicy.ENUM, justification="probe",
            allowed=frozenset({"a"}),
        ),
    }))
    with pytest.raises(DataChangeError, match="must stay NAME_ONLY"):
        _build(spec)


def test_denylisted_name_is_allowed_as_name_only():
    spec = _table(fields=MappingProxyType({
        "email": ChangeFieldSpec(policy=ValuePolicy.NAME_ONLY,
                                 justification="ПДн"),
    }))
    assert "email" in _build(spec)["probe_table"].fields


def test_fields_and_derived_fields_must_be_disjoint():
    with pytest.raises(DataChangeError, match="disjoint"):
        _build(_table(derived_fields=frozenset({"capacity"})))


def test_justification_is_required():
    spec = _table(fields=MappingProxyType({
        "capacity": ChangeFieldSpec(policy=ValuePolicy.BOOL,
                                    justification="   "),
    }))
    with pytest.raises(DataChangeError, match="justification is required"):
        _build(spec)


def test_int_bounds_must_fit_postgres_integer():
    spec = _table(fields=MappingProxyType({
        "capacity": ChangeFieldSpec(
            policy=ValuePolicy.INT, justification="probe",
            min_value=PG_INT32_MIN - 1, max_value=PG_INT32_MAX,
        ),
    }))
    with pytest.raises(DataChangeError, match="exceed PostgreSQL INTEGER"):
        _build(spec)


def test_int_requires_min_and_max():
    spec = _table(fields=MappingProxyType({
        "capacity": ChangeFieldSpec(policy=ValuePolicy.INT, justification="p"),
    }))
    with pytest.raises(DataChangeError, match="requires min_value"):
        _build(spec)


def test_enum_requires_non_empty_frozenset():
    spec = _table(fields=MappingProxyType({
        "capacity": ChangeFieldSpec(policy=ValuePolicy.ENUM, justification="p",
                                    allowed=frozenset()),
    }))
    with pytest.raises(DataChangeError, match="non-empty frozenset"):
        _build(spec)


def test_bool_must_not_set_bounds():
    spec = _table(fields=MappingProxyType({
        "capacity": ChangeFieldSpec(policy=ValuePolicy.BOOL, justification="p",
                                    min_value=0),
    }))
    with pytest.raises(DataChangeError, match="must not set allowed/min/max"):
        _build(spec)


def test_anonymous_actor_policy_is_rejected():
    spec = _table(actor_policy=ActorPolicy.ANONYMOUS_ONLY,
                  allowed_actor_roles=frozenset())
    with pytest.raises(DataChangeError, match="unsupported actor_policy"):
        _build(spec)


def test_non_snake_case_names_are_rejected():
    with pytest.raises(DataChangeError, match="stable snake_case"):
        _build(_table(table="Probe-Table"))
    spec = _table(fields=MappingProxyType({
        "Capacity": ChangeFieldSpec(policy=ValuePolicy.NAME_ONLY,
                                    justification="p"),
    }))
    with pytest.raises(DataChangeError, match="stable snake_case"):
        _build(spec)


def test_empty_fields_and_empty_operations_are_rejected():
    with pytest.raises(DataChangeError, match="fields is empty"):
        _build(_table(fields=MappingProxyType({})))
    with pytest.raises(DataChangeError, match="allowed_operations is empty"):
        _build(_table(allowed_operations=frozenset()))


def test_duplicate_table_is_detected_before_dict_creation():
    events = MappingProxyType({e.name: e for e in [_event()]})
    with pytest.raises(DataChangeError, match="duplicate table"):
        build_change_registry([_table(), _table()], event_registry=events)


def test_validate_change_registry_rejects_key_mismatch():
    events = MappingProxyType({e.name: e for e in [_event()]})
    with pytest.raises(DataChangeError, match="!= spec.table"):
        validate_change_registry(MappingProxyType({"wrong_key": _table()}),
                                 event_registry=events)


def test_production_registry_validates_against_production_events():
    validate_change_registry(CHANGE_REGISTRY, event_registry=REGISTRY)


# ── Глубокая immutability build_change_registry ──────────────────────────────
#
# MappingProxyType(d) — live-view поверх ЧУЖОГО d. Если build_change_registry
# не копирует контейнеры, caller, сохранивший ссылку на исходный dict/set/list,
# мог бы изменить allowlist ПОСЛЕ построения registry. Тесты ниже доказывают
# обратное: build() разрывает эту связь для fields/allowed_operations/
# allowed_actor_roles/derived_fields.

def test_build_registry_copies_mutable_fields_dict_post_build_mutation_is_isolated():
    mutable_fields = {
        "capacity": ChangeFieldSpec(
            policy=ValuePolicy.INT, justification="p", min_value=1, max_value=10,
        ),
    }
    built = _build(_table(fields=mutable_fields))

    # Мутация ИСХОДНОГО dict ПОСЛЕ build — не должна быть видна в registry.
    mutable_fields["capacity"] = ChangeFieldSpec(
        policy=ValuePolicy.NAME_ONLY, justification="p",
    )
    mutable_fields["extra_field"] = ChangeFieldSpec(
        policy=ValuePolicy.NAME_ONLY, justification="p",
    )

    assert set(built["probe_table"].fields) == {"capacity"}
    assert built["probe_table"].fields["capacity"].policy is ValuePolicy.INT
    assert built["probe_table"].fields is not mutable_fields


def test_built_registry_fields_mapping_rejects_mutation_with_type_error():
    mutable_fields = {
        "capacity": ChangeFieldSpec(
            policy=ValuePolicy.INT, justification="p", min_value=1, max_value=10,
        ),
    }
    built = _build(_table(fields=mutable_fields))
    with pytest.raises(TypeError):
        built["probe_table"].fields["capacity"] = None    # type: ignore[index]
    with pytest.raises(TypeError):
        built["probe_table"].fields["new_key"] = None     # type: ignore[index]


def test_build_registry_copies_mutable_operations_roles_and_derived():
    mutable_ops = {Operation.UPDATE}
    mutable_roles = {"admin"}
    mutable_derived = ["legacy_field"]
    fields = MappingProxyType({
        "capacity": ChangeFieldSpec(
            policy=ValuePolicy.INT, justification="p", min_value=1, max_value=10,
        ),
    })
    built = _build(_table(
        allowed_operations=mutable_ops,
        allowed_actor_roles=mutable_roles,
        derived_fields=mutable_derived,
        fields=fields,
    ))
    spec = built["probe_table"]
    assert isinstance(spec.allowed_operations, frozenset)
    assert isinstance(spec.allowed_actor_roles, frozenset)
    assert isinstance(spec.derived_fields, frozenset)
    assert spec.allowed_operations == frozenset({Operation.UPDATE})
    assert spec.allowed_actor_roles == frozenset({"admin"})
    assert spec.derived_fields == frozenset({"legacy_field"})

    # Мутация ИСХОДНЫХ set/list ПОСЛЕ build — не должна просочиться в registry.
    mutable_ops.add(Operation.DELETE)
    mutable_roles.add("student")
    mutable_derived.append("other_field")

    assert spec.allowed_operations == frozenset({Operation.UPDATE})
    assert spec.allowed_actor_roles == frozenset({"admin"})
    assert spec.derived_fields == frozenset({"legacy_field"})
    # И сами контейнеры теперь frozenset — попытка мутировать их падает.
    with pytest.raises(AttributeError):
        spec.allowed_operations.add(Operation.INSERT)   # type: ignore[attr-defined]


def test_production_registry_fields_are_not_shared_between_tables():
    """Каждый TableSpec после build несёт СОБСТВЕННЫЙ dict под MappingProxyType,
    а не общий объект — регрессия на возможную ошибку копирования."""
    proxies = [spec.fields for spec in CHANGE_REGISTRY.values()]
    ids = {id(p) for p in proxies}
    assert len(ids) == len(proxies)


# ── Bad container types → DataChangeError, не TypeError/AttributeError ───────

@pytest.mark.parametrize("bad_fields", [None, 5, "capacity", object()])
def test_build_registry_rejects_invalid_fields_type(bad_fields):
    with pytest.raises(DataChangeError, match="fields must be a mapping"):
        _build(_table(fields=bad_fields))


@pytest.mark.parametrize("bad_ops", [None, 5, "UPDATE", object()])
def test_build_registry_rejects_invalid_allowed_operations_type(bad_ops):
    with pytest.raises(DataChangeError, match="allowed_operations must be"):
        _build(_table(allowed_operations=bad_ops))


@pytest.mark.parametrize("bad_roles", [None, 5, "admin", object()])
def test_build_registry_rejects_invalid_allowed_actor_roles_type(bad_roles):
    with pytest.raises(DataChangeError, match="allowed_actor_roles must be"):
        _build(_table(allowed_actor_roles=bad_roles))


@pytest.mark.parametrize("bad_derived", [None, 5, "normalized_email", object()])
def test_build_registry_rejects_invalid_derived_fields_type(bad_derived):
    with pytest.raises(DataChangeError, match="derived_fields must be"):
        _build(_table(derived_fields=bad_derived))


def test_bad_container_type_error_messages_do_not_leak_repr():
    """Сообщения фиксированы (имя контейнера), без repr переданного значения —
    как и остальные DataChangeError в проекте."""
    secret_marker = "SECRET_VALUE_MARKER_12345"

    with pytest.raises(DataChangeError) as excinfo:
        _build(_table(fields=secret_marker))
    assert secret_marker not in str(excinfo.value)

    with pytest.raises(DataChangeError) as excinfo:
        _build(_table(allowed_operations=object()))
    assert "object" not in str(excinfo.value)


def test_dict_and_frozenset_field_input_remain_valid_after_normalization():
    """Нормальный путь (frozenset/MappingProxyType, как в production) не
    задет новыми проверками."""
    built = _build(_table(
        allowed_operations=frozenset({Operation.UPDATE}),
        allowed_actor_roles=frozenset({"admin"}),
        derived_fields=frozenset(),
        fields=MappingProxyType({
            "capacity": ChangeFieldSpec(
                policy=ValuePolicy.INT, justification="p",
                min_value=1, max_value=10,
            ),
        }),
    ))
    assert set(built["probe_table"].fields) == {"capacity"}
