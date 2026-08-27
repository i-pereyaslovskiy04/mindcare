"""
Stage 5C-1 — no-DB unit-тесты audit trail для типов встреч и расписаний.

Покрывает: registry contract 14 событий; actor/target/event mapping; no-op
семантику (identical PATCH / повторная деактивация / restore / extend без
сдвига); канонический diff серии (row-id сохраняются, audit не пишется);
combined MeetingType transition (updated + activated/deactivated двумя
непересекающимися строками); узкую границу IntegrityError в
create_schedule_exception; распространение AuditStorageError и недостижимость
owner-commit; fail-closed actor guard до мутации; минимизацию (metadata={},
без названий/дат/ПДн). Реальная БД не используется.
"""
import inspect
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.appointments.service as appt_service
import app.appointments.storage as st
from app.audit import Actor, RequestContext
from app.audit.contracts import AuditStorageError
from app.audit.registry import REGISTRY

SUP = Actor.user(9, "supervisor")
ADMIN = Actor.user(3, "admin")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")


# ══════════════════════════════════════════════════════════════════════════
# 1. Registry contract — 14 событий 5C-1
# ══════════════════════════════════════════════════════════════════════════

_5C1_EVENTS = {
    "meeting_type_created": "meeting_type",
    "meeting_type_updated": "meeting_type",
    "meeting_type_activated": "meeting_type",
    "meeting_type_deactivated": "meeting_type",
    "schedule_created": "schedule_series",
    "schedule_updated": "schedule_series",
    "schedule_deactivated": "schedule_series",
    "schedule_restored": "schedule_series",
    "schedule_extended": "schedule_series",
    "schedule_rule_created": "schedule_rule",
    "schedule_rule_deactivated": "schedule_rule",
    "schedule_break_created": "schedule_break",
    "schedule_break_deactivated": "schedule_break",
    "schedule_exception_created": "schedule_exception",
}


def test_registry_contract_and_count():
    assert len(REGISTRY) == 99
    for name, entity in _5C1_EVENTS.items():
        s = REGISTRY[name]
        assert s.destination.value == "audit_log", name
        assert s.allowed_actor_roles == frozenset({"supervisor", "admin"}), name
        assert s.target_policy.value == "required", name
        assert s.entity_type == entity, name
        assert {o.value for o in s.allowed_outcomes} == {"success"}, name
        assert s.allowed_failure_codes == frozenset(), name
        assert dict(s.metadata_schema) == {}, name        # минимизация
        assert s.tx_mode.value == "atomic", name
        assert s.failure_policy.value == "raise", name
        assert s.description_policy.value == "none", name


def test_series_target_is_identity_not_uuid_and_not_user():
    """target серии — schedule_series (integer identity 5C-0), НЕ user и не UUID."""
    for name in ("schedule_created", "schedule_updated", "schedule_deactivated",
                 "schedule_restored", "schedule_extended"):
        assert REGISTRY[name].entity_type == "schedule_series", name


# ══════════════════════════════════════════════════════════════════════════
# 2. Fail-closed actor guard — до любой мутации
# ══════════════════════════════════════════════════════════════════════════

def _db():
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.mark.parametrize("call", [
    lambda db: st.create_meeting_type({"name": "x"}, db, actor=None, context=None),
    lambda db: st.update_meeting_type(
        SimpleNamespace(id=1, is_active=True, name="a"), {"name": "b"}, db,
        actor=None, context=None),
    lambda db: st.create_schedule_rules_bulk(
        {"psychologist_id": 7, "days_of_week": [1]}, db,
        actor=None, context=None),
    lambda db: st.create_schedule_breaks_bulk(
        {"psychologist_id": 7, "days_of_week": [1]}, db,
        actor=None, context=None),
    lambda db: st.deactivate_schedule_rule(1, db, actor=None, context=None),
    lambda db: st.deactivate_schedule_break(1, db, actor=None, context=None),
    lambda db: st.create_schedule_exception({}, db, actor=None, context=None),
], ids=["mt_create", "mt_update", "rules_bulk", "breaks_bulk",
        "rule_deact", "break_deact", "exception"])
