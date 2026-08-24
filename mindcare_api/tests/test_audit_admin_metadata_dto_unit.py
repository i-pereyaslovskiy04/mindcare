"""
Stage 8 — вторая ступень проекции metadata.

`validation.validate_metadata()` защищает от мусора в БД, но пропускает всё, что
объявил EventSpec, — включая `linked_user_id`, то есть внутренний `users.id`.
Поэтому поверх неё стоит закрытый DTO-allowlist: он преобразует такой ключ в
UUID и отбрасывает всё, для чего решение «отдавать / преобразовать» не принято
явно.
"""
from __future__ import annotations

from types import MappingProxyType
from uuid import UUID

import pytest

from app.audit import admin_service as svc
from app.audit.contracts import (
    ActorPolicy, AuditError, Destination, EventSpec, FailurePolicy, FieldSpec,
    Outcome, TargetPolicy, TxMode,
)
from app.audit.registry import REGISTRY
from tests.audit_admin_rows import audit_row

LINKED_UUID = UUID("33333333-3333-4333-8333-333333333333")


def _project(row, uuid_by_id=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(
            svc.storage, "resolve_user_uuids", lambda ids: dict(uuid_by_id or {}),
        )
    items = svc._project_audit_rows([row])
    return items[0]


def _linked_row(**kwargs):
    return audit_row(
        event_type="unregistered_student_card_linked",
        actor_role="supervisor",
        entity_type="unregistered_student_card",
        entity_id=12,
        **kwargs,
    )


# ── linked_user_id → linked_user_uuid ────────────────────────────────────────

def test_internal_user_id_is_replaced_by_uuid(monkeypatch):
    item = _project(
        _linked_row(raw_metadata={"linked_user_id": 909}),
        uuid_by_id={909: LINKED_UUID},
        monkeypatch=monkeypatch,
    )
    assert item.details == {"linked_user_uuid": str(LINKED_UUID)}
    assert item.details_redacted is False

    payload = item.model_dump_json()
    assert "linked_user_id" not in payload
    assert "909" not in payload


def test_unresolved_internal_id_drops_the_key(monkeypatch):
    """Аккаунт удалён физически — UUID взять неоткуда. Внутренний id при этом
    всё равно не показывается."""
    item = _project(
        _linked_row(raw_metadata={"linked_user_id": 909}),
        uuid_by_id={},
        monkeypatch=monkeypatch,
    )
    assert item.details == {}
    assert item.details_redacted is True
    assert "909" not in item.model_dump_json()


@pytest.mark.parametrize("value", [0, -5, "909", True, None, 3.5])
def test_non_positive_or_wrong_typed_id_is_dropped(monkeypatch, value):
    item = _project(
        _linked_row(raw_metadata={"linked_user_id": value}),
        uuid_by_id={909: LINKED_UUID},
        monkeypatch=monkeypatch,
    )
    assert item.details == {}
    assert item.details_redacted is True


def test_resolution_is_batched_across_the_page(monkeypatch):
    """Один запрос на страницу, а не на строку: иначе получился бы N+1."""
    calls = []

    def _resolve(ids):
        calls.append(sorted(ids))
        return {901: LINKED_UUID, 902: LINKED_UUID}

    monkeypatch.setattr(svc.storage, "resolve_user_uuids", _resolve)
    rows = [
        _linked_row(raw_metadata={"linked_user_id": 901}),
        _linked_row(raw_metadata={"linked_user_id": 902}),
        _linked_row(raw_metadata={"linked_user_id": 901}),
    ]
    items = svc._project_audit_rows(rows)

    assert len(items) == 3
    assert calls == [[901, 902]]


def test_no_resolution_query_when_nothing_is_pending(monkeypatch):
    def _boom(ids):
        raise AssertionError("резолв не должен вызываться без ожидающих ключей")

    monkeypatch.setattr(svc.storage, "resolve_user_uuids", _boom)
    svc._project_audit_rows([audit_row(raw_metadata={})])


# ── Пропускаемые ключи ────────────────────────────────────────────────────────

def test_role_diff_metadata_passes_through():
    item = svc._project_audit_rows([audit_row(
        event_type="admin_role_add",
        target_found=True,
        raw_metadata={"roles_before": ["student"], "roles_after": ["student", "admin"],
                      "added": ["admin"]},
    )])[0]
    assert item.details == {
        "roles_before": ["student"],
        "roles_after": ["student", "admin"],
        "added": ["admin"],
    }
    assert item.details_redacted is False


def test_metadata_failing_revalidation_yields_empty_details():
    """Мусор в колонке не должен ронять страницу и не должен частично утекать."""
    item = svc._project_audit_rows([audit_row(
        event_type="admin_role_add",
        raw_metadata={"roles_after": ["not_a_real_role"], "added": ["admin"]},
    )])[0]
    assert item.details == {}
    assert item.details_redacted is True
    assert "not_a_real_role" not in item.model_dump_json()


@pytest.mark.parametrize("raw", ["a string", 17, ["a", "list"]])
def test_non_mapping_metadata_is_rejected(raw):
    item = svc._project_audit_rows([audit_row(
        event_type="admin_role_add", raw_metadata=raw,
    )])[0]
    assert item.details == {}
    assert item.details_redacted is True


def test_unclassified_key_is_dropped():
    """Ключ, для которого нет DTO-политики, не отдаётся даже если EventSpec его
    объявил бы: политика по умолчанию — fail-closed."""
    spec = REGISTRY["admin_role_add"]
    details, redacted, pending = svc._project_metadata(spec, {"added": ["admin"]})
    assert details == {"added": ["admin"]} and redacted is False

    # Тот же ключ, но политика удалена — эмуляция «завели metadata и забыли DTO».
    trimmed = {k: v for k, v in svc._METADATA_DTO_POLICY.items() if k != "added"}
    original = svc._METADATA_DTO_POLICY
    try:
        svc._METADATA_DTO_POLICY = trimmed
        details, redacted, pending = svc._project_metadata(spec, {"added": ["admin"]})
    finally:
        svc._METADATA_DTO_POLICY = original

    assert details == {}
    assert redacted is True
    assert pending == {}


# ── Полнота политики проверяется на импорте ──────────────────────────────────

def test_production_registry_is_fully_classified():
    svc.validate_metadata_dto_policy()


def test_every_metadata_key_of_every_spec_has_a_policy():
    for spec in REGISTRY.values():
        for key in spec.metadata_schema:
            assert key in svc._METADATA_DTO_POLICY, key


def _spec_with_metadata(metadata):
    return EventSpec(
        name="synthetic_event",
        destination=Destination.AUDIT_LOG,
        actor_policy=ActorPolicy.USER_REQUIRED,
        allowed_actor_roles=frozenset({"admin"}),
        target_policy=TargetPolicy.FORBIDDEN,
        entity_type=None,
        allowed_outcomes=frozenset({Outcome.SUCCESS}),
        allowed_failure_codes=frozenset(),
        metadata_schema=MappingProxyType(metadata),
        tx_mode=TxMode.INDEPENDENT,
        failure_policy=FailurePolicy.RAISE,
    )


def test_new_metadata_key_without_a_policy_fails_fast():
    """Новый ключ в registry обязан ронять старт, а не молча утекать в ответ."""
    spec = _spec_with_metadata({
        "invented_key": FieldSpec(type="int", min_value=0),
    })
    with pytest.raises(AuditError):
        svc.validate_metadata_dto_policy(registry={"synthetic_event": spec})


def test_uuid_mapping_requires_an_id_suffix():
    spec = _spec_with_metadata({
        "subject": FieldSpec(type="int", min_value=1),
    })
    policy = dict(svc._METADATA_DTO_POLICY)
    policy["subject"] = svc.MetaPolicy.USER_ID_TO_UUID
    with pytest.raises(AuditError):
        svc.validate_metadata_dto_policy(
            registry={"synthetic_event": spec}, policy=policy,
        )


def test_access_event_metadata_keys_are_classified():
    """Собственные ключи события просмотра тоже проходят DTO-политику."""
    spec = REGISTRY["audit_logs_viewed"]
    assert set(spec.metadata_schema) == {"journal", "filter_keys"}
    for key in spec.metadata_schema:
        assert svc._METADATA_DTO_POLICY[key] is svc.MetaPolicy.PASS


def test_enum_metadata_of_access_event_survives_round_trip():
    spec = REGISTRY["audit_logs_viewed"]
    details, redacted, pending = svc._project_metadata(
        spec, {"journal": "auth_log", "filter_keys": ["date_range", "success"]},
    )
    assert details == {"journal": "auth_log",
                       "filter_keys": ["date_range", "success"]}
    assert redacted is False and pending == {}


def test_field_spec_enum_is_enforced_on_read():
    spec = REGISTRY["audit_logs_viewed"]
    details, redacted, _ = svc._project_metadata(
        spec, {"journal": "some_other_table"},
    )
    assert details == {} and redacted is True
