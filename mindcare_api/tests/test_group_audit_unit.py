"""
Stage 5C-2 — no-DB unit-тесты audit trail групповых занятий и регистраций.

Покрывает: registry contract 7 событий; actor/target/event mapping; generic
group_session_updated НЕ содержит status/booking_enabled; booking-переходы и
scheduled→cancelled как отдельные строки; no-op (identical PATCH, booking
same→same); transition-контракт status (manual completed запрещён,
cancelled→scheduled запрещён, identical — no-op); регистрации с внутренним
integer id (реактивация переиспользует тот же id); отказ/не найдено → 0
success-событий; fail-closed actor guard; распространение AuditStorageError и
недостижимость owner-commit; минимизация. Реальная БД не используется.
"""
import inspect
from datetime import datetime, timedelta, timezone
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
STUDENT = Actor.user(50, "student")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")


# ══════════════════════════════════════════════════════════════════════════
# 1. Registry contract — 7 событий 5C-2
# ══════════════════════════════════════════════════════════════════════════

_STAFF_EVENTS = {
    "group_session_created", "group_session_updated",
    "group_session_booking_opened", "group_session_booking_closed",
    "group_session_cancelled",
}
_STUDENT_EVENTS = {
    "group_session_registered", "group_session_registration_cancelled",
}


def test_registry_contract_and_count():
    assert len(REGISTRY) == 94
    for name in _STAFF_EVENTS | _STUDENT_EVENTS:
        s = REGISTRY[name]
        assert s.destination.value == "audit_log", name
        assert s.target_policy.value == "required", name
        assert {o.value for o in s.allowed_outcomes} == {"success"}, name
        assert s.allowed_failure_codes == frozenset(), name
        assert dict(s.metadata_schema) == {}, name        # минимизация
        assert s.tx_mode.value == "atomic", name
        assert s.failure_policy.value == "raise", name
        assert s.description_policy.value == "none", name


def test_staff_and_student_roles_and_entities():
    for name in _STAFF_EVENTS:
        s = REGISTRY[name]
        assert s.allowed_actor_roles == frozenset({"supervisor", "admin"}), name
        assert s.entity_type == "group_session", name
    for name in _STUDENT_EVENTS:
        s = REGISTRY[name]
        assert s.allowed_actor_roles == frozenset({"student"}), name
        assert s.entity_type == "group_session_registration", name


def test_completed_event_is_system_only_not_staff_writable():
    """`completed` принадлежит system maintenance (5C-3): событие существует, но
    у него SYSTEM actor policy и НЕТ ролей — staff записать его не может."""
    s = REGISTRY["group_session_completed"]
    assert s.actor_policy.value == "system"
    assert s.allowed_actor_roles == frozenset()
    # и оно не входит в набор staff-событий 5C-2
    assert "group_session_completed" not in _STAFF_EVENTS


# ══════════════════════════════════════════════════════════════════════════
# 2. Fail-closed actor guard + обязательные сигнатуры
# ══════════════════════════════════════════════════════════════════════════

def _db():
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = None
    return db


@pytest.mark.parametrize("call", [
    lambda db: st.create_group_session({}, db, actor=None, context=None),
    lambda db: st.update_group_session(
        SimpleNamespace(id=1, booking_enabled=True, status="scheduled"),
        {"title": "x"}, db, actor=None, context=None),
    lambda db: st.set_group_session_booking(
        SimpleNamespace(id=1, booking_enabled=True), False, db,
        actor=None, context=None),
    lambda db: st.register_student_group_session(
        SimpleNamespace(id=1), 50, db, actor=None, context=None),
    lambda db: st.cancel_student_group_session(
        "u", 50, db, actor=None, context=None),
], ids=["create", "update", "booking", "register", "cancel"])
def test_actor_guard_rejects_before_mutation(call):
    db = _db()
    with pytest.raises(RuntimeError):
        call(db)
    db.add.assert_not_called()
    db.flush.assert_not_called()