def test_actor_guard_rejects_before_mutation(call):
    db = _db()
    with pytest.raises(RuntimeError):
        call(db)
    db.add.assert_not_called()
    db.flush.assert_not_called()


def test_storage_actor_context_required_keyword_only():
    for fn_name in ("create_meeting_type", "update_meeting_type",
                    "create_schedule_rules_bulk", "create_schedule_series",
                    "update_schedule_series", "soft_delete_series",
                    "restore_series", "extend_series",
                    "deactivate_schedule_rule", "create_schedule_breaks_bulk",
                    "deactivate_schedule_break", "create_schedule_exception"):
        sig = inspect.signature(getattr(st, fn_name))
        for p_name in ("actor", "context"):
            p = sig.parameters[p_name]
            assert p.default is inspect.Parameter.empty, f"{fn_name}.{p_name}"
            assert p.kind == inspect.Parameter.KEYWORD_ONLY, f"{fn_name}.{p_name}"


def test_service_actor_role_required_no_default():
    for fn_name in ("create_meeting_type", "update_meeting_type",
                    "create_schedule_rules", "deactivate_schedule_rule",
                    "create_schedule", "update_schedule",
                    "soft_delete_schedule", "restore_schedule",
                    "extend_schedule", "create_schedule_breaks",
                    "deactivate_schedule_break", "create_schedule_exception"):
        sig = inspect.signature(getattr(appt_service, fn_name))
        for p_name in ("actor_id", "actor_role"):
            p = sig.parameters[p_name]
            assert p.default is inspect.Parameter.empty, f"{fn_name}.{p_name}"


# ══════════════════════════════════════════════════════════════════════════
# 3. MeetingType — mapping, combined transition, no-op
# ══════════════════════════════════════════════════════════════════════════

def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    return calls


def test_meeting_type_created_mapping(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "_mt_to_dict", lambda mt: {"id": mt.id})
    monkeypatch.setattr(st, "MeetingType",
                        lambda **kw: SimpleNamespace(id=42))
    db = MagicMock(name="db")
    st.create_meeting_type({"name": "СЕКРЕТНОЕ ИМЯ"}, db, actor=SUP, context=CTX)

    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "meeting_type_created"
    assert kw["actor"] is SUP
    assert kw["target"].entity_type == "meeting_type"
    assert kw["target"].entity_id == 42
    assert kw["metadata"] == {}
    assert kw["context"] is CTX and kw["db"] is db
    assert "СЕКРЕТНОЕ ИМЯ" not in repr(kw)      # название не в audit


def _mt(**over):
    base = dict(id=5, name="a", description=None, duration_minutes=50,
                buffer_minutes=10, allow_in_person=True, allow_online=True,
                is_group=False, is_active=True, is_bookable=True,
                display_order=0, updated_at=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_meeting_type_update_only_regular_fields(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "_mt_to_dict", lambda mt: {"id": mt.id})
    db = MagicMock(name="db")
    mt = _mt()
    st.update_meeting_type(mt, {"name": "b"}, db, actor=SUP, context=CTX)
    assert [c["event"] for c in calls] == ["meeting_type_updated"]
    assert mt.updated_at is not None


@pytest.mark.parametrize("before,after,expected", [
    (True, False, "meeting_type_deactivated"),
    (False, True, "meeting_type_activated"),
])
def test_meeting_type_is_active_only_no_generic_updated(
    monkeypatch, before, after, expected
):
    """PATCH только с is_active → generic updated НЕ пишется."""
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "_mt_to_dict", lambda mt: {"id": mt.id})
    db = MagicMock(name="db")
    st.update_meeting_type(
        _mt(is_active=before), {"is_active": after}, db, actor=SUP, context=CTX
    )
    assert [c["event"] for c in calls] == [expected]


