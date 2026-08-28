"""
Stage 4A — no-DB тесты registry: имена событий, immutability, fail-fast validation.
"""
from types import MappingProxyType

import pytest

from app.audit.contracts import (
    ActorPolicy, AuditError, Destination, EventSpec, FailurePolicy, FieldSpec,
    Outcome, StringFormat, TargetPolicy, TxMode,
)
from app.audit.registry import REGISTRY, build_registry, get_spec, validate_registry


def test_canonical_registration_event_names():
    assert "registration_succeeded" in REGISTRY
    assert "registration_failed" in REGISTRY
    # никаких ошибочных вариантов написания
    for name in REGISTRY:
        assert "registeration" not in name
        assert name not in ("register", "registeration_succeeded",
                            "registeration_failed")


# ── Точный контракт реестра: полное множество имён по destination ─────────────

_EXPECTED_AUTH_LOG_EVENTS = frozenset({
    "registration_succeeded", "registration_failed", "login", "failed_login",
    "logout", "password_change", "password_reset",
})

_EXPECTED_AUDIT_LOG_EVENTS = frozenset({
    "admin_role_add", "admin_role_remove", "admin_role_update",
    "admin_user_created", "admin_user_updated", "admin_user_deleted",
    "admin_user_activated", "admin_user_deactivated", "user_reactivated",
    "profile_updated",
    "supervisor_create_student", "supervisor_assign_psychologist",
    "supervisor_reactivate_psychologist",
    "supervisor_transfer_psychologist", "supervisor_close_engagement",
    "email_domain_add", "email_domain_disable", "email_domain_reactivate",
    "email_domain_update",
    "session_note_created", "session_note_updated", "session_note_content_read",
    "chat_conversation_created", "chat_message_edited", "chat_message_deleted",
    "chat_attachment_uploaded", "chat_attachment_downloaded",
    "system_conversation_created",
    "article_created", "article_updated", "article_deleted",
    "news_created", "news_updated", "news_deleted",
    "tag_created", "tag_updated", "tag_deleted",
    "category_created", "category_updated", "category_deleted",
    "test_created", "test_updated", "test_duplicated", "test_deleted",
    "test_consent_accepted", "test_submitted",
    # Stage 5A-2 durable failure события (INDEPENDENT/SOFT).
    "admin_user_create_failed", "admin_user_update_failed",
    "admin_user_delete_failed", "profile_update_failed",
    # Stage 5B-1 appointments + walk-in cards (success lifecycle).
    "appointment_created", "appointment_confirmed", "appointment_declined",
    "appointment_cancelled",
    "unregistered_student_card_created", "unregistered_student_card_updated",
    "unregistered_student_card_archived", "unregistered_student_card_linked",
    # Stage 5B-2 appointments/cards durable failure (INDEPENDENT/SOFT).
    "appointment_create_failed", "appointment_cancel_failed",
    "appointment_confirm_failed", "appointment_decline_failed",
    "unregistered_student_card_create_failed",
    # Stage 5C-1 meeting types + schedules (success lifecycle).
    "meeting_type_created", "meeting_type_updated",
    "meeting_type_activated", "meeting_type_deactivated",
    "banner_slide_created", "banner_slide_updated",
    "banner_slide_activated", "banner_slide_deactivated",
    "banner_slide_deleted",
    "service_card_created", "service_card_updated",
    "service_card_activated", "service_card_deactivated",
    "service_card_deleted",
    "schedule_created", "schedule_updated", "schedule_deactivated",
    "schedule_restored", "schedule_extended",
    "schedule_rule_created", "schedule_rule_deactivated",
    "schedule_break_created", "schedule_break_deactivated",
    "schedule_exception_created",
    # Stage 5C-2 group sessions + student registrations (success lifecycle).
    "group_session_created", "group_session_updated",
    "group_session_booking_opened", "group_session_booking_closed",
    "group_session_cancelled",
    "group_session_registered", "group_session_registration_cancelled",
    # Stage 5C-3 system maintenance (SYSTEM actor, ATOMIC/RAISE).
    "group_session_completed", "schedule_auto_extended",
    # Stage 8 read-only admin viewer: привилегированное чтение журналов
    # (target FORBIDDEN, success-only, INDEPENDENT + RAISE).
    "audit_logs_viewed",
})


def test_registry_exact_contract():
    assert set(REGISTRY) == _EXPECTED_AUTH_LOG_EVENTS | _EXPECTED_AUDIT_LOG_EVENTS

    auth_names = {n for n, s in REGISTRY.items()
                  if s.destination is Destination.AUTH_LOG}
    audit_names = {n for n, s in REGISTRY.items()
                   if s.destination is Destination.AUDIT_LOG}

    assert auth_names == _EXPECTED_AUTH_LOG_EVENTS
    assert len(auth_names) == 7
    assert audit_names == _EXPECTED_AUDIT_LOG_EVENTS
    assert len(audit_names) == 97
    assert len(REGISTRY) == 104