def test_storage_actor_context_required_keyword_only():
    for fn_name in ("create_group_session", "update_group_session",
                    "set_group_session_booking",
                    "register_student_group_session",
                    "cancel_student_group_session"):
        sig = inspect.signature(getattr(st, fn_name))
        for p_name in ("actor", "context"):
            p = sig.parameters[p_name]
            assert p.default is inspect.Parameter.empty, f"{fn_name}.{p_name}"
            assert p.kind == inspect.Parameter.KEYWORD_ONLY, f"{fn_name}.{p_name}"


def test_service_actor_role_required_no_default():
    for fn_name, params in (
        ("create_group_session", ("actor_id", "actor_role")),
        ("update_group_session", ("actor_id", "actor_role")),
        ("set_group_session_booking", ("actor_id", "actor_role")),
        ("student_register_group", ("actor_role",)),
        ("student_cancel_group", ("actor_role",)),
    ):
        sig = inspect.signature(getattr(appt_service, fn_name))
        for p_name in params:
            p = sig.parameters[p_name]
            assert p.default is inspect.Parameter.empty, f"{fn_name}.{p_name}"


# ══════════════════════════════════════════════════════════════════════════
# 3. GroupSession create / update / transitions
# ══════════════════════════════════════════════════════════════════════════

def _spy(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(st, "_gs_to_dict", lambda gs, db: {"id": gs.id})
    return calls


def _gs(**over):
    base = dict(id=7, title="a", description=None, capacity=10,
                booking_enabled=True, status="scheduled", format="online",
                meeting_type_id=1, psychologist_id=2, starts_at=None,
                ends_at=None, updated_at=None)
    base.update(over)
    return SimpleNamespace(**base)


def test_group_session_created_mapping(monkeypatch):
    calls = _spy(monkeypatch)
    monkeypatch.setattr(st, "GroupSession", lambda **kw: _gs(id=77))
    db = MagicMock(name="db")
    st.create_group_session(
        {"title": "СЕКРЕТНОЕ НАЗВАНИЕ"}, db, actor=SUP, context=CTX
    )
    assert len(calls) == 1
    kw = calls[0]
    assert kw["event"] == "group_session_created"
    assert kw["actor"] is SUP
    assert kw["target"].entity_type == "group_session"
    assert kw["target"].entity_id == 77
    assert kw["metadata"] == {}
    assert kw["context"] is CTX and kw["db"] is db
    assert "СЕКРЕТНОЕ НАЗВАНИЕ" not in repr(kw)


def test_generic_update_excludes_booking_and_status(monkeypatch):
    """Изменение только title → ровно один generic updated."""
    calls = _spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(_gs(), {"title": "b"}, db, actor=SUP, context=CTX)
    assert [c["event"] for c in calls] == ["group_session_updated"]


@pytest.mark.parametrize("before,after,expected", [
    (True, False, "group_session_booking_closed"),
    (False, True, "group_session_booking_opened"),
])
def test_update_booking_transition_without_generic(
    monkeypatch, before, after, expected
):
    """PATCH только booking_enabled → generic updated НЕ пишется."""
    calls = _spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(
        _gs(booking_enabled=before), {"booking_enabled": after}, db,
        actor=SUP, context=CTX,
    )
    assert [c["event"] for c in calls] == [expected]


def test_update_status_cancelled_writes_only_cancelled(monkeypatch):
    calls = _spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(
        _gs(status="scheduled"), {"status": "cancelled"}, db,
        actor=ADMIN, context=CTX,
    )
    assert [c["event"] for c in calls] == ["group_session_cancelled"]
    assert calls[0]["actor"] is ADMIN
    assert calls[0]["target"].entity_id == 7


def test_combined_update_writes_disjoint_rows(monkeypatch):
    """title + booking + status → три непересекающиеся строки."""
    calls = _spy(monkeypatch)
    db = MagicMock(name="db")
    st.update_group_session(
        _gs(booking_enabled=True, status="scheduled"),
        {"title": "b", "booking_enabled": False, "status": "cancelled"}, db,
        actor=SUP, context=CTX,
    )
    assert [c["event"] for c in calls] == [
        "group_session_updated",
        "group_session_booking_closed",
        "group_session_cancelled",
    ]


@pytest.mark.parametrize("updates", [
    {}, {"title": "a"}, {"booking_enabled": True}, {"status": "scheduled"},
    {"title": "a", "booking_enabled": True, "status": "scheduled"},
], ids=["empty", "same_title", "same_booking", "same_status", "all_same"])
def test_update_identical_patch_is_noop(monkeypatch, updates):
    calls = _spy(monkeypatch)
    db = MagicMock(name="db")
    gs = _gs(title="a", booking_enabled=True, status="scheduled",
             updated_at=None)
    st.update_group_session(gs, updates, db, actor=SUP, context=CTX)
    assert calls == []
    assert gs.updated_at is None
    db.flush.assert_not_called()


def test_set_booking_transition_and_same_value_noop(monkeypatch):
    calls = _spy(monkeypatch)
    db = MagicMock(name="db")
    st.set_group_session_booking(
        _gs(booking_enabled=True), False, db, actor=SUP, context=CTX)
    assert [c["event"] for c in calls] == ["group_session_booking_closed"]

    calls.clear()
    gs = _gs(booking_enabled=True, updated_at=None)
    st.set_group_session_booking(gs, True, db, actor=SUP, context=CTX)
    assert calls == []                    # same→same → no-op
    assert gs.updated_at is None


# ══════════════════════════════════════════════════════════════════════════
# 4. Status transition contract (service)
# ══════════════════════════════════════════════════════════════════════════

def test_manual_completed_is_rejected():
    with pytest.raises(appt_service.AppointmentError) as ei:
        appt_service._validate_group_status_transition("scheduled", "completed")
    assert ei.value.status_code == 422


def test_cancelled_to_scheduled_is_rejected():
    """Восстановление требует отдельного события — молча не вводится."""
    with pytest.raises(appt_service.AppointmentError) as ei:
        appt_service._validate_group_status_transition("cancelled", "scheduled")
    assert ei.value.status_code == 422


def test_scheduled_to_cancelled_is_allowed():
    appt_service._validate_group_status_transition("scheduled", "cancelled")


@pytest.mark.parametrize("status", ["scheduled", "cancelled", "completed"])
def test_identical_status_is_noop_not_rejected(status):
    """Identical status не считается переходом и не отвергается."""
    appt_service._validate_group_status_transition(status, status)


@pytest.mark.parametrize("field", [
    "status", "booking_enabled", "meeting_type_id", "psychologist_id",
    "starts_at", "format", "capacity",
])
def test_explicit_null_for_not_null_field_is_422_before_mutation(
    monkeypatch, field
):
    """Corrective: явный null для NOT NULL-поля раньше доходил до setattr и
    падал NOT NULL violation (500). Теперь — контролируемый 422 ДО мутации."""
    db = _mock_session(monkeypatch)
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_service.storage, "get_group_session_by_uuid",
                        lambda *a, **kw: _gs())
    mutated = []
    monkeypatch.setattr(appt_service.storage, "update_group_session",
                        lambda *a, **kw: mutated.append(1))

    with pytest.raises(appt_service.AppointmentError) as ei:
        appt_service.update_group_session(
            "u", {field: None}, actor_id=9, actor_role="supervisor")

    assert ei.value.status_code == 422
    assert field in ei.value.message
    assert mutated == [] and calls == []
    db.commit.assert_not_called()


