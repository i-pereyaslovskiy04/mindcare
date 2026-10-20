"""
Stage 6-B — no-DB unit-тесты подключения record_data_change к
update_meeting_type / update_group_session.

Покрывает: точный changed_fields + old/new mapping; snapshot old СТРОГО до
setattr; порядок generic paired_event -> DCL -> transition-события; границы
(is_active / booking_enabled / status НЕ попадают в DCL); identical PATCH —
0 record_event и 0 record_data_change; неизвестное для CHANGE_REGISTRY поле
роняет операцию ДО ORM-мутации; распространение DataChangeError/
DataChangeStorageError и недостижимость service-commit; storage
самостоятельно не управляет транзакцией (commit/rollback/close).

Реальная БД не используется — DataChangeLog(...) конструируется как обычный
Python-объект без сессии, поэтому нетронутый writer безопасно запускается
против MagicMock db в тестах, которые не подменяют record_data_change.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.appointments.service as appt_service
import app.appointments.storage as st
from app.audit import Actor, ChangeValue, Operation, RequestContext
from app.audit.change_contracts import DataChangeError, DataChangeStorageError

SUP = Actor.user(9, "supervisor")
ADMIN = Actor.user(3, "admin")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")


@pytest.fixture(autouse=True)
def _stub_dict_converters(monkeypatch):
    """_mt_to_dict/_gs_to_dict делают полноценные DB-запросы/сериализацию
    (uuid, meeting_type lookup, registered_count...) — не относится к Stage
    6-B и не нужно этому файлу. Тот же stub, что в test_schedule_audit_unit.py
    / test_group_audit_unit.py."""
    monkeypatch.setattr(st, "_mt_to_dict", lambda mt: {"id": mt.id})
    monkeypatch.setattr(st, "_gs_to_dict", lambda gs, db: {"id": gs.id})


def _mt(**over):
    base = dict(id=5, name="a", description=None, duration_minutes=50,
                buffer_minutes=10, allow_in_person=True, allow_online=True,
                is_group=False, is_active=True, is_bookable=True,
                display_order=0, updated_at=None)
    base.update(over)
    return SimpleNamespace(**base)


def _gs(**over):
    base = dict(id=7, title="a", description=None, capacity=10,
                booking_enabled=True, status="scheduled", format="online",
                meeting_type_id=1, psychologist_id=2, starts_at=None,
                ends_at=None, updated_at=None)
    base.update(over)
    return SimpleNamespace(**base)


def _event_spy(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    return calls


def _dcl_spy(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "record_data_change", lambda **kw: calls.append(kw))
    return calls


def _ordered_spy(monkeypatch):
    """Единый упорядоченный список record_event + record_data_change —
    доказывает порядок: generic paired_event -> DCL -> transition-события."""
    calls = []
    monkeypatch.setattr(
        st, "record_event",
        lambda **kw: calls.append(("event", kw["event"])),
    )
    monkeypatch.setattr(
        st, "record_data_change",
        lambda **kw: calls.append(("dcl", kw["table"])),
    )
    return calls


def _mock_service_session(monkeypatch):
    """Owner-commit boundary на уровне service (по образцу
    tests/test_schedule_audit_unit.py::_mock_session)."""
    db = MagicMock(name="owner_db")
    sess = MagicMock(name="SessionLocal")
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    return db


# ══════════════════════════════════════════════════════════════════════════
# 1. meeting_types — точный changed_fields / values mapping
# ══════════════════════════════════════════════════════════════════════════

def test_mt_name_only_fields_write_dcl_with_none_values(monkeypatch):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(name="a", description=None)
    st.update_meeting_type(
        mt, {"name": "b", "description": "d"}, db, actor=SUP, context=CTX
    )
    assert len(dcl) == 1
    kw = dcl[0]
    assert kw["table"] == "meeting_types"
    assert kw["record_id"] == 5
    assert kw["operation"] is Operation.UPDATE
    assert kw["actor"] is SUP
    assert kw["context"] is CTX
    assert kw["db"] is db
    assert kw["changed_fields"] == ["description", "name"]   # sorted
    assert kw["values"] is None


def test_mt_value_enabled_fields_write_exact_old_new_pairs(monkeypatch):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(duration_minutes=50, is_bookable=True)
    st.update_meeting_type(
        mt, {"duration_minutes": 75, "is_bookable": False}, db,
        actor=SUP, context=CTX,
    )
    kw = dcl[0]
    assert kw["changed_fields"] == ["duration_minutes", "is_bookable"]
    assert kw["values"] == {
        "duration_minutes": ChangeValue(old=50, new=75),
        "is_bookable": ChangeValue(old=True, new=False),
    }


def test_mt_combined_name_only_and_value_enabled_values_only_for_value_field(
    monkeypatch,
):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(name="a", duration_minutes=50)
    st.update_meeting_type(
        mt, {"name": "b", "duration_minutes": 75}, db, actor=SUP, context=CTX
    )
    kw = dcl[0]
    assert kw["changed_fields"] == ["duration_minutes", "name"]
    assert kw["values"] == {"duration_minutes": ChangeValue(old=50, new=75)}
    assert "name" not in kw["values"]


@pytest.mark.parametrize("field,before,after", [
    ("duration_minutes", 50, 75),
    ("buffer_minutes", 10, 20),
    ("display_order", 0, 3),
    ("allow_in_person", True, False),
    ("allow_online", True, False),
    ("is_group", False, True),
    ("is_bookable", True, False),
])
def test_mt_every_value_enabled_field_round_trips(monkeypatch, field, before, after):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(**{field: before})
    st.update_meeting_type(mt, {field: after}, db, actor=SUP, context=CTX)
    kw = dcl[0]
    assert kw["changed_fields"] == [field]
    assert kw["values"] == {field: ChangeValue(old=before, new=after)}


@pytest.mark.parametrize("field", ["name", "description"])
def test_mt_name_only_field_never_carries_a_value(monkeypatch, field):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(**{field: "old text"})
    st.update_meeting_type(mt, {field: "new text"}, db, actor=SUP, context=CTX)
    kw = dcl[0]
    assert kw["changed_fields"] == [field]
    assert kw["values"] is None
    # свободный текст не утекает даже в имени поля/значении
    assert "new text" not in repr(kw["changed_fields"])


# ══════════════════════════════════════════════════════════════════════════
# 2. meeting_types — границы: is_active НЕ попадает в DCL
# ══════════════════════════════════════════════════════════════════════════

def test_mt_transition_only_is_active_writes_zero_dcl(monkeypatch):
    events = _event_spy(monkeypatch)
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_meeting_type(
        _mt(is_active=True), {"is_active": False}, db, actor=SUP, context=CTX
    )
    assert [c["event"] for c in events] == ["meeting_type_deactivated"]
    assert dcl == []


def test_mt_combined_generic_and_transition_writes_exactly_one_dcl_without_is_active(
    monkeypatch,
):
    events = _event_spy(monkeypatch)
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_meeting_type(
        _mt(is_active=True), {"name": "b", "is_active": False}, db,
        actor=ADMIN, context=CTX,
    )
    assert [c["event"] for c in events] == [
        "meeting_type_updated", "meeting_type_deactivated",
    ]
    assert len(dcl) == 1
    assert dcl[0]["changed_fields"] == ["name"]
    assert "is_active" not in dcl[0]["changed_fields"]


def test_mt_identical_patch_writes_zero_events_and_zero_dcl(monkeypatch):
    events = _event_spy(monkeypatch)
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(name="a", is_active=True, updated_at=None)
    st.update_meeting_type(
        mt, {"name": "a", "is_active": True}, db, actor=SUP, context=CTX
    )
    assert events == []
    assert dcl == []
    assert mt.updated_at is None
    db.flush.assert_not_called()
    db.refresh.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 3. meeting_types — snapshot ordering + вызов после generic / до transition
# ══════════════════════════════════════════════════════════════════════════

def test_mt_old_snapshot_reflects_value_before_mutation(monkeypatch):
    """DCL-spy получает values, построенные из old_snapshot, снятого ДО
    setattr — а не из текущего (уже изменённого) состояния объекта."""
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(duration_minutes=50)
    st.update_meeting_type(
        mt, {"duration_minutes": 75}, db, actor=SUP, context=CTX
    )
    assert mt.duration_minutes == 75                       # мутация применена
    assert dcl[0]["values"]["duration_minutes"].old == 50   # snapshot — ДО неё
    assert dcl[0]["values"]["duration_minutes"].new == 75


def test_mt_dcl_called_after_generic_event_and_before_transition_event(monkeypatch):
    calls = _ordered_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_meeting_type(
        _mt(is_active=True), {"name": "b", "is_active": False}, db,
        actor=SUP, context=CTX,
    )
    assert calls == [
        ("event", "meeting_type_updated"),
        ("dcl", "meeting_types"),
        ("event", "meeting_type_deactivated"),
    ]


def test_mt_dcl_is_the_last_call_when_no_transition(monkeypatch):
    calls = _ordered_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_meeting_type(_mt(), {"name": "b"}, db, actor=SUP, context=CTX)
    assert calls == [("event", "meeting_type_updated"), ("dcl", "meeting_types")]


# ══════════════════════════════════════════════════════════════════════════
# 4. meeting_types — fail-closed: неизвестное поле роняет операцию до мутации
# ══════════════════════════════════════════════════════════════════════════

def test_mt_field_unknown_to_registry_raises_before_orm_mutation(monkeypatch):
    """Поле присутствует как атрибут ORM-объекта (getattr не падает), но
    отсутствует в CHANGE_REGISTRY: project_changed_fields обязана остановить
    операцию ДО setattr/flush/refresh/record_event."""
    events = _event_spy(monkeypatch)
    db = MagicMock(name="db")
    mt = _mt(name="a")
    mt.secret_field = "before"
    with pytest.raises(DataChangeError):
        st.update_meeting_type(
            mt, {"secret_field": "after"}, db, actor=SUP, context=CTX
        )
    assert mt.secret_field == "before"     # мутация НЕ произошла
    assert mt.updated_at is None
    assert events == []
    db.flush.assert_not_called()
    db.refresh.assert_not_called()
    db.add.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 5. meeting_types — распространение сбоя writer'а + owner-commit boundary
# ══════════════════════════════════════════════════════════════════════════

def test_mt_data_change_storage_error_propagates_after_generic_event(monkeypatch):
    events = _event_spy(monkeypatch)

    def _boom(**kw):
        raise DataChangeStorageError("dcl storage down")

    monkeypatch.setattr(st, "record_data_change", _boom)
    db = MagicMock(name="db")
    with pytest.raises(DataChangeStorageError):
        st.update_meeting_type(_mt(), {"name": "b"}, db, actor=SUP, context=CTX)
    # generic paired_event уже был застейджен ДО сбоя DCL (тот же порядок).
    assert [c["event"] for c in events] == ["meeting_type_updated"]


def test_mt_storage_never_manages_the_transaction(monkeypatch):
    db = MagicMock(name="db")
    mt = _mt(duration_minutes=50)
    st.update_meeting_type(mt, {"duration_minutes": 75}, db, actor=SUP, context=CTX)
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()


def test_mt_service_commit_not_reached_on_dcl_storage_error(monkeypatch):
    db = _mock_service_session(monkeypatch)
    monkeypatch.setattr(
        appt_service.storage, "get_meeting_type",
        lambda mt_id, db: _mt(name="a", is_group=False),
    )

    def _boom(**kw):
        raise DataChangeStorageError("dcl storage down")

    monkeypatch.setattr(st, "record_data_change", _boom)
    with pytest.raises(DataChangeStorageError):
        appt_service.update_meeting_type(
            5, {"name": "b"}, actor_id=9, actor_role="supervisor"
        )
    db.commit.assert_not_called()


def test_mt_service_commit_failure_propagates_without_swallowing(monkeypatch):
    """Commit-сбой (симулирует rollback БД) не поглощается: он пробрасывается,
    и никаких дополнительных операций после него не происходит."""
    db = _mock_service_session(monkeypatch)
    db.commit.side_effect = RuntimeError("commit boom")
    monkeypatch.setattr(
        appt_service.storage, "get_meeting_type",
        lambda mt_id, db: _mt(name="a", is_group=False),
    )
    with pytest.raises(RuntimeError, match="commit boom"):
        appt_service.update_meeting_type(
            5, {"name": "b"}, actor_id=9, actor_role="supervisor"
        )
    db.commit.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# 6. group_sessions — точный changed_fields / values mapping
# ══════════════════════════════════════════════════════════════════════════

def test_gs_name_only_fields_write_dcl_with_none_values(monkeypatch):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(title="a", description=None)
    st.update_group_session(
        gs, {"title": "b", "description": "d"}, db, actor=SUP, context=CTX
    )
    kw = dcl[0]
    assert kw["table"] == "group_sessions"
    assert kw["record_id"] == 7
    assert kw["operation"] is Operation.UPDATE
    assert kw["actor"] is SUP
    assert kw["context"] is CTX
    assert kw["db"] is db
    assert kw["changed_fields"] == ["description", "title"]   # sorted
    assert kw["values"] is None


def test_gs_value_enabled_fields_write_exact_old_new_pairs(monkeypatch):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(capacity=10, format="online", meeting_type_id=1)
    st.update_group_session(
        gs, {"capacity": 25, "format": "in_person", "meeting_type_id": 9}, db,
        actor=SUP, context=CTX,
    )
    kw = dcl[0]
    assert kw["changed_fields"] == ["capacity", "format", "meeting_type_id"]
    assert kw["values"] == {
        "capacity": ChangeValue(old=10, new=25),
        "format": ChangeValue(old="online", new="in_person"),
        "meeting_type_id": ChangeValue(old=1, new=9),
    }


def test_gs_combined_name_only_and_value_enabled_values_only_for_value_field(
    monkeypatch,
):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(title="a", capacity=10)
    st.update_group_session(
        gs, {"title": "b", "capacity": 25}, db, actor=SUP, context=CTX
    )
    kw = dcl[0]
    assert kw["changed_fields"] == ["capacity", "title"]
    assert kw["values"] == {"capacity": ChangeValue(old=10, new=25)}
    assert "title" not in kw["values"]


@pytest.mark.parametrize("field", ["title", "description", "starts_at",
                                   "ends_at", "psychologist_id"])
def test_gs_name_only_field_never_carries_a_value(monkeypatch, field):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(**{field: "before"})
    st.update_group_session(gs, {field: "after"}, db, actor=SUP, context=CTX)
    kw = dcl[0]
    assert kw["changed_fields"] == [field]
    assert kw["values"] is None


# ══════════════════════════════════════════════════════════════════════════
# 7. group_sessions — границы: booking_enabled/status НЕ попадают в DCL
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("before,after", [(True, False), (False, True)])
def test_gs_transition_only_booking_writes_zero_dcl(monkeypatch, before, after):
    events = _event_spy(monkeypatch)
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(
        _gs(booking_enabled=before), {"booking_enabled": after}, db,
        actor=SUP, context=CTX,
    )
    assert len(events) == 1
    assert dcl == []


def test_gs_transition_only_status_cancelled_writes_zero_dcl(monkeypatch):
    events = _event_spy(monkeypatch)
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(
        _gs(status="scheduled"), {"status": "cancelled"}, db,
        actor=ADMIN, context=CTX,
    )
    assert [c["event"] for c in events] == ["group_session_cancelled"]
    assert dcl == []


def test_gs_combined_generic_booking_status_writes_exactly_one_dcl(monkeypatch):
    events = _event_spy(monkeypatch)
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(
        _gs(booking_enabled=True, status="scheduled"),
        {"title": "b", "booking_enabled": False, "status": "cancelled"}, db,
        actor=SUP, context=CTX,
    )
    assert [c["event"] for c in events] == [
        "group_session_updated",
        "group_session_booking_closed",
        "group_session_cancelled",
    ]
    assert len(dcl) == 1
    assert dcl[0]["changed_fields"] == ["title"]
    for leaked in ("booking_enabled", "status"):
        assert leaked not in dcl[0]["changed_fields"]


def test_gs_identical_patch_writes_zero_events_and_zero_dcl(monkeypatch):
    events = _event_spy(monkeypatch)
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(title="a", booking_enabled=True, status="scheduled",
             updated_at=None)
    st.update_group_session(
        gs, {"title": "a", "booking_enabled": True, "status": "scheduled"},
        db, actor=SUP, context=CTX,
    )
    assert events == []
    assert dcl == []
    assert gs.updated_at is None
    db.flush.assert_not_called()
    db.refresh.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 8. group_sessions — snapshot ordering + вызов после generic / до transition
# ══════════════════════════════════════════════════════════════════════════

def test_gs_old_snapshot_reflects_value_before_mutation(monkeypatch):
    dcl = _dcl_spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(capacity=10)
    st.update_group_session(gs, {"capacity": 40}, db, actor=SUP, context=CTX)
    assert gs.capacity == 40
    assert dcl[0]["values"]["capacity"].old == 10
    assert dcl[0]["values"]["capacity"].new == 40


def test_gs_dcl_called_after_generic_event_and_before_transition_events(monkeypatch):
    calls = _ordered_spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(
        _gs(booking_enabled=True, status="scheduled"),
        {"title": "b", "booking_enabled": False, "status": "cancelled"}, db,
        actor=SUP, context=CTX,
    )
    assert calls == [
        ("event", "group_session_updated"),
        ("dcl", "group_sessions"),
        ("event", "group_session_booking_closed"),
        ("event", "group_session_cancelled"),
    ]


# ══════════════════════════════════════════════════════════════════════════
# 9. group_sessions — fail-closed: неизвестное поле роняет операцию до мутации
# ══════════════════════════════════════════════════════════════════════════

def test_gs_field_unknown_to_registry_raises_before_orm_mutation(monkeypatch):
    events = _event_spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(title="a")
    gs.secret_field = "before"
    with pytest.raises(DataChangeError):
        st.update_group_session(
            gs, {"secret_field": "after"}, db, actor=SUP, context=CTX
        )
    assert gs.secret_field == "before"
    assert gs.updated_at is None
    assert events == []
    db.flush.assert_not_called()
    db.refresh.assert_not_called()
    db.add.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 10. group_sessions — распространение сбоя writer'а + owner-commit boundary
# ══════════════════════════════════════════════════════════════════════════

def test_gs_data_change_error_propagates_after_generic_event(monkeypatch):
    events = _event_spy(monkeypatch)

    def _boom(**kw):
        raise DataChangeError("contract violation")

    monkeypatch.setattr(st, "record_data_change", _boom)
    db = MagicMock(name="db")
    with pytest.raises(DataChangeError):
        st.update_group_session(_gs(), {"title": "b"}, db, actor=SUP, context=CTX)
    assert [c["event"] for c in events] == ["group_session_updated"]


def test_gs_storage_never_manages_the_transaction(monkeypatch):
    db = MagicMock(name="db")
    gs = _gs(capacity=10)
    st.update_group_session(gs, {"capacity": 40}, db, actor=SUP, context=CTX)
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.close.assert_not_called()


def test_gs_service_commit_not_reached_on_dcl_storage_error(monkeypatch):
    db = _mock_service_session(monkeypatch)
    monkeypatch.setattr(
        appt_service.storage, "get_group_session_by_uuid",
        lambda uuid, db: _gs(title="a"),
    )

    def _boom(**kw):
        raise DataChangeStorageError("dcl storage down")

    monkeypatch.setattr(st, "record_data_change", _boom)
    with pytest.raises(DataChangeStorageError):
        appt_service.update_group_session(
            "11111111-1111-1111-1111-111111111111", {"title": "b"},
            actor_id=9, actor_role="supervisor",
        )
    db.commit.assert_not_called()


def test_gs_service_commit_failure_propagates_without_swallowing(monkeypatch):
    db = _mock_service_session(monkeypatch)
    db.commit.side_effect = RuntimeError("commit boom")
    monkeypatch.setattr(
        appt_service.storage, "get_group_session_by_uuid",
        lambda uuid, db: _gs(title="a"),
    )
    with pytest.raises(RuntimeError, match="commit boom"):
        appt_service.update_group_session(
            "11111111-1111-1111-1111-111111111111", {"title": "b"},
            actor_id=9, actor_role="supervisor",
        )
    db.commit.assert_called_once()