def test_unknown_event_rejected():
    with pytest.raises(AuditError):
        get_spec("no_such_event")


def test_registry_is_immutable():
    with pytest.raises(TypeError):
        REGISTRY["x"] = None                      # MappingProxyType
    spec = REGISTRY["login"]
    with pytest.raises(Exception):                # FrozenInstanceError
        spec.name = "y"
    with pytest.raises(TypeError):
        spec.metadata_schema["k"] = None          # MappingProxyType


def test_production_registry_valid():
    validate_registry(REGISTRY)                    # fail-fast уже на импорте; повтор


def test_name_length_within_destination_bounds():
    for spec in REGISTRY.values():
        limit = 150 if spec.destination is Destination.AUTH_LOG else 100
        assert 0 < len(spec.name) <= limit


def test_auth_events_have_no_metadata_and_forbidden_target():
    for spec in REGISTRY.values():
        if spec.destination is Destination.AUTH_LOG:
            assert dict(spec.metadata_schema) == {}
            assert spec.target_policy is TargetPolicy.FORBIDDEN


def test_atomic_events_are_raise():
    for spec in REGISTRY.values():
        if spec.tx_mode is TxMode.ATOMIC:
            assert spec.failure_policy is FailurePolicy.RAISE


def test_supervisor_events_allow_supervisor_and_admin():
    # supervisor-операции доступны и supervisor, и admin (routes allow both) —
    # actor_role может быть "admin", поэтому оба должны валидироваться.
    for name in (
        "supervisor_create_student", "supervisor_assign_psychologist",
        "supervisor_reactivate_psychologist", "supervisor_transfer_psychologist",
        "supervisor_close_engagement",
    ):
        assert REGISTRY[name].allowed_actor_roles == frozenset({"supervisor", "admin"})


def test_chat_conversation_created_allows_all_four_roles():
    # supervisor/admin создают беседу через assign/transfer (Stage 4B-3);
    # student/psychologist — через lazy-create. Все 4 роли должны валидироваться.
    assert REGISTRY["chat_conversation_created"].allowed_actor_roles == frozenset(
        {"student", "psychologist", "supervisor", "admin"}
    )


def test_other_chat_events_stay_student_psychologist_only():
    # Негативный тест: остальные chat-события НЕ должны случайно расшириться
    # вместе с chat_conversation_created — их actor всегда student/psychologist.
    for name in (
        "chat_message_edited", "chat_message_deleted",
        "chat_attachment_uploaded", "chat_attachment_downloaded",
    ):
        assert REGISTRY[name].allowed_actor_roles == frozenset(
            {"student", "psychologist"}
        )


def test_registry_total_count_stage_5c3():
    # Stage 8 (read-only admin viewer журналов): 7 auth + 87 audit = 94.
    # 5A-1 +3 lifecycle, 5A-2 +4 failure, 5B-1 +8 (appointments + walk-in card),
    # 5B-2 +5 durable failure, 5C-1 +14 (meeting types + schedules),
    # 5C-2 +7 (group sessions + registrations), 5C-3 +2 (system maintenance).
    # Hero CMS (banner_slides, вне стадийной нумерации): +5
    # (created/updated/activated/deactivated/deleted) → 7 auth + 92 audit = 99.
    # Карточки услуг (service_cards, вне стадийной нумерации): +5
    # (created/updated/activated/deactivated/deleted) → 7 auth + 97 audit = 104.
    assert len(REGISTRY) == 104


def test_role_metadata_enum_excludes_system():
    spec = REGISTRY["admin_role_add"]
    fs = spec.metadata_schema["roles_before"]
    assert "system" not in fs.enum
    assert fs.enum == frozenset({"student", "psychologist", "supervisor", "admin"})


# ── validate_registry отвергает некорректные specs (без изменения production) ──

def _audit_spec(**over) -> EventSpec:
    base = dict(
        name="x_event", destination=Destination.AUDIT_LOG,
        actor_policy=ActorPolicy.USER_REQUIRED,
        allowed_actor_roles=frozenset({"admin"}),
        target_policy=TargetPolicy.REQUIRED, entity_type="user",
        allowed_outcomes=frozenset({Outcome.SUCCESS}),
        allowed_failure_codes=frozenset(),
        metadata_schema=MappingProxyType({}),
        tx_mode=TxMode.ATOMIC, failure_policy=FailurePolicy.RAISE,
    )
    base.update(over)
    return EventSpec(**base)


def _check_invalid(**over):
    spec = _audit_spec(**over)
    with pytest.raises(AuditError):
        validate_registry({spec.name: spec})


def test_reject_atomic_soft():
    _check_invalid(tx_mode=TxMode.ATOMIC, failure_policy=FailurePolicy.SOFT)


def test_reject_system_with_roles():
    _check_invalid(actor_policy=ActorPolicy.SYSTEM,
                   allowed_actor_roles=frozenset({"admin"}))


