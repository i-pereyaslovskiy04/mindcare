"""
Stage 8 — тест на утечку: враждебная legacy-строка не должна проступать в JSON.

Идея: подставить в КАЖДУЮ потенциально опасную колонку заведомо узнаваемый
маркер (пароль, токен, ciphertext, plaintext-контент, SQL, traceback, текст
исключения, полный email, IP, User-Agent, URL, old/new JSONB), спроецировать
строку и рекурсивно обойти сериализованный ответ. Ни одна контрольная строка не
должна встретиться нигде — ни как значение, ни как подстрока.

Все маркеры синтетические. Настоящие ПДн, токены и секреты в фикстурах
запрещены (`AGENTS.md`, раздел Sensitive data).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.audit import admin_policy as pol
from app.audit import admin_service as svc
from tests.audit_admin_rows import OCCURRED_AT

# ── Контрольные маркеры ───────────────────────────────────────────────────────

MARKERS = {
    "password": "hunter2-synthetic-password",
    "session_token": "9f8e7d6c5b4a39281706ffee0011223344556677889900aabbccddeeff001122",
    "ciphertext": "enc:v1:Z0FBQUFBQm1zeW50aGV0aWM9",
    "plaintext_note": "Клиент сообщил о синтетической тревоге перед сессией",
    "sql": "SELECT password_hash FROM users WHERE id = 1; DROP TABLE audit_log;",
    "traceback": 'Traceback (most recent call last): File "app.py", line 1',
    "exception": "IntegrityError: duplicate key value violates unique constraint",
    "full_email": "victim.person@synthetic-domain.test",
    "ip": "203.0.113.199",
    "user_agent": "Mozilla/5.0 (SyntheticLeakProbe) Build/DEADBEEF",
    "url": "/api/admin/users?token=leaked-synthetic-token",
    "otp": "SyntheticOTP-483920",
    # ФИО, спрятанное в колонках, которые наружу выходить не должны
    # (description, old/new JSONB, metadata). Текущее отображаемое имя актора —
    # НЕ маркер: `display_name_current` является публичным полем DTO.
    "hidden_full_name": "Синтетический Пострадавший Пользователь",
}

# Безобидные значения join-колонок: они легитимно попадают в DTO.
BENIGN_NAME = "Актор Из Джойна"
BENIGN_UUID = "44444444-4444-4444-8444-444444444444"


def _walk(payload):
    """Все строковые узлы сериализованного ответа, включая ключи."""
    if isinstance(payload, dict):
        for key, value in payload.items():
            yield str(key)
            yield from _walk(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk(item)
    else:
        yield str(payload)


def _assert_clean(items):
    dumped = [json.loads(item.model_dump_json()) for item in items]
    flat = "  ".join(_walk(dumped))
    raw = json.dumps(dumped, ensure_ascii=False)
    for name, marker in MARKERS.items():
        assert marker not in flat, f"утечка {name} в узлах ответа"
        assert marker not in raw, f"утечка {name} в сериализованном ответе"
    return dumped


# ── Враждебные строки ─────────────────────────────────────────────────────────

def _hostile_audit_row(**overrides):
    """Строка audit_log, у которой отравлено всё, что вообще может быть отравлено.

    Колонки `description` / `ip_address` / `user_agent` / `session_id` /
    `request_url` / `request_method` перечислены здесь намеренно: если однажды
    кто-то добавит их в SELECT, тест это заметит.
    """
    base = dict(
        entry_id=9007199254740993,
        occurred_at=OCCURRED_AT,
        event_type="admin_role_add",
        actor_id=42,
        actor_role="admin",
        entity_type="user",
        entity_id=77,
        outcome="success",
        failure_code=MARKERS["exception"],
        raw_metadata={
            "roles_after": ["admin"],
            "password": MARKERS["password"],
            "note": MARKERS["plaintext_note"],
            "sql": MARKERS["sql"],
        },
        description=MARKERS["hidden_full_name"],
        ip_address=MARKERS["ip"],
        user_agent=MARKERS["user_agent"],
        session_id=MARKERS["session_token"],
        request_url=MARKERS["url"],
        request_method="POST",
        actor_row_id=42,
        actor_user_uuid=BENIGN_UUID,
        actor_full_name=BENIGN_NAME,
        actor_email=MARKERS["full_email"],
        actor_deleted_at=None,
        target_user_uuid=None,
        target_full_name=BENIGN_NAME,
        target_email=MARKERS["full_email"],
        target_deleted_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hostile_dcl_row(**overrides):
    base = dict(
        entry_id=9007199254740995,
        occurred_at=OCCURRED_AT,
        actor_id=42,
        actor_role="admin",
        table_name="users",
        record_id=77,
        operation="UPDATE",
        changed_fields=["full_name", MARKERS["password"], MARKERS["sql"]],
        old_values={"full_name": MARKERS["hidden_full_name"],
                    "email": MARKERS["full_email"]},
        new_values={"full_name": MARKERS["plaintext_note"]},
        ip_address=MARKERS["ip"],
        actor_row_id=42,
        actor_user_uuid=BENIGN_UUID,
        actor_full_name=BENIGN_NAME,
        actor_email=MARKERS["full_email"],
        actor_deleted_at=None,
        target_user_uuid=None,
        target_full_name=BENIGN_NAME,
        target_email=MARKERS["full_email"],
        target_deleted_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _hostile_auth_row(**overrides):
    base = dict(
        entry_id=9007199254740994,
        occurred_at=OCCURRED_AT,
        event="failed_login",
        actor_id=None,
        event_email=MARKERS["full_email"],
        success=False,
        failure_reason=MARKERS["traceback"],
        ip_address=MARKERS["ip"],
        user_agent=MARKERS["user_agent"],
        session_id=MARKERS["session_token"],
        mfa_method="totp",
        actor_row_id=None,
        actor_user_uuid=None,
        actor_full_name=None,
        actor_email=None,
        actor_deleted_at=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


# ── audit_log ─────────────────────────────────────────────────────────────────

def test_hostile_audit_row_leaks_nothing():
    items = svc._project_audit_rows([_hostile_audit_row()])
    dumped = _assert_clean(items)

    payload = dumped[0]
    assert payload["details"] == {}
    assert payload["details_redacted"] is True
    assert payload["failure_code"] is None


@pytest.mark.parametrize("event_type", [
    "admin_role_add",                 # известное событие
    "legacy_event_from_2019",         # неизвестное
    "login",                          # чужой destination
])
def test_hostile_row_leaks_nothing_for_any_event_class(event_type):
    _assert_clean(svc._project_audit_rows([
        _hostile_audit_row(event_type=event_type),
    ]))


def test_forbidden_columns_are_absent_from_the_dto_field_set():
    """Структурная гарантия: запрещённых полей нет в схеме физически."""
    item = svc._project_audit_rows([_hostile_audit_row()])[0]
    fields = set(item.model_dump())
    for forbidden in (
        "description", "ip_address", "user_agent", "session_id", "request_url",
        "request_method", "log_metadata", "metadata", "raw_metadata",
    ):
        assert forbidden not in fields, forbidden


def test_actor_email_is_masked_even_on_a_hostile_row():
    """Актор разрешён (join нашёл строку `users`), поэтому DTO показывает его
    текущее отображаемое имя и МАСКИРОВАННЫЙ email — но никогда полный."""
    item = svc._project_audit_rows([_hostile_audit_row()])[0]
    assert item.actor.kind == pol.KIND_USER
    assert item.actor.display_name_current == BENIGN_NAME
    assert item.actor.email_masked == "v***@synthetic-domain.test"
    assert MARKERS["full_email"] not in item.model_dump_json()


# ── data_change_log ───────────────────────────────────────────────────────────

def test_hostile_data_change_row_leaks_nothing():
    item = svc._project_data_change_row(_hostile_dcl_row())
    dumped = _assert_clean([item])[0]

    # Имена полей отфильтрованы по allowlist таблицы, значения не копируются.
    assert dumped["changed_fields"] == ["full_name"]
    assert dumped["details_redacted"] is True
    assert dumped["record_id"] is None
    assert "old_values" not in dumped
    assert "new_values" not in dumped


def test_hostile_unknown_table_row_leaks_nothing():
    item = svc._project_data_change_row(_hostile_dcl_row(
        table_name="session_notes", changed_fields=["content", MARKERS["ciphertext"]],
    ))
    dumped = _assert_clean([item])[0]
    assert dumped["table_name"] is None
    assert dumped["changed_fields"] == []


# ── auth_log ──────────────────────────────────────────────────────────────────

def test_hostile_auth_row_masks_email_and_drops_free_text_reason():
    row = _hostile_auth_row()
    spec = pol.auth_spec(row.event)
    actor, _ = svc._project_actor(
        pol.AUTH_POLICY, key=row.event, actor_id=row.actor_id, role=None, row=row,
    )
    failure_code, redacted = svc._project_auth_failure(
        spec, bool(row.success), row.failure_reason,
    )

    from app.audit.admin_schemas import AuthEventOut
    item = AuthEventOut(
        entry_id=str(row.entry_id), occurred_at=row.occurred_at,
        event_code=row.event, known_event=True, actor=actor,
        success=bool(row.success), failure_code=failure_code,
        email_masked=svc.mask_email(row.event_email or ""),
        details_redacted=redacted,
    )
    dumped = _assert_clean([item])[0]

    assert dumped["failure_code"] is None
    assert dumped["details_redacted"] is True
    assert dumped["email_masked"] == "v***@synthetic-domain.test"
    assert "mfa_method" not in dumped


def test_invalid_recorded_email_falls_back_to_stars():
    assert svc.mask_email("") == "***"
    assert svc.mask_email("not-an-email") == "***"
