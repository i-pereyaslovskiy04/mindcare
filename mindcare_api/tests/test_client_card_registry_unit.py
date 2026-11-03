"""
Карточка клиента у психолога (ADR-016 дополнение 2026-10-29, ADR-035) —
точные контракты событий без БД.
"""
from app.audit.contracts import (
    ActorPolicy, Destination, FailurePolicy, Outcome, TargetPolicy, TxMode,
)
from app.audit.registry import REGISTRY


def _assert_failure(name, roles, codes):
    spec = REGISTRY[name]
    assert spec.destination is Destination.AUDIT_LOG
    assert spec.actor_policy is ActorPolicy.USER_REQUIRED
    assert spec.allowed_actor_roles == frozenset(roles)
    assert spec.target_policy is TargetPolicy.FORBIDDEN and spec.entity_type is None
    assert spec.allowed_outcomes == frozenset({Outcome.FAILURE})
    assert spec.allowed_failure_codes == frozenset(codes)
    assert spec.tx_mode is TxMode.INDEPENDENT and spec.failure_policy is FailurePolicy.SOFT
    assert not spec.metadata_schema


# ── Этап 1: результаты тестов и ответы ───────────────────────────────────────

def test_result_content_read_is_fail_closed():
    spec = REGISTRY["test_result_content_read"]
    assert spec.destination is Destination.AUDIT_LOG
    assert spec.allowed_actor_roles == frozenset({"supervisor", "psychologist"})
    assert spec.target_policy is TargetPolicy.REQUIRED
    assert spec.entity_type == "test_result"
    assert spec.allowed_outcomes == frozenset({Outcome.SUCCESS})
    assert spec.tx_mode is TxMode.INDEPENDENT
    assert spec.failure_policy is FailurePolicy.RAISE
    assert not spec.metadata_schema


def test_result_read_failed_contract():
    _assert_failure("test_result_read_failed", {"psychologist"}, {"access_denied"})


def test_no_admin_actor_on_test_result_reads():
    for name in ("test_result_content_read", "test_result_read_failed"):
        assert "admin" not in REGISTRY[name].allowed_actor_roles


# ── Этап 2: итог встречи ─────────────────────────────────────────────────────

def test_outcome_events_are_atomic_raise():
    for name in ("appointment_completed", "appointment_no_show"):
        spec = REGISTRY[name]
        assert spec.destination is Destination.AUDIT_LOG
        assert spec.actor_policy is ActorPolicy.USER_REQUIRED
        assert spec.allowed_actor_roles == frozenset({"psychologist"})
        assert spec.target_policy is TargetPolicy.REQUIRED
        assert spec.entity_type == "appointment"
        assert spec.allowed_outcomes == frozenset({Outcome.SUCCESS})
        assert spec.tx_mode is TxMode.ATOMIC and spec.failure_policy is FailurePolicy.RAISE
        assert not spec.metadata_schema


def test_outcome_failed_contract():
    _assert_failure(
        "appointment_outcome_failed", {"psychologist"},
        {"access_denied", "invalid_status", "outcome_conflict", "not_ended"},
    )


# ── Этап 3: заметки ──────────────────────────────────────────────────────────

def test_note_failure_contracts():
    _assert_failure("session_note_create_failed", {"psychologist"},
                    {"access_denied", "link_mismatch"})
    _assert_failure("session_note_update_failed", {"psychologist"},
                    {"access_denied", "version_conflict"})


def test_note_success_and_supervisor_read_policy_unchanged():
    for name in ("session_note_created", "session_note_updated"):
        spec = REGISTRY[name]
        assert spec.allowed_actor_roles == frozenset({"psychologist"})
        assert spec.tx_mode is TxMode.ATOMIC and spec.failure_policy is FailurePolicy.RAISE
    read = REGISTRY["session_note_content_read"]
    assert read.allowed_actor_roles == frozenset({"supervisor"})
    assert read.tx_mode is TxMode.INDEPENDENT and read.failure_policy is FailurePolicy.SOFT
