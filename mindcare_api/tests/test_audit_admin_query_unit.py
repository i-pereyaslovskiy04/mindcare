"""
Stage 8 — контракт запроса read-only admin viewer журналов (без БД).

Проверяется, что нарушение контракта отвергается ДО обращения к журналам:
storage-функции подменены и должны остаться невызванными, а access-событие —
незаписанным. Это и есть требование «invalid query не создаёт success event».
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.audit import admin_service as svc
from app.audit.change_contracts import PG_INT32_MAX


# ── Инфраструктура: storage и facade не должны вызываться на невалидном входе ─

class _Recorder:
    def __init__(self):
        self.storage_calls = 0
        self.audit_calls = []

    def storage(self, **kwargs):
        self.storage_calls += 1
        return [], 0

    def record_event(self, **kwargs):
        self.audit_calls.append(kwargs)


@pytest.fixture
def spy(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(svc.storage, "list_audit_events", rec.storage)
    monkeypatch.setattr(svc.storage, "list_auth_events", rec.storage)
    monkeypatch.setattr(svc.storage, "list_data_changes", rec.storage)
    monkeypatch.setattr(svc, "record_event", rec.record_event)
    return rec


def _events(**kwargs):
    base = dict(
        actor_id=1, actor_role="admin", ip=None, user_agent=None,
        session_id_hash=None,
    )
    base.update(kwargs)
    return svc.list_audit_events(**base)


def _changes(**kwargs):
    base = dict(
        actor_id=1, actor_role="admin", ip=None, user_agent=None,
        session_id_hash=None,
    )
    base.update(kwargs)
    return svc.list_data_changes(**base)


def _auth(**kwargs):
    base = dict(
        actor_id=1, actor_role="admin", ip=None, user_agent=None,
        session_id_hash=None,
    )
    base.update(kwargs)
    return svc.list_auth_events(**base)


# ── Окно дат ──────────────────────────────────────────────────────────────────

def test_default_window_is_seven_calendar_days_including_today():
    start, end = svc.resolve_window(None, None)

    today = datetime.now(svc.MOSCOW_TZ).date()
    assert start.date() == today - timedelta(days=6)
    assert end.date() == today + timedelta(days=1)
    # Полуинтервал: обе границы — полночь по Москве.
    assert (start.hour, start.minute, start.second) == (0, 0, 0)
    assert (end.hour, end.minute, end.second) == (0, 0, 0)
    assert start.utcoffset() == timedelta(hours=3)
    assert end.utcoffset() == timedelta(hours=3)
    assert (end - start) == timedelta(days=7)


@pytest.mark.parametrize("date_from,date_to", [
    (date(2026, 8, 1), None),
    (None, date(2026, 8, 1)),
])
def test_single_date_boundary_is_rejected(date_from, date_to):
    with pytest.raises(svc.AuditQueryError):
        svc.resolve_window(date_from, date_to)


def test_reversed_range_is_rejected():
    with pytest.raises(svc.AuditQueryError):
        svc.resolve_window(date(2026, 8, 10), date(2026, 8, 1))


def test_exactly_ninety_days_is_accepted():
    date_from = date(2026, 5, 1)
    date_to = date_from + timedelta(days=89)     # включительно = 90 дней
    start, end = svc.resolve_window(date_from, date_to)
    assert (end - start) == timedelta(days=90)


def test_ninety_one_days_is_rejected():
    date_from = date(2026, 5, 1)
    with pytest.raises(svc.AuditQueryError):
        svc.resolve_window(date_from, date_from + timedelta(days=90))


def test_same_day_range_is_one_day_window():
    start, end = svc.resolve_window(date(2026, 8, 5), date(2026, 8, 5))
    assert (end - start) == timedelta(days=1)


# ── Пагинация ─────────────────────────────────────────────────────────────────

def test_size_above_maximum_is_rejected():
    with pytest.raises(svc.AuditQueryError):
        svc.validate_paging(1, svc.MAX_PAGE_SIZE + 1)


@pytest.mark.parametrize("page,size", [(0, 20), (-1, 20)])
def test_non_positive_page_is_rejected(page, size):
    with pytest.raises(svc.AuditQueryError):
        svc.validate_paging(page, size)


def test_result_window_boundary_is_accepted():
    size = svc.MAX_PAGE_SIZE
    last_page = svc.MAX_RESULT_WINDOW // size
    svc.validate_paging(last_page, size)          # ровно на границе — можно


def test_deep_paging_beyond_result_window_is_rejected():
    size = svc.MAX_PAGE_SIZE
    with pytest.raises(svc.AuditQueryError):
        svc.validate_paging(svc.MAX_RESULT_WINDOW // size + 1, size)


# ── Enum-фильтры валидируются по живым registry ───────────────────────────────

@pytest.mark.parametrize("kwargs", [
    {"order": "sideways"},
    {"actor_kind": "robot"},
    {"filter_actor_role": "root"},
    {"event_type": "no_such_event"},
    {"event_type": "login"},            # AUTH_LOG-событие в audit-ленте
    {"event_type": "legacy_unknown_event"},   # выходной код, не значение фильтра
    {"outcome": "maybe"},
    {"entity_type": "no_such_entity"},
])
def test_invalid_event_filters_are_rejected_before_any_read(spy, kwargs):
    with pytest.raises(svc.AuditQueryError):
        _events(**kwargs)
    assert spy.storage_calls == 0
    assert spy.audit_calls == []


@pytest.mark.parametrize("kwargs", [
    {"actor_kind": "anonymous"},        # недостижим для data_change_log
    {"actor_kind": "system"},           # все TableSpec сейчас USER_REQUIRED
    {"table_name": "session_notes"},    # не входит в CHANGE_REGISTRY
    {"operation": "INSERT"},            # union allowed_operations = {UPDATE}
    {"operation": "DELETE"},
    {"operation": "TRUNCATE"},
])
def test_invalid_data_change_filters_are_rejected(spy, kwargs):
    with pytest.raises(svc.AuditQueryError):
        _changes(**kwargs)
    assert spy.storage_calls == 0
    assert spy.audit_calls == []


def test_update_operation_is_accepted(spy):
    _changes(operation="UPDATE")
    assert spy.storage_calls == 1


@pytest.mark.parametrize("kwargs", [
    {"event": "no_such_event"},
    {"event": "admin_role_add"},        # AUDIT_LOG-событие в auth-ленте
    {"actor_kind": "system"},           # auth_log SYSTEM-событий не имеет
])
def test_invalid_auth_filters_are_rejected(spy, kwargs):
    with pytest.raises(svc.AuditQueryError):
        _auth(**kwargs)
    assert spy.storage_calls == 0
    assert spy.audit_calls == []


def test_auth_accepts_its_own_actor_kinds(spy):
    _auth(actor_kind="anonymous")
    assert spy.storage_calls == 1


# ── Границы точечных идентификаторов ──────────────────────────────────────────

@pytest.mark.parametrize("value", [0, -1, PG_INT32_MAX + 1, 2 ** 63])
def test_entity_id_outside_integer_range_is_rejected(spy, value):
    # entity_type задан явно, чтобы проверялась именно граница диапазона.
    with pytest.raises(svc.AuditQueryError):
        _events(entity_id=value, entity_type="appointment")
    assert spy.storage_calls == 0


@pytest.mark.parametrize("value", [0, -1, PG_INT32_MAX + 1])
def test_record_id_outside_integer_range_is_rejected(spy, value):
    with pytest.raises(svc.AuditQueryError):
        _changes(record_id=value, table_name="meeting_types")
    assert spy.storage_calls == 0


@pytest.mark.parametrize("value", [1, PG_INT32_MAX])
def test_record_ref_boundaries_are_accepted(spy, value):
    _events(entity_id=value, entity_type="appointment")
    assert spy.storage_calls == 1


# ── Целочисленный идентификатор требует явного типа цели ─────────────────────
#
# Без типа цели integer-идентификатор неоднозначен: он сопоставляется в том
# числе с пользовательскими строками, а значит превращает внутренний `users.id`
# в рабочий ключ поиска — перебором можно получить UUID и текущее ФИО из
# безопасной сводки цели.

def test_entity_id_without_entity_type_is_rejected(spy):
    with pytest.raises(svc.AuditQueryError):
        _events(entity_id=42)
    assert spy.storage_calls == 0
    assert spy.audit_calls == []


def test_record_id_without_table_name_is_rejected(spy):
    with pytest.raises(svc.AuditQueryError):
        _changes(record_id=42)
    assert spy.storage_calls == 0
    assert spy.audit_calls == []


@pytest.mark.parametrize("entity_type", [
    "appointment", "meeting_type", "group_session", "session_note",
])
def test_entity_id_with_non_user_entity_type_is_allowed(spy, entity_type):
    _events(entity_id=42, entity_type=entity_type)
    assert spy.storage_calls == 1


@pytest.mark.parametrize("table_name", [
    "meeting_types", "group_sessions", "unregistered_student_cards",
])
def test_record_id_with_non_users_table_is_allowed(spy, table_name):
    _changes(record_id=42, table_name=table_name)
    assert spy.storage_calls == 1


def test_entity_type_alone_stays_allowed(spy):
    """Сам по себе тип цели ограничением не является — запрещена только
    неоднозначная пара «integer без типа»."""
    _events(entity_type="user")
    _changes(table_name="users")
    assert spy.storage_calls == 2


# ── Внутренний users.id не является публичным идентификатором ────────────────

_UUID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize("kwargs", [
    {"entity_type": "user", "entity_id": 5},
    {"target_user_uuid": _UUID, "entity_id": 5},
    {"target_user_uuid": _UUID, "entity_type": "appointment"},
])
def test_events_reject_internal_user_id_targeting(spy, kwargs):
    with pytest.raises(svc.AuditQueryError):
        _events(**kwargs)
    assert spy.storage_calls == 0
    assert spy.audit_calls == []


@pytest.mark.parametrize("kwargs", [
    {"table_name": "users", "record_id": 5},
    {"target_user_uuid": _UUID, "record_id": 5},
    {"target_user_uuid": _UUID, "table_name": "meeting_types"},
])
def test_data_changes_reject_internal_user_id_targeting(spy, kwargs):
    with pytest.raises(svc.AuditQueryError):
        _changes(**kwargs)
    assert spy.storage_calls == 0
    assert spy.audit_calls == []


def test_user_target_via_uuid_is_allowed(spy):
    _events(target_user_uuid=_UUID, entity_type="user")
    _changes(target_user_uuid=_UUID, table_name="users")
    assert spy.storage_calls == 2


# ── Валидный запрос всё-таки доходит до чтения и пишет ровно одно событие ─────

def test_valid_request_reads_once_and_records_one_access_event(spy):
    page = _events()
    assert (page.total, page.page, page.size) == (0, 1, svc.DEFAULT_PAGE_SIZE)
    assert spy.storage_calls == 1
    assert len(spy.audit_calls) == 1
    assert spy.audit_calls[0]["event"] == "audit_logs_viewed"