def test_reject_failure_without_codes():
    _check_invalid(allowed_outcomes=frozenset({Outcome.FAILURE}),
                   allowed_failure_codes=frozenset())


def test_reject_success_with_codes():
    _check_invalid(allowed_outcomes=frozenset({Outcome.SUCCESS}),
                   allowed_failure_codes=frozenset({"boom"}))


def test_reject_user_email_on_audit():
    spec = _audit_spec()
    spec = EventSpec(**{**spec.__dict__, "user_email_allowed": True})
    with pytest.raises(AuditError):
        validate_registry({spec.name: spec})


def test_reject_denylisted_metadata_key():
    _check_invalid(metadata_schema=MappingProxyType(
        {"email": FieldSpec(type="str", fmt=StringFormat.MIME_TYPE)}))


def test_reject_string_field_without_format():
    _check_invalid(metadata_schema=MappingProxyType(
        {"note": FieldSpec(type="str")}))


def test_reject_target_required_without_entity_type():
    _check_invalid(target_policy=TargetPolicy.REQUIRED, entity_type=None)


def test_reject_key_name_mismatch():
    spec = _audit_spec(name="real_name")
    with pytest.raises(AuditError):
        validate_registry({"other_key": spec})


# ── build_registry: дубликат обнаруживается ДО создания dict ──────────────────

def test_duplicate_event_name_detected_before_dict_creation():
    dup1 = _audit_spec(name="dup_event")
    dup2 = _audit_spec(name="dup_event")
    with pytest.raises(AuditError):
        build_registry([dup1, dup2])


def test_build_registry_returns_validated_immutable_mapping():
    spec = _audit_spec(name="fresh_event")
    built = build_registry([spec])
    assert dict(built) == {"fresh_event": spec}
    with pytest.raises(TypeError):
        built["x"] = None


# ── Stable snake_case names / failure codes (пункт 3) ──────────────────────────

@pytest.mark.parametrize("bad_name", [
    "AdminRoleAdd", "admin-role-add", "1admin", "admin role add",
])
def test_reject_unstable_event_name(bad_name):
    spec = _audit_spec(name=bad_name)
    with pytest.raises(AuditError):
        validate_registry({spec.name: spec})


def test_reject_unstable_failure_code():
    _check_invalid(
        allowed_outcomes=frozenset({Outcome.FAILURE}),
        allowed_failure_codes=frozenset({"Not-Snake-Case"}),
    )


# ── FieldSpec type-strictness (пункт 3) ────────────────────────────────────────

def test_reject_invalid_fieldspec_type():
    _check_invalid(metadata_schema=MappingProxyType(
        {"x": FieldSpec(type="float")}))


def test_reject_enum_empty_frozenset():
    _check_invalid(metadata_schema=MappingProxyType(
        {"x": FieldSpec(type="str", fmt=StringFormat.ENUM, enum=frozenset())}))


def test_reject_mime_type_with_enum():
    _check_invalid(metadata_schema=MappingProxyType({
        "x": FieldSpec(type="str", fmt=StringFormat.MIME_TYPE,
                       enum=frozenset({"a"})),
    }))


def test_reject_int_with_string_format_or_enum():
    _check_invalid(metadata_schema=MappingProxyType(
        {"x": FieldSpec(type="int", fmt=StringFormat.ENUM, enum=frozenset({"a"}))}))
    _check_invalid(metadata_schema=MappingProxyType(
        {"x": FieldSpec(type="int", enum=frozenset({"a"}))}))


def test_reject_min_max_on_string_type():
    _check_invalid(metadata_schema=MappingProxyType({
        "x": FieldSpec(type="str", fmt=StringFormat.MIME_TYPE, min_value=0),
    }))


def test_reject_max_len_on_int_type():
    _check_invalid(metadata_schema=MappingProxyType(
        {"x": FieldSpec(type="int", max_len=10)}))


def test_reject_non_positive_max_len():
    _check_invalid(metadata_schema=MappingProxyType({
        "x": FieldSpec(type="str", fmt=StringFormat.MIME_TYPE, max_len=0),
    }))


def test_reject_bool_with_extra_constraints():
    _check_invalid(metadata_schema=MappingProxyType(
        {"x": FieldSpec(type="bool", max_len=5)}))


# ── DescriptionPolicy (пункт 3) ─────────────────────────────────────────────────

def test_reject_none_policy_with_static_description():
    from app.audit.contracts import DescriptionPolicy
    _check_invalid(
        description_policy=DescriptionPolicy.NONE, static_description="oops",
    )


def test_reject_static_policy_without_description():
    from app.audit.contracts import DescriptionPolicy
    _check_invalid(description_policy=DescriptionPolicy.STATIC, static_description=None)


def test_reject_static_description_too_long():
    from app.audit.contracts import DescriptionPolicy
    _check_invalid(
        description_policy=DescriptionPolicy.STATIC,
        static_description="x" * 201,
    )
