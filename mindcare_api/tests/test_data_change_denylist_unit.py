"""
Stage 6-0 — точечное расширение denylist и его последствия.

Расширение SENSITIVE_TOKENS обслуживает ИМЕНА полей data_change_log: через
registry-инвариант поле с чувствительным именем может быть только NAME_ONLY.
Обязательное условие — не задеть существующий событийный REGISTRY (94 события)
и его metadata-ключи.
"""
import pytest

from app.audit.change_contracts import ValuePolicy
from app.audit.change_registry import CHANGE_REGISTRY
from app.audit.registry import REGISTRY, build_registry, validate_registry
from app.audit.validation import (
    SENSITIVE_KEYS, SENSITIVE_TOKENS, is_denylisted_key,
)

# Токены, добавленные Stage 6-0.
_NEW_TOKENS = frozenset({
    "birth", "birthdate", "comment", "concern", "content", "note", "notes",
    "diagnosis", "answer", "mood", "diary",
})

# Токены, существовавшие до Stage 6-0 — не должны исчезнуть.
_LEGACY_TOKENS = frozenset({
    "email", "phone", "password", "secret", "token", "ciphertext", "plaintext",
    "checksum", "traceback", "ssn", "dob",
})

# Все metadata-ключи production REGISTRY на момент Stage 6-0.
_EXISTING_METADATA_KEYS = frozenset({
    "roles_before", "roles_after", "added", "removed",
    "fields", "file_size", "mime_type", "linked_user_id",
    # Stage 8: metadata события audit_logs_viewed — имя журнала и СТАБИЛЬНЫЕ
    # ИМЕНА применённых фильтров (без единого значения фильтра).
    "journal", "filter_keys",
    # media_uploaded (общая медиатека): класс файла (image/audio/video).
    "file_type",
})


def test_new_tokens_are_present_and_legacy_tokens_survive():
    assert _NEW_TOKENS <= SENSITIVE_TOKENS
    assert _LEGACY_TOKENS <= SENSITIVE_TOKENS


@pytest.mark.parametrize("name", [
    "birth_date", "birthdate", "comment", "admin_comment", "primary_concern",
    "content", "old_content", "note", "notes", "session_note", "diagnosis",
    "free_text_answer", "mood_score", "diary_entry",
])
def test_new_tokens_catch_sensitive_field_names(name):
    assert is_denylisted_key(name) is True


@pytest.mark.parametrize("name", [
    "full_name", "phone", "email", "normalized_email", "password_hash",
    "session_token", "storage_key", "original_filename",
])
def test_pii_names_remain_denylisted(name):
    assert is_denylisted_key(name) is True


# ── Совместимость с существующим событийным registry ────────────────────────

@pytest.mark.parametrize("key", sorted(_EXISTING_METADATA_KEYS))
def test_existing_metadata_keys_are_not_denylisted(key):
    assert is_denylisted_key(key) is False


def test_metadata_keys_of_production_registry_are_exactly_expected():
    actual = {
        key
        for spec in REGISTRY.values()
        for key in spec.metadata_schema
    }
    assert actual == _EXISTING_METADATA_KEYS


def test_production_event_registry_still_validates_after_extension():
    validate_registry(REGISTRY)
    assert len(REGISTRY) == 110


def test_event_registry_can_still_be_rebuilt():
    rebuilt = build_registry(list(REGISTRY.values()))
    assert set(rebuilt) == set(REGISTRY)
    assert len(rebuilt) == 110


# ── Связка denylist ↔ CHANGE_REGISTRY ───────────────────────────────────────

def test_no_value_enabled_field_is_denylisted():
    """Ключевой anti-PII инвариант: значение может нести только поле, чьё имя
    не срабатывает на denylist."""
    for table, spec in CHANGE_REGISTRY.items():
        for fname, fs in spec.fields.items():
            if fs.policy is not ValuePolicy.NAME_ONLY:
                assert not is_denylisted_key(fname), (table, fname)


def test_all_denylisted_change_fields_are_name_only():
    """Обратное направление того же инварианта."""
    denylisted = [
        (table, fname)
        for table, spec in CHANGE_REGISTRY.items()
        for fname in spec.fields
        if is_denylisted_key(fname)
    ]
    assert denylisted, "ожидаются ПДн-поля в allowlist (name-only)"
    for table, fname in denylisted:
        assert CHANGE_REGISTRY[table].fields[fname].policy is ValuePolicy.NAME_ONLY


def test_derived_field_normalized_email_is_denylisted_and_never_logged():
    spec = CHANGE_REGISTRY["unregistered_student_cards"]
    assert is_denylisted_key("normalized_email") is True
    assert "normalized_email" in spec.derived_fields
    assert "normalized_email" not in spec.fields


def test_sensitive_keys_set_is_untouched_by_stage_6():
    assert "full_name" in SENSITIVE_KEYS
    assert "old_content" in SENSITIVE_KEYS
    assert "new_content" in SENSITIVE_KEYS
