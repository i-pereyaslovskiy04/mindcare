"""
Stage 8 — контракт события `audit_logs_viewed` и его транзакционная граница.

Просмотр журналов — привилегированное массовое чтение чувствительной
service-use metadata, поэтому он сам является аудируемым действием. Событие
пишется ПОСЛЕ успешной выборки (и потому не попадает в собственный ответ) и
fail-closed: не записали факт просмотра — не отдали журнал.
"""
from __future__ import annotations

import inspect

import pytest

from app.audit import admin_policy as pol
from app.audit import admin_service as svc
from app.audit import admin_storage, routes_admin
from app.audit.contracts import (
    ActorPolicy, AuditStorageError, DescriptionPolicy, Destination, FailurePolicy,
    Outcome, StringFormat, TargetPolicy, TxMode,
)
from app.audit.registry import AUDIT_FILTER_KEYS, AUDIT_JOURNALS, REGISTRY

SPEC = REGISTRY["audit_logs_viewed"]


# ── Точная спецификация ───────────────────────────────────────────────────────

def test_event_spec_is_exactly_as_designed():
    assert SPEC.destination is Destination.AUDIT_LOG
    assert SPEC.actor_policy is ActorPolicy.USER_REQUIRED
    assert SPEC.allowed_actor_roles == frozenset({"admin"})
    assert SPEC.target_policy is TargetPolicy.FORBIDDEN
    assert SPEC.entity_type is None
    assert SPEC.allowed_outcomes == frozenset({Outcome.SUCCESS})
    assert SPEC.allowed_failure_codes == frozenset()
    assert SPEC.tx_mode is TxMode.INDEPENDENT
    assert SPEC.failure_policy is FailurePolicy.RAISE
    assert SPEC.description_policy is DescriptionPolicy.NONE
    assert SPEC.static_description is None
    assert SPEC.user_email_allowed is False


def test_metadata_schema_is_two_closed_enums():
    assert set(SPEC.metadata_schema) == {"journal", "filter_keys"}

    journal = SPEC.metadata_schema["journal"]
    assert journal.type == "str" and journal.fmt is StringFormat.ENUM
    assert journal.enum == AUDIT_JOURNALS == frozenset(pol.JOURNALS)

    keys = SPEC.metadata_schema["filter_keys"]
    assert keys.type == "str_list" and keys.fmt is StringFormat.ENUM
    assert keys.enum == AUDIT_FILTER_KEYS


def test_registry_counters_after_the_new_event():
    audit = {n for n, s in REGISTRY.items() if s.destination is Destination.AUDIT_LOG}
    auth = {n for n, s in REGISTRY.items() if s.destination is Destination.AUTH_LOG}
    assert (len(auth), len(audit), len(REGISTRY)) == (7, 87, 94)


# ── Инфраструктура ────────────────────────────────────────────────────────────

class _Spy:
    def __init__(self, rows=None, total=0, fail=None):
        self.rows = rows or []
        self.total = total
        self.fail = fail
        self.order = []
        self.calls = []

    def storage(self, **kwargs):
        self.order.append("read")
        return list(self.rows), self.total

    def record_event(self, **kwargs):
        self.order.append("audit")
        self.calls.append(kwargs)
        if self.fail is not None:
            raise self.fail

    @property
    def meta(self):
        return self.calls[-1]["metadata"]


@pytest.fixture
def spy(monkeypatch):
    s = _Spy()
    monkeypatch.setattr(svc.storage, "list_audit_events", s.storage)
    monkeypatch.setattr(svc.storage, "list_auth_events", s.storage)
    monkeypatch.setattr(svc.storage, "list_data_changes", s.storage)
    monkeypatch.setattr(svc, "record_event", s.record_event)
    return s


_ACTOR = dict(actor_id=7, actor_role="admin", ip="198.51.100.7",
              user_agent="pytest", session_id_hash="a" * 64)


# ── Actor / target / outcome вызова ───────────────────────────────────────────

