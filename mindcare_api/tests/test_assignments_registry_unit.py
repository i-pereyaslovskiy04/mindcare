"""ADR-033 — контракты событий заданий психолога клиенту (без БД)."""
import pytest

from app.audit.contracts import (
    ActorPolicy, Destination, FailurePolicy, Outcome, TargetPolicy, TxMode,
)
from app.audit.registry import REGISTRY


@pytest.mark.parametrize("name, roles", [
    ("assignment_created", {"psychologist"}),
    ("assignment_completed", {"student"}),
    ("assignment_cancelled", {"psychologist"}),
])
def test_transition_events_are_atomic_raise(name, roles):
    spec = REGISTRY[name]
    assert spec.destination is Destination.AUDIT_LOG
    assert spec.actor_policy is ActorPolicy.USER_REQUIRED
    assert spec.allowed_actor_roles == frozenset(roles)
    assert spec.target_policy is TargetPolicy.REQUIRED and spec.entity_type == "assignment"
    assert spec.allowed_outcomes == frozenset({Outcome.SUCCESS})
    assert spec.tx_mode is TxMode.ATOMIC and spec.failure_policy is FailurePolicy.RAISE
    assert not spec.metadata_schema


def test_content_read_is_fail_closed():
    spec = REGISTRY["assignment_content_read"]
    assert spec.allowed_actor_roles == frozenset({"psychologist"})
    assert spec.target_policy is TargetPolicy.REQUIRED and spec.entity_type == "assignment"
    assert spec.allowed_outcomes == frozenset({Outcome.SUCCESS})
    assert spec.tx_mode is TxMode.INDEPENDENT
    assert spec.failure_policy is FailurePolicy.RAISE
    assert not spec.metadata_schema


@pytest.mark.parametrize("name, roles, codes", [
    ("assignment_create_failed", {"psychologist"},
     {"access_denied", "material_unavailable", "invalid_request"}),
    ("assignment_complete_failed", {"student"},
     {"access_denied", "engagement_inactive", "assignment_finalized"}),
    ("assignment_cancel_failed", {"psychologist"},
     {"access_denied", "assignment_finalized"}),
    ("assignment_read_failed", {"psychologist"}, {"access_denied"}),
])
def test_failure_events_contract(name, roles, codes):
    spec = REGISTRY[name]
    assert spec.allowed_actor_roles == frozenset(roles)
    assert spec.target_policy is TargetPolicy.FORBIDDEN and spec.entity_type is None
    assert spec.allowed_outcomes == frozenset({Outcome.FAILURE})
    assert spec.allowed_failure_codes == frozenset(codes)
    assert spec.tx_mode is TxMode.INDEPENDENT and spec.failure_policy is FailurePolicy.SOFT
    assert not spec.metadata_schema


def test_no_admin_or_supervisor_actor_on_assignment_events():
    for name, spec in REGISTRY.items():
        if name.startswith("assignment_"):
            assert not ({"admin", "supervisor"} & spec.allowed_actor_roles), name