def test_explicit_null_rejected_before_status_transition_check(monkeypatch):
    """status=None не должен уходить в transition-контракт как «переход»."""
    _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_group_session_by_uuid",
                        lambda *a, **kw: _gs(status="scheduled"))
    with pytest.raises(appt_service.AppointmentError) as ei:
        appt_service.update_group_session(
            "u", {"status": None}, actor_id=9, actor_role="supervisor")
    assert ei.value.status_code == 422
    assert "null" in ei.value.message.lower()


def test_nullable_fields_still_accept_explicit_null(monkeypatch):
    """title/description/ends_at NULLABLE — явный null остаётся допустимым."""
    _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_group_session_by_uuid",
                        lambda *a, **kw: _gs(title="a"))
    seen = {}
    monkeypatch.setattr(
        appt_service.storage, "update_group_session",
        lambda gs, upd, db, **kw: seen.update(upd) or {"id": 7})
    appt_service.update_group_session(
        "u", {"title": None}, actor_id=9, actor_role="supervisor")
    assert seen == {"title": None}          # 422 не поднят


def test_schema_status_is_stable_enum_not_free_string():
    from app.appointments.schemas import GroupSessionUpdate
    with pytest.raises(Exception):
        GroupSessionUpdate(status="bogus")
    with pytest.raises(Exception):
        GroupSessionUpdate(status="completed")   # только через maintenance
    assert GroupSessionUpdate(status="cancelled").status == "cancelled"