def test_meeting_type_combined_transition_two_disjoint_rows(monkeypatch):
    """Обычные поля + is_active → ДВЕ непересекающиеся строки."""
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "_mt_to_dict", lambda mt: {"id": mt.id})
    db = MagicMock(name="db")
    st.update_meeting_type(
        _mt(is_active=True), {"name": "b", "is_active": False}, db,
        actor=ADMIN, context=CTX,
    )
    assert [c["event"] for c in calls] == [
        "meeting_type_updated", "meeting_type_deactivated",
    ]
    assert all(c["target"].entity_id == 5 for c in calls)
    assert all(c["actor"] is ADMIN for c in calls)


@pytest.mark.parametrize("updates", [
    {}, {"name": "a"}, {"is_active": True}, {"name": "a", "is_active": True},
], ids=["empty", "identical_field", "identical_is_active", "identical_both"])
def test_meeting_type_identical_patch_is_noop(monkeypatch, updates):
    """Identical PATCH → нет мутации, нет сдвига updated_at, нет audit."""
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "_mt_to_dict", lambda mt: {"id": mt.id})
    db = MagicMock(name="db")
    mt = _mt(name="a", is_active=True, updated_at=None)
    st.update_meeting_type(mt, updates, db, actor=SUP, context=CTX)
    assert calls == []
    assert mt.updated_at is None
    db.flush.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 4. Канонический diff серии — identical PATCH сохраняет row-id
# ══════════════════════════════════════════════════════════════════════════

def _rule(**over):
    base = dict(id=101, psychologist_id=7, meeting_type_id=None, day_of_week=1,
                start_time=time(9, 0), end_time=time(10, 0), period=None,
                effective_from=date(2026, 1, 1), effective_until=None,
                auto_extend=False, created_by=9, is_active=True,
                series_id="S", created_at=None)
    base.update(over)
    return SimpleNamespace(**base)


def _payload(**over):
    base = dict(days_of_week=[1], start_time=time(9, 0), end_time=time(10, 0),
                period=None, effective_from=date(2026, 1, 1),
                effective_until=None, auto_extend=False, breaks=[])
    base.update(over)
    return base


def _series_db(monkeypatch, rules, breaks=()):
    monkeypatch.setattr(st, "get_series_rules", lambda sid, db: list(rules))
    monkeypatch.setattr(st, "get_series_breaks", lambda sid, db: list(breaks))
    monkeypatch.setattr(st, "_ensure_series_identity",
                        lambda sid, pid, db: SimpleNamespace(id=55))
    monkeypatch.setattr(st, "_rule_to_dict", lambda r: {"id": r.id})
    monkeypatch.setattr(st, "_break_to_dict", lambda b: {"id": b.id})
    return MagicMock(name="db")


def test_schedule_update_identical_payload_is_noop(monkeypatch):
    """Каноническое совпадение → строки НЕ пересоздаются (row-id сохраняются),
    audit не пишется."""
    calls = _spy(monkeypatch)
    rules = [_rule(id=101)]
    db = _series_db(monkeypatch, rules)
    result = st.update_schedule_series(
        "S", _payload(), db, actor=SUP, context=CTX
    )
    assert calls == []
    db.query.assert_not_called()          # delete/recreate не выполнялся
    db.flush.assert_not_called()
    assert [r["id"] for r in result["rules"]] == [101]   # row-id сохранён


def test_schedule_update_real_diff_writes_exactly_one(monkeypatch):
    # ScheduleRule/ScheduleBreak НЕ подменяются: bulk delete обращается к
    # ScheduleRule.series_id как к атрибуту КЛАССА — lambda сломала бы запрос.
    calls = _spy(monkeypatch)
    db = _series_db(monkeypatch, [_rule(id=101)])
    st.update_schedule_series(
        "S", _payload(days_of_week=[1, 2]), db, actor=SUP, context=CTX
    )
    assert [c["event"] for c in calls] == ["schedule_updated"]
    assert calls[0]["target"].entity_type == "schedule_series"
    assert calls[0]["target"].entity_id == 55
    assert calls[0]["metadata"] == {}