def test_call_uses_admin_actor_without_target_and_with_success(spy):
    svc.list_audit_events(**_ACTOR)
    call = spy.calls[0]

    assert call["event"] == "audit_logs_viewed"
    assert call["actor"].kind == "user"
    assert call["actor"].user_id == 7
    assert call["actor"].role == "admin"
    assert call["outcome"] is Outcome.SUCCESS
    assert "target" not in call or call["target"] is None
    assert "failure_reason_code" not in call


def test_independent_event_never_receives_a_caller_session(spy):
    """INDEPENDENT-событие обязано открывать свою транзакцию: передача `db`
    сломала бы facade (`independent event must not receive a caller db`)."""
    svc.list_audit_events(**_ACTOR)
    assert "db" not in spy.calls[0]


def test_context_carries_only_sanitised_ip_ua_and_session_hash(spy):
    svc.list_audit_events(**_ACTOR)
    context = spy.calls[0]["context"]
    assert context.ip_address == "198.51.100.7"
    assert context.user_agent == "pytest"
    assert context.session_id_hash == "a" * 64
    assert context.request_path is None and context.request_method is None


def test_malformed_ip_and_user_agent_are_dropped_not_rejected(spy):
    svc.list_audit_events(**{**_ACTOR, "ip": "not-an-ip", "user_agent": "x" * 900})
    context = spy.calls[0]["context"]
    assert context.ip_address is None
    assert context.user_agent is None


# ── metadata: только имена, никаких значений ─────────────────────────────────

@pytest.mark.parametrize("journal,call", [
    ("audit_log", svc.list_audit_events),
    ("auth_log", svc.list_auth_events),
    ("data_change_log", svc.list_data_changes),
])
def test_journal_is_recorded_per_endpoint(spy, journal, call):
    call(**_ACTOR)
    assert spy.meta["journal"] == journal
    assert set(spy.meta) == {"journal", "filter_keys"}


def test_date_range_key_is_present_even_with_default_window(spy):
    """Окно применяется всегда, поэтому «фильтра по периоду не было» не бывает."""
    svc.list_audit_events(**_ACTOR)
    assert spy.meta["filter_keys"] == ["date_range"]


def test_success_false_counts_as_an_applied_filter(spy):
    """Классическая ловушка: проверка по истинности значения потеряла бы самый
    интересный случай — просмотр НЕУДАЧНЫХ входов."""
    svc.list_auth_events(**_ACTOR, success=False)
    assert "success" in spy.meta["filter_keys"]


def test_success_true_also_counts(spy):
    svc.list_auth_events(**_ACTOR, success=True)
    assert "success" in spy.meta["filter_keys"]


def test_success_absent_is_not_recorded(spy):
    svc.list_auth_events(**_ACTOR)
    assert "success" not in spy.meta["filter_keys"]


def test_access_events_key_only_on_explicit_opt_in(spy):
    svc.list_audit_events(**_ACTOR)
    assert "access_events" not in spy.meta["filter_keys"]

    svc.list_audit_events(**_ACTOR, include_access_events=True)
    assert "access_events" in spy.meta["filter_keys"]


def test_every_filter_maps_to_a_stable_key(spy):
    svc.list_audit_events(
        **_ACTOR,
        actor_uuid="11111111-1111-4111-8111-111111111111",
        actor_kind="user",
        filter_actor_role="admin",
        event_type="admin_role_add",
        outcome="success",
        entity_type="appointment",
        entity_id=5,
        include_access_events=True,
    )
    assert spy.meta["filter_keys"] == [
        "access_events", "actor", "actor_kind", "actor_role", "date_range",
        "entity", "event", "outcome", "record",
    ]


def test_data_change_filters_map_to_stable_keys(spy):
    svc.list_data_changes(
        **_ACTOR,
        actor_uuid="11111111-1111-4111-8111-111111111111",
        filter_actor_role="admin",
        table_name="meeting_types",
        operation="UPDATE",
        record_id=3,
    )
    assert spy.meta["filter_keys"] == [
        "actor", "actor_role", "date_range", "operation", "record", "table",
    ]