# ══════════════════════════════════════════════════════════════════════════
# 5. Регистрации — внутренний integer id, реактивация переиспользует id
# ══════════════════════════════════════════════════════════════════════════

def _reg_db(existing=None):
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = existing
    return db


def test_register_new_uses_internal_integer_id(monkeypatch):
    """GroupSessionRegistration НЕ подменяется lambda: query обращается к
    атрибутам КЛАССА (GroupSessionRegistration.group_session_id). Вместо этого
    подменяется db.add, чтобы «выдать» строке integer id после flush."""
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    db = _reg_db(existing=None)
    added = {}

    def _add(obj):
        added["reg"] = obj
        obj.id = 321                 # эмулируем присвоение PK на flush
        obj.uuid = "reg-uuid"
    db.add.side_effect = _add

    result = st.register_student_group_session(
        _gs(), 50, db, actor=STUDENT, context=CTX)

    assert [c["event"] for c in calls] == ["group_session_registered"]
    kw = calls[0]
    assert kw["target"].entity_type == "group_session_registration"
    assert kw["target"].entity_id == 321          # integer id, не UUID
    assert kw["actor"] is STUDENT and kw["metadata"] == {}
    assert "reg-uuid" not in repr(kw["target"])
    assert "id" not in result                     # публичный DTO не расширен
    assert result["uuid"] == "reg-uuid"


def test_reactivation_reuses_same_registration_id(monkeypatch):
    """cancelled→registered переиспользует ТУ ЖЕ строку → стабильный target."""
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    existing = SimpleNamespace(id=321, uuid="reg-uuid", group_session_id=7,
                               student_id=50, status="cancelled",
                               created_at=None, updated_at=None)
    db = _reg_db(existing=existing)

    st.register_student_group_session(
        _gs(), 50, db, actor=STUDENT, context=CTX)

    assert [c["event"] for c in calls] == ["group_session_registered"]
    assert calls[0]["target"].entity_id == 321    # тот же id, что и у новой
    # Статус переводится SQL-уровневым условным UPDATE (не setattr), поэтому на
    # mock-сессии in-memory объект не перечитывается: проверяем сам факт
    # выполнения UPDATE. Реальное значение status проверяет gated-тест на живой
    # БД (test_reactivation_reuses_same_registration_id в integration).
    db.execute.assert_called_once()


def test_cancel_registration_writes_event_with_reg_id(monkeypatch):
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    gs = _gs(id=7)
    reg = SimpleNamespace(id=321, status="registered", updated_at=None)
    monkeypatch.setattr(st, "get_group_session_by_uuid", lambda u, db: gs)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = reg

    assert st.cancel_student_group_session(
        "u", 50, db, actor=STUDENT, context=CTX) is True
    assert [c["event"] for c in calls] == [
        "group_session_registration_cancelled"]
    assert calls[0]["target"].entity_id == 321
    assert calls[0]["actor"] is STUDENT