def test_schedule_update_legacy_meeting_type_is_a_real_diff(monkeypatch):
    """Legacy-серия с meeting_type_id: перезапись очистит его → это НЕ no-op."""
    calls = _spy(monkeypatch)
    db = _series_db(monkeypatch, [_rule(id=101, meeting_type_id=3)])
    st.update_schedule_series("S", _payload(), db, actor=SUP, context=CTX)
    assert [c["event"] for c in calls] == ["schedule_updated"]


# ══════════════════════════════════════════════════════════════════════════
# 5. soft-delete / restore / extend — только реальный переход
# ══════════════════════════════════════════════════════════════════════════

def test_soft_delete_writes_on_real_transition(monkeypatch):
    calls = _spy(monkeypatch)
    rules = [_rule(is_active=True)]
    db = _series_db(monkeypatch, rules)
    r, b = st.soft_delete_series("S", db, actor=SUP, context=CTX)
    assert (r, b) == (1, 0)
    assert [c["event"] for c in calls] == ["schedule_deactivated"]
    assert calls[0]["target"].entity_id == 55 and calls[0]["metadata"] == {}


def test_soft_delete_repeat_is_noop(monkeypatch):
    calls = _spy(monkeypatch)
    db = _series_db(monkeypatch, [_rule(is_active=False)])
    assert st.soft_delete_series("S", db, actor=SUP, context=CTX) == (0, 0)
    assert calls == []
    db.flush.assert_not_called()


def test_restore_writes_on_real_transition_and_repeat_is_noop(monkeypatch):
    calls = _spy(monkeypatch)
    db = _series_db(monkeypatch, [_rule(is_active=False)])
    assert st.restore_series("S", db, actor=SUP, context=CTX) == (1, 0)
    assert [c["event"] for c in calls] == ["schedule_restored"]

    calls.clear()
    db2 = _series_db(monkeypatch, [_rule(is_active=True)])
    assert st.restore_series("S", db2, actor=SUP, context=CTX) == (0, 0)
    assert calls == []
    db2.flush.assert_not_called()


def test_extend_writes_only_on_real_shift(monkeypatch):
    calls = _spy(monkeypatch)
    db = _series_db(monkeypatch, [_rule(effective_until=date(2026, 1, 31))])
    changed = st.extend_series(
        "S", date(2026, 2, 28), db, actor=SUP, context=CTX
    )
    assert changed == 1
    assert [c["event"] for c in calls] == ["schedule_extended"]


def test_extend_same_date_is_noop(monkeypatch):
    calls = _spy(monkeypatch)
    same = date(2026, 1, 31)
    db = _series_db(monkeypatch, [_rule(effective_until=same)])
    assert st.extend_series("S", same, db, actor=SUP, context=CTX) == 0
    assert calls == []


def test_apply_series_extension_is_audit_free(monkeypatch):
    """Примитив автопродления (5C-3) не пишет audit в 5C-1."""
    calls = _spy(monkeypatch)
    db = _series_db(monkeypatch, [_rule(effective_until=date(2026, 1, 31))])
    assert st.apply_series_extension("S", date(2026, 2, 28), db) == 1
    assert calls == []


# ══════════════════════════════════════════════════════════════════════════
# 6. Per-row rules/breaks — bulk и transition-gated deactivate
# ══════════════════════════════════════════════════════════════════════════