def test_target_filter_has_its_own_key(spy):
    svc.list_audit_events(
        **_ACTOR, target_user_uuid="11111111-1111-4111-8111-111111111111",
        entity_type="user",
    )
    assert "target" in spy.meta["filter_keys"]


def test_filter_values_are_never_written(spy):
    """Ни дат, ни UUID, ни id, ни номеров страниц — только имена фильтров."""
    from datetime import date

    svc.list_audit_events(
        **_ACTOR, date_from=date(2026, 8, 1), date_to=date(2026, 8, 10),
        actor_uuid="11111111-1111-4111-8111-111111111111",
        event_type="admin_role_add", entity_type="appointment", entity_id=4242,
        page=3, size=50,
    )
    serialised = repr(spy.meta)
    for forbidden in ("2026-08-01", "2026-08-10", "11111111", "admin_role_add",
                      "appointment", "4242", "50"):
        assert forbidden not in serialised, forbidden


def test_recorded_keys_stay_within_the_registered_enum(spy):
    svc.list_audit_events(**_ACTOR, include_access_events=True)
    assert set(spy.meta["filter_keys"]) <= AUDIT_FILTER_KEYS


# ── Порядок и fail-closed ─────────────────────────────────────────────────────

def test_event_is_written_after_the_read(spy):
    """Поэтому событие просмотра физически не может попасть в свой же ответ."""
    svc.list_audit_events(**_ACTOR)
    assert spy.order == ["read", "audit"]


def test_invalid_query_creates_no_success_event(spy):
    from datetime import date

    with pytest.raises(svc.AuditQueryError):
        svc.list_audit_events(**_ACTOR, date_from=date(2026, 8, 10))
    assert spy.order == []
    assert spy.calls == []


def test_audit_storage_failure_suppresses_the_whole_result(monkeypatch):
    """RAISE + INDEPENDENT: страница уже собрана, но наружу не уходит."""
    from tests.audit_admin_rows import audit_row

    spy = _Spy(rows=[audit_row()], total=1, fail=AuditStorageError("sanitised"))
    monkeypatch.setattr(svc.storage, "list_audit_events", spy.storage)
    monkeypatch.setattr(svc, "record_event", spy.record_event)

    with pytest.raises(AuditStorageError):
        svc.list_audit_events(**_ACTOR)
    assert spy.order == ["read", "audit"]


def test_default_feed_excludes_the_access_event(spy):
    captured = {}

    def _storage(**kwargs):
        captured.update(kwargs)
        return [], 0

    spy.storage = _storage
    svc.storage.list_audit_events = _storage
    svc.list_audit_events(**_ACTOR)
    assert captured["exclude_access_events"] is True


def test_explicit_event_filter_reveals_the_access_event(monkeypatch):
    captured = []
    monkeypatch.setattr(svc, "record_event", lambda **kw: None)
    monkeypatch.setattr(
        svc.storage, "list_audit_events",
        lambda **kw: (captured.append(kw), ([], 0))[1],
    )

    svc.list_audit_events(**_ACTOR, event_type="audit_logs_viewed")
    assert captured[0]["exclude_access_events"] is False

    svc.list_audit_events(**_ACTOR, include_access_events=True)
    assert captured[1]["exclude_access_events"] is False


# ── Просмотр не является изменением данных ───────────────────────────────────

@pytest.mark.parametrize("module", [svc, admin_storage, routes_admin, pol])
def test_viewer_never_writes_a_data_change_row(module):
    """`data_change_log` описывает generic UPDATE; чтение к нему отношения не
    имеет, и пятого call site AST-тест бы не простил."""
    source = inspect.getsource(module)
    assert "record_data_change" not in source


def test_viewer_never_constructs_journal_orm_rows_directly():
    for module in (svc, admin_storage, routes_admin):
        source = inspect.getsource(module)
        for forbidden in ("AuditLog(", "AuthLog(", "DataChangeLog("):
            assert forbidden not in source, f"{module.__name__}: {forbidden}"
