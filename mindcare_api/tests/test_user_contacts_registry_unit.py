"""ADR-031 — контракты событий контактов пользователя (без БД)."""
from app.audit.contracts import (
    ActorPolicy, Destination, FailurePolicy, Outcome, TargetPolicy, TxMode,
)
from app.audit.registry import REGISTRY


def test_content_read_contract():
    spec = REGISTRY["user_contacts_content_read"]
    assert spec.destination is Destination.AUDIT_LOG
    assert spec.allowed_actor_roles == frozenset({"psychologist", "supervisor"})
    assert spec.actor_policy is ActorPolicy.USER_REQUIRED
    assert spec.target_policy is TargetPolicy.REQUIRED and spec.entity_type == "user"
    assert spec.allowed_outcomes == frozenset({Outcome.SUCCESS})
    # fail-closed: INDEPENDENT + RAISE, metadata пуста.
    assert spec.tx_mode is TxMode.INDEPENDENT
    assert spec.failure_policy is FailurePolicy.RAISE
    assert not spec.metadata_schema


def test_read_failed_contract():
    spec = REGISTRY["user_contacts_read_failed"]
    assert spec.allowed_actor_roles == frozenset({"psychologist", "supervisor"})
    assert spec.target_policy is TargetPolicy.FORBIDDEN and spec.entity_type is None
    assert spec.allowed_outcomes == frozenset({Outcome.FAILURE})
    assert spec.allowed_failure_codes == frozenset({"access_denied"})
    assert spec.tx_mode is TxMode.INDEPENDENT and spec.failure_policy is FailurePolicy.SOFT
    assert not spec.metadata_schema


def test_profile_update_failed_has_version_conflict_code():
    codes = REGISTRY["profile_update_failed"].allowed_failure_codes
    assert {"user_not_found", "invalid_request", "internal_error",
            "contacts_version_conflict"} == set(codes)