def test_reactivation_no_flip_raises_conflict_without_audit(monkeypatch):
    """Corrective (concurrency): условный UPDATE не нашёл строку для перехода
    (её уже перевела конкурентная транзакция) → конфликт, 0 мутаций, 0 audit."""
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    existing = SimpleNamespace(id=321, uuid="u", group_session_id=7,
                               student_id=50, status="registered",
                               created_at=None, updated_at=None)
    db = _reg_db(existing=existing)
    db.execute.return_value.first.return_value = None      # no-flip

    with pytest.raises(st.GroupRegistrationConflict):
        st.register_student_group_session(
            _gs(), 50, db, actor=STUDENT, context=CTX)
    assert calls == []


def _integrity_error(constraint_name):
    """IntegrityError с psycopg2-подобным ``orig.diag.constraint_name``."""
    from sqlalchemy.exc import IntegrityError
    orig = Exception("orig")
    if constraint_name is not None:
        orig.diag = SimpleNamespace(constraint_name=constraint_name)
    return IntegrityError("stmt", {}, orig)


def test_new_registration_unique_violation_becomes_conflict(monkeypatch):
    """Нарушение РЕАЛЬНОГО partial unique ux_gsr_active → доменный конфликт."""
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    db = _reg_db(existing=None)
    db.flush.side_effect = _integrity_error("ux_gsr_active")

    with pytest.raises(st.GroupRegistrationConflict):
        st.register_student_group_session(
            _gs(), 50, db, actor=STUDENT, context=CTX)
    assert calls == []


@pytest.mark.parametrize("constraint_name", [
    "group_session_registrations_group_session_id_fkey",   # FK на занятие
    "group_session_registrations_student_id_fkey",         # FK на студента
    "group_session_registrations_uuid_key",                # чужой unique
    None,                                                  # драйвер не назвал
])
def test_foreign_integrity_error_is_not_masked_as_conflict(
    monkeypatch, constraint_name
):
    """Только ux_gsr_active — бизнес-конфликт; остальное всплывает как есть.

    Иначе FK-нарушение (несуществующее занятие/студент) выдавалось бы студенту
    за «вы уже записаны» и скрывало реальный дефект.
    """
    from sqlalchemy.exc import IntegrityError
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    db = _reg_db(existing=None)
    db.flush.side_effect = _integrity_error(constraint_name)

    with pytest.raises(IntegrityError):
        st.register_student_group_session(
            _gs(), 50, db, actor=STUDENT, context=CTX)
    assert calls == []


def test_conflict_classifier_reads_structured_diag_not_message_text():
    """Классификация опирается на orig.diag.constraint_name, не на текст.

    Разбор строки исключения ломается от локали/версии драйвера и протащил бы
    произвольную ошибку в доменный 409.
    """
    from sqlalchemy.exc import IntegrityError
    assert st._is_gsr_active_violation(
        _integrity_error("ux_gsr_active")) is True
    # имя constraint отсутствует, но текст сообщения его содержит
    misleading = IntegrityError(
        "stmt", {}, Exception('duplicate key value violates "ux_gsr_active"'))
    assert st._is_gsr_active_violation(misleading) is False


def test_cancel_no_flip_returns_false_without_audit(monkeypatch):
    """Две параллельные отмены: вторая не переворачивает строку → False, 0 audit."""
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(st, "get_group_session_by_uuid", lambda u, db: _gs())
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = (
        SimpleNamespace(id=321, status="registered", updated_at=None))
    db.execute.return_value.first.return_value = None       # no-flip

    assert st.cancel_student_group_session(
        "u", 50, db, actor=STUDENT, context=CTX) is False
    assert calls == []