def test_rules_bulk_writes_per_row(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "_ensure_series_identity",
                        lambda sid, pid, db: SimpleNamespace(id=55))
    monkeypatch.setattr(st, "_rule_to_dict", lambda r: {"id": r.id})
    seq = iter([SimpleNamespace(id=1), SimpleNamespace(id=2)])
    monkeypatch.setattr(st, "ScheduleRule", lambda **kw: next(seq))
    db = MagicMock(name="db")
    st.create_schedule_rules_bulk(
        {"psychologist_id": 7, "days_of_week": [1, 2],
         "start_time": time(9), "end_time": time(10),
         "effective_from": date(2026, 1, 1)},
        db, actor=SUP, context=CTX,
    )
    assert [c["event"] for c in calls] == [
        "schedule_rule_created", "schedule_rule_created",
    ]
    assert [c["target"].entity_id for c in calls] == [1, 2]


def test_empty_bulk_writes_nothing(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "_ensure_series_identity",
                        lambda sid, pid, db: SimpleNamespace(id=55))
    db = MagicMock(name="db")
    st.create_schedule_rules_bulk(
        {"psychologist_id": 7, "days_of_week": []}, db, actor=SUP, context=CTX)
    st.create_schedule_breaks_bulk(
        {"psychologist_id": 7, "days_of_week": []}, db, actor=SUP, context=CTX)
    assert calls == []


@pytest.mark.parametrize("fn,model,event", [
    ("deactivate_schedule_rule", "ScheduleRule", "schedule_rule_deactivated"),
    ("deactivate_schedule_break", "ScheduleBreak", "schedule_break_deactivated"),
])
def test_deactivate_transition_and_repeat_noop(monkeypatch, fn, model, event):
    calls = _spy(monkeypatch)
    row = SimpleNamespace(id=77, is_active=True)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = row

    assert getattr(st, fn)(77, db, actor=SUP, context=CTX) is True
    assert [c["event"] for c in calls] == [event]
    assert calls[0]["target"].entity_id == 77

    # повторная деактивация — no-op, но по-прежнему True (строка найдена)
    calls.clear()
    db.flush.reset_mock()
    assert getattr(st, fn)(77, db, actor=SUP, context=CTX) is True
    assert calls == []
    db.flush.assert_not_called()


@pytest.mark.parametrize("fn", [
    "deactivate_schedule_rule", "deactivate_schedule_break",
])
def test_deactivate_missing_row_returns_false_without_audit(monkeypatch, fn):
    calls = _spy(monkeypatch)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None
    assert getattr(st, fn)(77, db, actor=SUP, context=CTX) is False
    assert calls == []


# ══════════════════════════════════════════════════════════════════════════
# 7. create_schedule_exception: НЕТ выдуманного бизнес-конфликта
# ══════════════════════════════════════════════════════════════════════════

def test_no_fabricated_conflict_type_exists():
    """`schedule_exceptions` не имеет ни одного unique-constraint (уникальность
    снята миграцией 9e193b84bba8), поэтому «конфликт расписания» недостижим по
    построению — выдуманный тип и его 409 удалены."""
    from app.db.models import ScheduleException as SE
    kinds = {type(c).__name__ for c in SE.__table__.constraints}
    assert "UniqueConstraint" not in kinds
    assert not any(i.unique for i in SE.__table__.indexes)
    assert not hasattr(st, "ScheduleExceptionConflict")


def test_business_integrity_error_is_not_renamed(monkeypatch):
    """FK-ошибка (несуществующий психолог) всплывает как IntegrityError и НЕ
    переименовывается в доменный конфликт расписания."""
    from sqlalchemy.exc import IntegrityError
    monkeypatch.setattr(st, "ScheduleException",
                        lambda **kw: SimpleNamespace(id=1))
    db = MagicMock(name="db")
    db.flush.side_effect = IntegrityError("stmt", {}, Exception("orig"))
    with pytest.raises(IntegrityError):
        st.create_schedule_exception({}, db, actor=SUP, context=CTX)


