"""
Stage 5C-0B — no-DB unit-тесты application writer'ов identity серии.

После 5C-0C на schedule_rules.series_id / schedule_breaks.series_id стоят FK →
schedule_series.series_uuid, поэтому КАЖДЫЙ генератор series_id обязан вставить
identity-строку ДО вставки rules/breaks в той же транзакции. Реальная БД не
используется.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.appointments.storage as st
from app.audit import Actor, RequestContext

# Stage 5C-1: генераторы серий стали audit-writer'ами и требуют actor/context.
SUP_ACTOR = Actor.user(9, "supervisor")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")


def _no_audit(monkeypatch):
    """Заглушить record_event — здесь проверяется порядок identity/child rows,
    а не audit-контракт (он покрыт tests/test_schedule_audit_unit.py)."""
    monkeypatch.setattr(st, "record_event", lambda **kw: None)


def _db_with_no_existing_series():
    """db, у которого lookup identity возвращает None (серия ещё не создана)."""
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def _added_series(db):
    return [
        c.args[0] for c in db.add.call_args_list
        if isinstance(c.args[0], st.ScheduleSeries)
    ]


def _add_order(db):
    """Классы объектов в порядке db.add(...)."""
    return [type(c.args[0]).__name__ for c in db.add.call_args_list]


# ══════════════════════════════════════════════════════════════════════════
# 1. _ensure_series_identity
# ══════════════════════════════════════════════════════════════════════════

def test_ensure_creates_identity_and_flushes():
    db = _db_with_no_existing_series()
    import uuid as _uuid
    sid = _uuid.uuid4()

    row = st._ensure_series_identity(sid, 7, db)

    assert isinstance(row, st.ScheduleSeries)
    assert row.series_uuid == sid and row.psychologist_id == 7
    db.add.assert_called_once()
    db.flush.assert_called_once()      # id доступен сразу после flush


def test_ensure_is_idempotent_reuses_existing_same_owner():
    """update_schedule_series переиспользует существующий series_id — дубль
    identity создавать нельзя (UNIQUE series_uuid)."""
    db = MagicMock(name="db")
    existing = SimpleNamespace(id=42, psychologist_id=7)
    db.query.return_value.filter.return_value.first.return_value = existing
    import uuid as _uuid

    row = st._ensure_series_identity(_uuid.uuid4(), 7, db)

    assert row is existing
    db.add.assert_not_called()
    db.flush.assert_not_called()


def _db_with_existing_owner(owner):
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = (
        SimpleNamespace(id=42, psychologist_id=owner)
    )
    return db


@pytest.mark.parametrize("existing_owner", [9, None], ids=["other", "null"])
def test_ensure_fail_closed_on_owner_mismatch(existing_owner):
    """Чужой владелец (или неожиданный NULL) → fail closed ДО вставки child
    rows; существующая строка не мутируется и владелец не перепривязывается."""
    import uuid as _uuid
    db = _db_with_existing_owner(existing_owner)
    before = db.query.return_value.filter.return_value.first.return_value

    with pytest.raises(RuntimeError):
        st._ensure_series_identity(_uuid.uuid4(), 7, db)

    assert before.psychologist_id == existing_owner   # не изменён
    db.add.assert_not_called()                        # child rows не создаются
    db.flush.assert_not_called()


def test_ensure_mismatch_message_has_no_input_values():
    import uuid as _uuid
    sid = _uuid.uuid4()
    db = _db_with_existing_owner(9)
    with pytest.raises(RuntimeError) as ei:
        st._ensure_series_identity(sid, 7, db)
    msg = str(ei.value)
    assert msg == st._ERR_SERIES_OWNER_MISMATCH
    assert str(sid) not in msg
    for token in ("7", "9", "@", "SELECT"):
        assert token not in msg


@pytest.mark.parametrize("fn_name", [
    "create_schedule_rules_bulk", "create_schedule_series",
    "create_schedule_breaks_bulk",
])
def test_generators_fail_closed_before_creating_children(monkeypatch, fn_name):
    """Расхождение владельца обязано остановить генератор до вставки rules/breaks."""
    db = _db_with_existing_owner(999)
    monkeypatch.setattr(st, "_rule_to_dict", lambda r: {"id": 1})
    monkeypatch.setattr(st, "_break_to_dict", lambda b: {"id": 2})
    payload = (_breaks_payload() if fn_name == "create_schedule_breaks_bulk"
               else _rules_payload())

    _no_audit(monkeypatch)

    with pytest.raises(RuntimeError):
        getattr(st, fn_name)(payload, db, actor=SUP_ACTOR, context=CTX)

    db.add.assert_not_called()


def test_ensure_casts_psychologist_id_to_int():
    db = _db_with_no_existing_series()
    import uuid as _uuid
    row = st._ensure_series_identity(_uuid.uuid4(), "7", db)
    assert row.psychologist_id == 7 and isinstance(row.psychologist_id, int)


# ══════════════════════════════════════════════════════════════════════════
# 2. Все три генератора series_id вставляют identity ПЕРВОЙ
# ══════════════════════════════════════════════════════════════════════════

def _rules_payload():
    from datetime import date, time
    return {
        "psychologist_id": 7, "days_of_week": [1, 2],
        "start_time": time(9, 0), "end_time": time(10, 0),
        "effective_from": date(2026, 1, 1),
    }


def _breaks_payload():
    from datetime import date, time
    return {
        "psychologist_id": 7, "days_of_week": [1],
        "start_time": time(13, 0), "end_time": time(14, 0),
        "effective_from": date(2026, 1, 1),
    }


def test_create_schedule_rules_bulk_inserts_identity_first(monkeypatch):
    db = _db_with_no_existing_series()
    monkeypatch.setattr(st, "_rule_to_dict", lambda r: {"id": 1})
    _no_audit(monkeypatch)
    st.create_schedule_rules_bulk(
        _rules_payload(), db, actor=SUP_ACTOR, context=CTX)

    order = _add_order(db)
    assert order[0] == "ScheduleSeries", order      # identity ДО rules
    assert "ScheduleRule" in order
    assert len(_added_series(db)) == 1              # ровно одна identity на серию


def test_create_schedule_series_inserts_identity_first(monkeypatch):
    db = _db_with_no_existing_series()
    monkeypatch.setattr(st, "_rule_to_dict", lambda r: {"id": 1})
    monkeypatch.setattr(st, "_break_to_dict", lambda b: {"id": 2})
    payload = _rules_payload()
    payload["breaks"] = [
        {"start_time": __import__("datetime").time(13, 0),
         "end_time": __import__("datetime").time(14, 0), "title": None},
    ]
    _no_audit(monkeypatch)
    st.create_schedule_series(
        payload, db, actor=SUP_ACTOR, context=CTX)

    order = _add_order(db)
    assert order[0] == "ScheduleSeries", order
    assert "ScheduleRule" in order and "ScheduleBreak" in order
    assert len(_added_series(db)) == 1


def test_create_schedule_breaks_bulk_inserts_identity_first(monkeypatch):
    """break-only серия: rules нет, identity всё равно обязательна."""
    db = _db_with_no_existing_series()
    monkeypatch.setattr(st, "_break_to_dict", lambda b: {"id": 2})
    _no_audit(monkeypatch)
    st.create_schedule_breaks_bulk(
        _breaks_payload(), db, actor=SUP_ACTOR, context=CTX)

    order = _add_order(db)
    assert order[0] == "ScheduleSeries", order
    assert "ScheduleBreak" in order
    assert "ScheduleRule" not in order
    assert len(_added_series(db)) == 1


@pytest.mark.parametrize("fn_name", [
    "create_schedule_rules_bulk", "create_schedule_series",
    "create_schedule_breaks_bulk",
])
def test_identity_uuid_matches_series_rows(monkeypatch, fn_name):
    """series_uuid identity-строки совпадает с series_id созданных строк —
    иначе FK 5C-0C будет нарушен."""
    db = _db_with_no_existing_series()
    monkeypatch.setattr(st, "_rule_to_dict", lambda r: {"id": 1})
    monkeypatch.setattr(st, "_break_to_dict", lambda b: {"id": 2})
    payload = (_breaks_payload() if fn_name == "create_schedule_breaks_bulk"
               else _rules_payload())
    _no_audit(monkeypatch)
    getattr(st, fn_name)(payload, db, actor=SUP_ACTOR, context=CTX)

    identity = _added_series(db)[0]
    children = [
        c.args[0] for c in db.add.call_args_list
        if not isinstance(c.args[0], st.ScheduleSeries)
    ]
    assert children
    for child in children:
        assert child.series_id == identity.series_uuid