@pytest.mark.parametrize("fn,marker", [
    ("register_student_group_session", 'status != "registered"'),
    ("cancel_student_group_session", 'status == "registered"'),
])
def test_transitions_use_conditional_update_returning(fn, marker):
    """Переход выполняется условным UPDATE…RETURNING, а не безусловным setattr:
    иначе устаревшее чтение давало бы вторую audit-строку при нулевом переходе."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "app" / "appointments"
           / "storage.py").read_text(encoding="utf-8")
    body = src.split(f"def {fn}(", 1)[1].split("\ndef ", 1)[0]
    assert ".returning(" in body
    assert "sa.update(" in body
    assert marker in body


@pytest.mark.parametrize("gs,reg", [
    (None, None),                                   # занятие не найдено
    (_gs(), None),                                  # активной регистрации нет
], ids=["no_session", "no_registration"])
def test_cancel_not_found_writes_no_event(monkeypatch, gs, reg):
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(st, "get_group_session_by_uuid", lambda u, db: gs)
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.first.return_value = reg

    assert st.cancel_student_group_session(
        "u", 50, db, actor=STUDENT, context=CTX) is False
    assert calls == []
    db.flush.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 6. Service owner-commit boundary
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


def test_group_create_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_meeting_type",
                        lambda *a, **kw: SimpleNamespace(
                            is_group=True, allow_in_person=True,
                            allow_online=True))
    monkeypatch.setattr(appt_service.storage, "is_psychologist",
                        lambda *a, **kw: True)
    monkeypatch.setattr(appt_service.storage, "create_group_session", _boom)
    with pytest.raises(AuditStorageError):
        appt_service.create_group_session(
            {"meeting_type_id": 1, "psychologist_id": 2, "format": "online"},
            actor_id=9, actor_role="supervisor")
    db.commit.assert_not_called()


def test_group_update_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service.storage, "get_group_session_by_uuid",
                        lambda *a, **kw: _gs())
    monkeypatch.setattr(appt_service.storage, "update_group_session", _boom)
    with pytest.raises(AuditStorageError):
        appt_service.update_group_session(
            "u", {"title": "b"}, actor_id=9, actor_role="supervisor")
    db.commit.assert_not_called()


def test_registration_cancel_service_commit_not_reached(monkeypatch):
    from datetime import datetime, timedelta
    db = _mock_session(monkeypatch)
    future = datetime.now(appt_service.MOSCOW_TZ) + timedelta(days=5)
    monkeypatch.setattr(appt_service.storage, "get_group_session_by_uuid",
                        lambda *a, **kw: _gs(starts_at=future))
    monkeypatch.setattr(appt_service.storage, "cancel_student_group_session",
                        _boom)
    with pytest.raises(AuditStorageError):
        appt_service.student_cancel_group(
            "u", {"id": 50}, actor_role="student")
    db.commit.assert_not_called()


def test_rejected_status_transition_writes_nothing(monkeypatch):
    """Отказ transition-контракта → 422 и НИ ОДНОГО success-события."""
    db = _mock_session(monkeypatch)
    calls = []
    monkeypatch.setattr(st, "record_event", lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_service.storage, "get_group_session_by_uuid",
                        lambda *a, **kw: _gs(status="cancelled"))
    with pytest.raises(appt_service.AppointmentError) as ei:
        appt_service.update_group_session(
            "u", {"status": "scheduled"}, actor_id=9, actor_role="supervisor")
    assert ei.value.status_code == 422
    assert calls == []
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 12. Lead-time cutoff читается ПОСЛЕ лока, вплотную к мутации (corrective)
# ══════════════════════════════════════════════════════════════════════════
#
# Регрессия: now_msk/cutoff раньше вычислялись ДО открытия SessionLocal(), т.е.
# ДО ожидания FOR UPDATE. Если бы это ожидание растянулось на произвольное
# время, проверка lead time шла бы по устаревшему "сейчас". Ниже — детерминиро-
# ванное (no-DB, без sleep/реального времени) доказательство порядка вызовов:
# lock acquired → current time read → lead-time check → mutation/audit.

_MOSCOW_TZ = timezone(timedelta(hours=3))
_FIXED_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=_MOSCOW_TZ)


class _FakeDateTime:
    """Подменяет `datetime.now()`: фиксирует момент КАЖДОГО вызова в `order`
    (для доказательства порядка) и возвращает контролируемое "сейчас" —
    без обращения к реальным часам и без sleep."""

    def __init__(self, order: list, fixed_now: datetime = _FIXED_NOW):
        self._order = order
        self._fixed_now = fixed_now

    def now(self, tz=None):
        self._order.append("now_read")
        return self._fixed_now


def _register_group_race_env(monkeypatch, order, starts_at):
    """Общая обвязка для двух тестов ниже: mock SessionLocal/lock/MeetingType/
    существующая регистрация/capacity. Возвращает (db, gs)."""
    db = _mock_session(monkeypatch)
    monkeypatch.setattr(appt_service, "datetime", _FakeDateTime(order))

    gs = _gs(starts_at=starts_at)

    def _lock(uuid_str, db_arg):
        order.append("lock_acquired")
        return gs
    monkeypatch.setattr(st, "lock_group_session_by_uuid", _lock)

    mt = SimpleNamespace(is_active=True, is_bookable=True)
    db.query.return_value.filter.return_value.first.return_value = mt

    monkeypatch.setattr(st, "get_student_registration",
                        lambda *a, **kw: None)
    monkeypatch.setattr(st, "count_active_registrations",
                        lambda *a, **kw: 0)
    return db, gs


def test_lead_time_read_after_lock_and_checks_before_mutation(monkeypatch):
    """Порядок вызовов: lock → (status/booking/meeting-type/existing/capacity
    checks, без отдельных маркеров) → now_read → mutation_and_audit.

    `starts_at` здесь заведомо вне lead time относительно `_FIXED_NOW`
    (+2 часа), поэтому путь доходит до мутации — тест проверяет именно
    ПОРЯДОК, а не факт отказа (его проверяет тест ниже).
    """
    order: list = []
    db, gs = _register_group_race_env(
        monkeypatch, order, starts_at=_FIXED_NOW + timedelta(hours=2)
    )

    def _register(gs_arg, student_id, db_arg, *, actor, context):
        order.append("mutation_and_audit")
        assert gs_arg is gs                     # тот же locked-объект
        return {"uuid": "reg-uuid"}
    monkeypatch.setattr(st, "register_student_group_session", _register)

    student = {"id": 50, "is_active": True}
    result = appt_service.student_register_group(
        "gs-uuid", student, actor_role="student")

    assert result == {"uuid": "reg-uuid"}
    # ровно один момент времени, прочитанный СТРОГО между локом и мутацией
    assert order == ["lock_acquired", "now_read", "mutation_and_audit"]
    db.commit.assert_called_once()


def test_lead_time_uses_fresh_now_not_precomputed_stale_value(monkeypatch):
    """Регрессия: если бы cutoff вычислялся ДО ожидания лока, эта регистрация
    прошла бы по устаревшему "сейчас". `starts_at` здесь ровно ВНУТРИ lead
    time относительно СВЕЖЕГО `_FIXED_NOW` (+30 минут < 1 час) — обязана
    быть отклонена ДО мутации, а `now_read` должен произойти ПОСЛЕ лока.
    """
    order: list = []
    db, gs = _register_group_race_env(
        monkeypatch, order, starts_at=_FIXED_NOW + timedelta(minutes=30)
    )

    mutated: list = []
    monkeypatch.setattr(
        st, "register_student_group_session",
        lambda *a, **kw: mutated.append(1),
    )

    student = {"id": 50, "is_active": True}
    with pytest.raises(appt_service.AppointmentError) as ei:
        appt_service.student_register_group(
            "gs-uuid", student, actor_role="student")

    assert ei.value.status_code == 422
    assert order == ["lock_acquired", "now_read"]    # мутация не достигнута
    assert mutated == []
    db.commit.assert_not_called()