def test_unknown_psychologist_gives_truthful_422(monkeypatch):
    """Реальная причина прежнего «конфликта» — неизвестный психолог — теперь
    даёт правдивый 422 ДО мутации, как в create_schedule."""
    db = MagicMock(name="owner_db")
    sess = MagicMock()
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    monkeypatch.setattr(appt_service.storage, "is_psychologist",
                        lambda *a, **kw: False)
    created = []
    monkeypatch.setattr(appt_service.storage, "create_schedule_exception",
                        lambda *a, **kw: created.append(1))

    with pytest.raises(appt_service.AppointmentError) as ei:
        appt_service.create_schedule_exception(
            {"exception_type": "day_off", "psychologist_id": 999},
            actor_id=9, actor_role="supervisor")
    assert ei.value.status_code == 422
    assert created == []                 # мутации не было
    db.commit.assert_not_called()


def test_audit_integrity_error_is_not_masked_as_conflict(monkeypatch):
    """IntegrityError из audit staging всплывает как есть (не как конфликт)."""
    from sqlalchemy.exc import IntegrityError
    monkeypatch.setattr(st, "ScheduleException",
                        lambda **kw: SimpleNamespace(id=1))
    monkeypatch.setattr(st, "_exception_to_dict", lambda e: {"id": e.id})

    def _boom(**kw):
        raise IntegrityError("audit", {}, Exception("orig"))
    monkeypatch.setattr(st, "record_event", _boom)
    db = MagicMock(name="db")
    with pytest.raises(IntegrityError):
        st.create_schedule_exception({}, db, actor=SUP, context=CTX)


def test_exception_created_mapping(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "ScheduleException",
                        lambda **kw: SimpleNamespace(id=13))
    monkeypatch.setattr(st, "_exception_to_dict", lambda e: {"id": e.id})
    db = MagicMock(name="db")
    st.create_schedule_exception(
        {"reason": "СЕКРЕТНАЯ ПРИЧИНА"}, db, actor=SUP, context=CTX
    )
    assert [c["event"] for c in calls] == ["schedule_exception_created"]
    assert calls[0]["target"].entity_type == "schedule_exception"
    assert calls[0]["target"].entity_id == 13
    assert calls[0]["metadata"] == {}
    assert "СЕКРЕТНАЯ ПРИЧИНА" not in repr(calls[0])   # reason не в audit


# ══════════════════════════════════════════════════════════════════════════
# 8. Service owner-commit boundary: AuditStorageError → commit не достигнут
# ══════════════════════════════════════════════════════════════════════════

def _mock_session(monkeypatch):
    db = MagicMock(name="owner_db")
    sess = MagicMock(name="SessionLocal")
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    return db


def _boom(*a, **kw):
    raise AuditStorageError("audit down")


def test_meeting_type_create_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "create_meeting_type", _boom)
    with pytest.raises(AuditStorageError):
        appt_service.create_meeting_type(
            {"name": "x"}, actor_id=9, actor_role="supervisor")
    db.commit.assert_not_called()


def test_schedule_create_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "is_psychologist",
                        lambda *a, **kw: True)
    monkeypatch.setattr(appt_service.storage, "create_schedule_series", _boom)
    with pytest.raises(AuditStorageError):
        appt_service.create_schedule(
            {"psychologist_id": 7, "days_of_week": [1],
             "start_time": "09:00", "end_time": "10:00",
             "effective_from": date(2026, 1, 1)},
            actor_id=9, actor_role="supervisor",
        )
    db.commit.assert_not_called()


def test_schedule_exception_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "is_psychologist",
                        lambda *a, **kw: True)
    monkeypatch.setattr(appt_service.storage, "create_schedule_exception",
                        _boom)
    with pytest.raises(AuditStorageError):
        appt_service.create_schedule_exception(
            {"exception_type": "day_off", "psychologist_id": 7},
            actor_id=9, actor_role="supervisor")
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 9. Static: нет прямого AuditLog writer в appointments
# ══════════════════════════════════════════════════════════════════════════

def test_no_direct_auditlog_writer_in_appointments():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app" / "appointments"
    for p in root.rglob("*.py"):
        assert "AuditLog(" not in p.read_text(encoding="utf-8"), p.name
