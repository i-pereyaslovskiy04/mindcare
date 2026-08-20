"""
Stage 5B-1 — no-DB unit-тесты audit trail для individual appointments и walk-in
cards: registry contract, actor/target mapping, минимизация, фазовые границы
(business flush → audit → commit), linking (per-card, idempotency, actor A/B),
card update/archive no-op. Реальная БД не используется.
"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.appointments.storage as appt_storage
from app.audit import Actor, RequestContext
from app.audit.contracts import AuditStorageError
from app.audit.registry import REGISTRY

ACTOR = Actor.user(50, "student")
SUP_ACTOR = Actor.user(9, "supervisor")
CTX = RequestContext(ip_address="203.0.113.7", user_agent="ua")


# ══════════════════════════════════════════════════════════════════════════
# 1. Registry contract
# ══════════════════════════════════════════════════════════════════════════

_APPT_EVENTS = {
    "appointment_created": {"student", "supervisor", "admin"},
    "appointment_confirmed": {"psychologist"},
    "appointment_declined": {"psychologist"},
    "appointment_cancelled": {"student"},
    "unregistered_student_card_created": {"supervisor", "admin"},
    "unregistered_student_card_updated": {"supervisor", "admin"},
    "unregistered_student_card_archived": {"supervisor", "admin"},
    "unregistered_student_card_linked": {"student", "supervisor", "admin"},
}


def test_registry_events_and_count():
    assert len(REGISTRY) == 93
    for name, roles in _APPT_EVENTS.items():
        s = REGISTRY[name]
        assert s.destination.value == "audit_log"
        assert s.allowed_actor_roles == frozenset(roles), name
        assert s.tx_mode.value == "atomic"
        assert s.failure_policy.value == "raise"
        assert {o.value for o in s.allowed_outcomes} == {"success"}
    for name in ("appointment_created", "appointment_cancelled"):
        assert REGISTRY[name].entity_type == "appointment"
    assert REGISTRY["unregistered_student_card_created"].entity_type == \
        "unregistered_student_card"


def test_appointment_events_metadata_empty():
    for name in ("appointment_created", "appointment_confirmed",
                 "appointment_declined", "appointment_cancelled",
                 "unregistered_student_card_created",
                 "unregistered_student_card_updated",
                 "unregistered_student_card_archived"):
        assert dict(REGISTRY[name].metadata_schema) == {}, name


def test_linked_metadata_only_linked_user_id():
    schema = REGISTRY["unregistered_student_card_linked"].metadata_schema
    assert set(schema) == {"linked_user_id"}
    fs = schema["linked_user_id"]
    assert fs.type == "int" and fs.min_value == 1


# ══════════════════════════════════════════════════════════════════════════
# 2. Fail-closed actor guard (до мутации)
# ══════════════════════════════════════════════════════════════════════════

def test_create_appointment_requires_actor_context():
    db = MagicMock(name="db")
    with pytest.raises(RuntimeError):
        appt_storage.create_appointment(
            psychologist_id=1, starts_at=None, duration_minutes=50,
            modality="in_person", topic=None, meeting_type_id=1, db=db,
            client_id=50, actor=None, context=None,
        )
    db.add.assert_not_called()


def test_link_requires_actor_context():
    db = MagicMock(name="db")
    with pytest.raises(RuntimeError):
        appt_storage.link_unregistered_cards_to_user(
            50, "a@donnu.ru", db, actor=None, context=None,
        )


# ══════════════════════════════════════════════════════════════════════════
# 3. Appointment create — mapping, phase order, no sensitive data
# ══════════════════════════════════════════════════════════════════════════

def _appt(monkeypatch, calls):
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_storage, "_appointment_to_dict",
                        lambda a, db: {"uuid": "u"})


def test_create_appointment_maps_and_flush_before_audit(monkeypatch):
    calls = []
    _appt(monkeypatch, calls)
    order = []
    db = MagicMock(name="db")
    db.flush.side_effect = lambda: order.append("flush")
    appt = SimpleNamespace(id=777)
    monkeypatch.setattr(appt_storage, "Appointment", lambda **kw: appt)
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: (order.append("audit"), calls.append(kw)))
    from datetime import datetime, timezone
    appt_storage.create_appointment(
        psychologist_id=1, starts_at=datetime.now(timezone.utc),
        duration_minutes=50, modality="in_person",
        topic="секретная тема", meeting_type_id=1, db=db,
        client_id=50, actor=ACTOR, context=CTX,
    )
    assert order[0] == "flush" and "audit" in order   # flush до audit
    kw = calls[0]
    assert kw["event"] == "appointment_created"
    assert kw["actor"] is ACTOR
    assert kw["target"].entity_type == "appointment" and kw["target"].entity_id == 777
    assert kw["metadata"] == {}
    assert kw["context"] is CTX and kw["db"] is db
    # topic и прочие ПДн не в audit kwargs
    assert "секретная тема" not in repr(kw)


def test_cancel_confirm_decline_map_events(monkeypatch):
    calls = []
    _appt(monkeypatch, calls)
    db = MagicMock(name="db")
    appt = SimpleNamespace(id=321, status="pending_confirmation",
                           cancellation_reason=None, canceled_by=None,
                           updated_at=None, deleted_at=None, decline_reason=None)
    appt_storage.cancel_appointment(
        appt, canceled_by=50, reason="передумал", db=db,
        soft_delete=True, actor=ACTOR, context=CTX,
    )
    assert appt.deleted_at is not None          # soft-delete
    assert calls[0]["event"] == "appointment_cancelled"
    assert calls[0]["target"].entity_id == 321  # target даже при soft-delete
    assert "передумал" not in repr(calls[0])

    calls.clear()
    p = Actor.user(7, "psychologist")
    appt_storage.confirm_appointment(appt, db, actor=p, context=CTX)
    assert calls[0]["event"] == "appointment_confirmed"
    calls.clear()
    appt_storage.decline_appointment(appt, "не могу", db, actor=p, context=CTX)
    assert calls[0]["event"] == "appointment_declined"
    assert "не могу" not in repr(calls[0])


def test_create_appointment_audit_failure_no_commit(monkeypatch):
    monkeypatch.setattr(appt_storage, "_appointment_to_dict",
                        lambda a, db: {"uuid": "u"})

    def _boom(**kw):
        raise AuditStorageError("audit down")
    monkeypatch.setattr(appt_storage, "record_event", _boom)
    db = MagicMock(name="db")
    monkeypatch.setattr(appt_storage, "Appointment",
                        lambda **kw: SimpleNamespace(id=1))
    from datetime import datetime, timezone
    with pytest.raises(AuditStorageError):
        appt_storage.create_appointment(
            psychologist_id=1, starts_at=datetime.now(timezone.utc),
            duration_minutes=50, modality="in_person", topic=None,
            meeting_type_id=1, db=db, client_id=50, actor=ACTOR, context=CTX,
        )
    # Propagation check only: this db is the caller's own mock, passed
    # directly into storage. Storage never calls commit by design, so this
    # does NOT verify the service owner-commit boundary — see §12 for real
    # service + mocked SessionLocal tests that check that boundary.
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 4. Walk-in card update/archive no-op + create
# ══════════════════════════════════════════════════════════════════════════

def test_card_update_real_diff_writes_one(monkeypatch):
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    db = MagicMock(name="db")
    card = SimpleNamespace(id=5, full_name="Old", phone=None, updated_at=None)
    appt_storage.update_unregistered_student_card(
        card, {"full_name": "New"}, db, actor=SUP_ACTOR, context=CTX,
    )
    assert card.full_name == "New" and card.updated_at is not None
    assert len(calls) == 1
    assert calls[0]["event"] == "unregistered_student_card_updated"
    assert calls[0]["target"].entity_id == 5 and calls[0]["metadata"] == {}


@pytest.mark.parametrize("updates", [{}, {"full_name": "Same"}])
def test_card_update_noop_no_mutation_no_audit(monkeypatch, updates):
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    db = MagicMock(name="db")
    card = SimpleNamespace(id=5, full_name="Same", phone=None, updated_at=None)
    appt_storage.update_unregistered_student_card(
        card, updates, db, actor=SUP_ACTOR, context=CTX,
    )
    assert card.updated_at is None       # updated_at не сдвинут
    assert calls == []                   # нет audit
    db.flush.assert_not_called()


def test_card_archive_transition_only(monkeypatch):
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    db = MagicMock(name="db")
    card = SimpleNamespace(id=5, archived_at=None, updated_at=None)
    appt_storage.archive_unregistered_student_card(
        card, db, actor=SUP_ACTOR, context=CTX,
    )
    assert card.archived_at is not None and len(calls) == 1
    assert calls[0]["event"] == "unregistered_student_card_archived"

    # повторный archive уже архивной — no-op
    calls.clear()
    prev = card.updated_at
    appt_storage.archive_unregistered_student_card(
        card, db, actor=SUP_ACTOR, context=CTX,
    )
    assert calls == [] and card.updated_at == prev


# ══════════════════════════════════════════════════════════════════════════
# 5. Linking — per-card, idempotency, actor A/B, phase order, failure
# ══════════════════════════════════════════════════════════════════════════

def _link_db(cards):
    db = MagicMock(name="db")
    db.query.return_value.filter.return_value.all.return_value = cards
    return db


def test_link_per_card_rows_and_metadata(monkeypatch):
    calls = []
    order = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: (order.append("audit"), calls.append(kw)))
    monkeypatch.setattr(appt_storage, "normalize_email", lambda e: e)
    cards = [SimpleNamespace(id=11, linked_user_id=None, updated_at=None),
             SimpleNamespace(id=22, linked_user_id=None, updated_at=None)]
    db = _link_db(cards)
    db.flush.side_effect = lambda: order.append("flush")

    ids = appt_storage.link_unregistered_cards_to_user(
        50, "a@donnu.ru", db, actor=ACTOR, context=CTX,
    )
    assert ids == [11, 22]                       # список id
    assert order[0] == "flush"                   # business flush ДО первого audit
    assert order.count("audit") == 2
    assert {c["target"].entity_id for c in calls} == {11, 22}   # уникальные target
    for c in calls:
        assert c["event"] == "unregistered_student_card_linked"
        assert c["metadata"] == {"linked_user_id": 50}          # только subject id
        assert c["actor"] is ACTOR                              # A: student
    for card in cards:
        assert card.linked_user_id == 50


def test_link_idempotent_zero_cards(monkeypatch):
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_storage, "normalize_email", lambda e: e)
    db = _link_db([])   # linked-to-other/уже привязанные не попадают в выборку
    ids = appt_storage.link_unregistered_cards_to_user(
        50, "a@donnu.ru", db, actor=ACTOR, context=CTX,
    )
    assert ids == [] and calls == []
    db.flush.assert_not_called()


def test_link_staff_actor_role(monkeypatch):
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_storage, "normalize_email", lambda e: e)
    cards = [SimpleNamespace(id=11, linked_user_id=None, updated_at=None)]
    db = _link_db(cards)
    appt_storage.link_unregistered_cards_to_user(
        60, "b@donnu.ru", db, actor=SUP_ACTOR, context=CTX,   # B: staff
    )
    assert calls[0]["actor"] is SUP_ACTOR
    assert calls[0]["metadata"] == {"linked_user_id": 60}


def test_link_second_record_event_failure_no_commit(monkeypatch):
    monkeypatch.setattr(appt_storage, "normalize_email", lambda e: e)
    seen = {"n": 0}

    def _rec(**kw):
        seen["n"] += 1
        if seen["n"] == 2:
            raise AuditStorageError("audit down on 2nd card")
    monkeypatch.setattr(appt_storage, "record_event", _rec)
    cards = [SimpleNamespace(id=11, linked_user_id=None, updated_at=None),
             SimpleNamespace(id=22, linked_user_id=None, updated_at=None)]
    db = _link_db(cards)
    with pytest.raises(AuditStorageError):
        appt_storage.link_unregistered_cards_to_user(
            50, "a@donnu.ru", db, actor=ACTOR, context=CTX,
        )
    # Propagation check only (see §12 for the service owner-commit boundary).
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 6. Service linking возвращает int (linked_cards_count)
# ══════════════════════════════════════════════════════════════════════════

def test_service_link_returns_int(monkeypatch):
    import app.appointments.service as appt_service
    monkeypatch.setattr(
        appt_service.storage, "link_unregistered_cards_to_user",
        lambda *a, **kw: [11, 22],
    )
    db = MagicMock(name="db")
    sess = MagicMock()
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(appt_service, "SessionLocal", sess)
    n = appt_service.link_unregistered_cards_to_user(
        50, "a@donnu.ru", actor_id=50, actor_role="student",
    )
    assert n == 2 and isinstance(n, int)
    db.commit.assert_called_once()


# ══════════════════════════════════════════════════════════════════════════
# 7. Static: нет прямого AuditLog writer в appointments
# ══════════════════════════════════════════════════════════════════════════

def test_no_direct_auditlog_writer_in_appointments():
    root = Path(__file__).resolve().parents[1] / "app" / "appointments"
    for p in root.rglob("*.py"):
        assert "AuditLog(" not in p.read_text(encoding="utf-8"), p.name


# ══════════════════════════════════════════════════════════════════════════
# 8. Strengthened _require_actor: system/anonymous/None-id/empty-role → reject
# ══════════════════════════════════════════════════════════════════════════

from datetime import datetime, timezone   # noqa: E402


@pytest.mark.parametrize("actor,ctx", [
    (Actor.system(), CTX),
    (Actor.anonymous(), CTX),
    (Actor.user(None, "student"), CTX),      # user_id None
    (Actor.user(0, "student"), CTX),         # user_id <= 0
    (Actor.user(True, "student"), CTX),      # bool не int
    (Actor.user(5, ""), CTX),                # пустая роль
    (Actor.user(5, None), CTX),              # роль None
    (ACTOR, None),                            # context не RequestContext
    (ACTOR, object()),                        # context неверный тип
])
def test_require_actor_rejects_before_mutation(actor, ctx):
    db = MagicMock(name="db")
    monkey_appt = SimpleNamespace(id=1)
    import app.appointments.storage as st
    orig = st.Appointment
    st.Appointment = lambda **kw: monkey_appt
    try:
        with pytest.raises(RuntimeError):
            st.create_appointment(
                psychologist_id=1, starts_at=datetime.now(timezone.utc),
                duration_minutes=50, modality="in_person", topic=None,
                meeting_type_id=1, db=db, client_id=5, actor=actor, context=ctx,
            )
    finally:
        st.Appointment = orig
    db.add.assert_not_called()
    db.flush.assert_not_called()


def test_require_actor_rejects_card_update_before_setattr():
    db = MagicMock(name="db")
    card = SimpleNamespace(id=5, full_name="Old", updated_at=None)
    with pytest.raises(RuntimeError):
        appt_storage.update_unregistered_student_card(
            card, {"full_name": "New"}, db,
            actor=Actor.system(), context=CTX,
        )
    assert card.full_name == "Old" and card.updated_at is None
    db.flush.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 9. Signature contract: actor_role/current_user без default
# ══════════════════════════════════════════════════════════════════════════

def test_service_actor_role_has_no_default():
    import inspect
    import app.appointments.service as svc
    for fn_name in ("book_appointment", "student_cancel",
                    "psychologist_confirm", "psychologist_decline",
                    "supervisor_book_appointment",
                    "create_unregistered_student_card",
                    "update_unregistered_student_card",
                    "archive_unregistered_student_card"):
        sig = inspect.signature(getattr(svc, fn_name))
        p = sig.parameters["actor_role"]
        assert p.default is inspect.Parameter.empty, fn_name


def test_service_current_user_required_for_staff():
    import inspect
    import app.appointments.service as svc
    for fn_name in ("supervisor_book_appointment",
                    "create_unregistered_student_card",
                    "update_unregistered_student_card",
                    "archive_unregistered_student_card"):
        p = inspect.signature(getattr(svc, fn_name)).parameters["current_user"]
        assert p.default is inspect.Parameter.empty, fn_name


def test_storage_actor_context_required():
    import inspect
    for fn_name in ("create_appointment", "cancel_appointment",
                    "confirm_appointment", "decline_appointment",
                    "create_unregistered_student_card",
                    "update_unregistered_student_card",
                    "archive_unregistered_student_card",
                    "link_unregistered_cards_to_user"):
        sig = inspect.signature(getattr(appt_storage, fn_name))
        for name in ("actor", "context"):
            p = sig.parameters[name]
            assert p.default is inspect.Parameter.empty, f"{fn_name}.{name}"
            assert p.kind == inspect.Parameter.KEYWORD_ONLY


# ══════════════════════════════════════════════════════════════════════════
# 10. Audit failure injection per writer → propagates, storage не коммитит
# ══════════════════════════════════════════════════════════════════════════

def _boom(**kw):
    raise AuditStorageError("audit down")


def test_confirm_decline_cancel_audit_failure_propagate(monkeypatch):
    monkeypatch.setattr(appt_storage, "_appointment_to_dict",
                        lambda a, db: {"uuid": "u"})
    monkeypatch.setattr(appt_storage, "record_event", _boom)
    db = MagicMock(name="db")
    appt = SimpleNamespace(id=1, status="pending_confirmation",
                           cancellation_reason=None, canceled_by=None,
                           updated_at=None, deleted_at=None, decline_reason=None)
    p = Actor.user(7, "psychologist")
    for call in (
        lambda: appt_storage.confirm_appointment(appt, db, actor=p, context=CTX),
        lambda: appt_storage.decline_appointment(appt, "r", db, actor=p, context=CTX),
        lambda: appt_storage.cancel_appointment(
            appt, canceled_by=5, reason="r", db=db, soft_delete=True,
            actor=ACTOR, context=CTX),
    ):
        with pytest.raises(AuditStorageError):
            call()
    # Propagation check only (see §12 for the service owner-commit boundary).
    db.commit.assert_not_called()


def test_card_create_update_archive_audit_failure_propagate(monkeypatch):
    monkeypatch.setattr(appt_storage, "_card_to_dict", lambda c: {"id": c.id})
    monkeypatch.setattr(appt_storage, "record_event", _boom)
    db = MagicMock(name="db")
    # create
    monkeypatch.setattr(appt_storage, "UnregisteredStudentCard",
                        lambda **kw: SimpleNamespace(id=1))
    with pytest.raises(AuditStorageError):
        appt_storage.create_unregistered_student_card(
            {"full_name": "x"}, db, actor=SUP_ACTOR, context=CTX)
    # update (real diff)
    card = SimpleNamespace(id=5, full_name="Old", updated_at=None)
    with pytest.raises(AuditStorageError):
        appt_storage.update_unregistered_student_card(
            card, {"full_name": "New"}, db, actor=SUP_ACTOR, context=CTX)
    # archive (real transition)
    card2 = SimpleNamespace(id=6, archived_at=None, updated_at=None)
    with pytest.raises(AuditStorageError):
        appt_storage.archive_unregistered_student_card(
            card2, db, actor=SUP_ACTOR, context=CTX)
    # Propagation check only (see §12 for the service owner-commit boundary).
    db.commit.assert_not_called()


class _FlushSentinel(Exception):
    pass


def test_link_flush_failure_no_record_event_no_commit(monkeypatch):
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    monkeypatch.setattr(appt_storage, "normalize_email", lambda e: e)
    cards = [SimpleNamespace(id=11, linked_user_id=None, updated_at=None)]
    db = _link_db(cards)
    db.flush.side_effect = _FlushSentinel("flush boom")
    with pytest.raises(_FlushSentinel):
        appt_storage.link_unregistered_cards_to_user(
            50, "a@donnu.ru", db, actor=ACTOR, context=CTX)
    assert calls == []                # record_event не вызван (flush до audit)
    # Propagation check only (see §12 for the service owner-commit boundary).
    db.commit.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════
# 11. Route acting-role: _sup_role (item 5)
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("roles,expected", [
    (["admin"], "admin"),
    (["supervisor"], "supervisor"),
    (["admin", "supervisor"], "supervisor"),
])
def test_sup_role_resolution(roles, expected):
    import app.appointments.routes_supervisor as rs
    assert rs._sup_role({"id": "1", "roles": roles}) == expected


# ══════════════════════════════════════════════════════════════════════════
# 12. Service-level owner-commit boundary (corrective pass, final item 1):
# real service function + mocked SessionLocal. The storage writer raises
# AuditStorageError (or, for linking, a real storage writer runs against a
# mocked db and record_event/db.flush is made to fail) → exception
# propagates out of the service call, and the service owner's db.commit()
# — the session opened by `with SessionLocal() as db:` inside the service
# function itself — is never reached. Postcommit notifications (where they
# exist) are not invoked either, since they sit after the `with` block.
#
# NB: §3/§10 above assert `db.commit.assert_not_called()` on a db MagicMock
# passed DIRECTLY into a storage function call. That only confirms storage
# itself never calls commit (true by construction — storage never commits).
# It does not exercise the service's own transaction boundary. The tests
# below mock `SessionLocal` and call the real service function, so `db` here
# IS the service owner's session — this is the actual owner-commit check.
#
# We do not assert an actual rollback on the MagicMock session; a real
# SessionLocal context manager rolls back on exit-with-exception, but that
# behaviour belongs to SQLAlchemy, not to this code path.
# ══════════════════════════════════════════════════════════════════════════
from datetime import timedelta as _timedelta   # noqa: E402

import app.appointments.service as appt_service   # noqa: E402


def _mock_session(monkeypatch, module):
    """Mock module.SessionLocal so `with SessionLocal() as db` yields db.
    Returns the db MagicMock — the service owner's session."""
    db = MagicMock(name="owner_db")
    sess = MagicMock(name="SessionLocal")
    sess.return_value.__enter__ = MagicMock(return_value=db)
    sess.return_value.__exit__ = MagicMock(return_value=False)
    monkeypatch.setattr(module, "SessionLocal", sess)
    return db


def _svc_boom(*a, **kw):
    raise AuditStorageError("audit down")


def test_book_appointment_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    engagement = SimpleNamespace(id=1, psychologist_id=7)
    monkeypatch.setattr(appt_service.storage, "get_active_engagement",
                        lambda **kw: engagement)
    mt = SimpleNamespace(id=1, duration_minutes=50, allow_in_person=True,
                         allow_online=True, is_active=True, is_bookable=True,
                         is_group=False)
    monkeypatch.setattr(appt_service, "_load_individual_meeting_type",
                        lambda mtid, db: mt)
    monkeypatch.setattr(appt_service.storage, "is_valid_structural_slot",
                        lambda *a, **kw: True)
    monkeypatch.setattr(appt_service.storage, "acquire_slot_lock",
                        lambda *a, **kw: None)
    monkeypatch.setattr(appt_service.storage, "is_slot_blocked",
                        lambda *a, **kw: False)
    monkeypatch.setattr(appt_service.storage, "is_group_session_overlap",
                        lambda *a, **kw: False)
    monkeypatch.setattr(appt_service.storage, "create_appointment", _svc_boom)
    notified = []
    monkeypatch.setattr(appt_service, "_notify_new_appointment",
                        lambda **kw: notified.append(1))
    student = {"id": 50, "is_active": True}
    starts_at = datetime.now(timezone.utc) + _timedelta(hours=5)
    with pytest.raises(AuditStorageError):
        appt_service.book_appointment(
            student, starts_at, "in_person", None, 1, actor_role="student",
        )
    db.commit.assert_not_called()
    assert notified == []


def test_supervisor_book_appointment_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    monkeypatch.setattr(appt_service.storage, "is_psychologist",
                        lambda *a, **kw: True)
    student = SimpleNamespace(is_active=True)
    monkeypatch.setattr(appt_service.storage, "get_user",
                        lambda *a, **kw: student)
    engagement = SimpleNamespace(id=2)
    monkeypatch.setattr(appt_service.storage, "get_active_engagement_with",
                        lambda *a, **kw: engagement)
    mt = SimpleNamespace(id=1, duration_minutes=50, allow_in_person=True,
                         allow_online=True, is_active=True, is_bookable=True,
                         is_group=False)
    monkeypatch.setattr(appt_service, "_load_individual_meeting_type",
                        lambda mtid, db: mt)
    monkeypatch.setattr(appt_service.storage, "is_valid_structural_slot",
                        lambda *a, **kw: True)
    monkeypatch.setattr(appt_service.storage, "acquire_slot_lock",
                        lambda *a, **kw: None)
    monkeypatch.setattr(appt_service.storage, "is_slot_blocked",
                        lambda *a, **kw: False)
    monkeypatch.setattr(appt_service.storage, "is_group_session_overlap",
                        lambda *a, **kw: False)
    monkeypatch.setattr(appt_service.storage, "create_appointment", _svc_boom)
    notified = []
    monkeypatch.setattr(appt_service, "_notify_supervisor_appointment",
                        lambda *a, **kw: notified.append(1))
    starts_at = datetime.now(timezone.utc) + _timedelta(hours=5)
    with pytest.raises(AuditStorageError):
        appt_service.supervisor_book_appointment(
            psychologist_id=7, meeting_type_id=1, starts_at=starts_at,
            modality="in_person", topic=None, student_id=50,
            current_user={"id": 9}, actor_role="supervisor",
        )
    db.commit.assert_not_called()
    assert notified == []


def test_student_cancel_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    appt = SimpleNamespace(
        id=1, client_id=50, unregistered_student_card_id=None,
        status="pending_confirmation",
        starts_at=datetime.now(timezone.utc) + _timedelta(days=5),
        psychologist_id=7,
    )
    monkeypatch.setattr(appt_service.storage, "get_appointment_by_uuid",
                        lambda *a, **kw: appt)
    monkeypatch.setattr(appt_service.storage, "cancel_appointment", _svc_boom)
    notified = []
    monkeypatch.setattr(appt_service, "_notify_cancelled",
                        lambda **kw: notified.append(1))
    with pytest.raises(AuditStorageError):
        appt_service.student_cancel(
            "uuid-x", {"id": 50}, "reason", actor_role="student",
        )
    db.commit.assert_not_called()
    assert notified == []


def test_psychologist_confirm_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    appt = SimpleNamespace(id=1, psychologist_id=7,
                           status="pending_confirmation",
                           client_id=50, unregistered_student_card_id=None)
    monkeypatch.setattr(appt_service.storage, "get_appointment_by_uuid",
                        lambda *a, **kw: appt)
    monkeypatch.setattr(appt_service.storage, "confirm_appointment",
                        _svc_boom)
    notified = []
    monkeypatch.setattr(appt_service, "_notify_confirmed",
                        lambda **kw: notified.append(1))
    with pytest.raises(AuditStorageError):
        appt_service.psychologist_confirm(
            "uuid-x", {"id": 7}, actor_role="psychologist",
        )
    db.commit.assert_not_called()
    assert notified == []


def test_psychologist_decline_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    appt = SimpleNamespace(id=1, psychologist_id=7,
                           status="pending_confirmation",
                           client_id=50, unregistered_student_card_id=None)
    monkeypatch.setattr(appt_service.storage, "get_appointment_by_uuid",
                        lambda *a, **kw: appt)
    monkeypatch.setattr(appt_service.storage, "decline_appointment",
                        _svc_boom)
    notified = []
    monkeypatch.setattr(appt_service, "_notify_declined",
                        lambda **kw: notified.append(1))
    with pytest.raises(AuditStorageError):
        appt_service.psychologist_decline(
            "uuid-x", {"id": 7}, "reason", actor_role="psychologist",
        )
    db.commit.assert_not_called()
    assert notified == []


def test_card_create_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    monkeypatch.setattr(appt_service.storage,
                        "create_unregistered_student_card", _svc_boom)
    with pytest.raises(AuditStorageError):
        appt_service.create_unregistered_student_card(
            {"full_name": "X", "personal_data_consent": True},
            {"id": 9}, actor_role="supervisor",
        )
    db.commit.assert_not_called()


def test_card_update_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    card = SimpleNamespace(id=5)
    monkeypatch.setattr(appt_service.storage, "get_unregistered_student_card",
                        lambda *a, **kw: card)
    monkeypatch.setattr(appt_service.storage,
                        "update_unregistered_student_card", _svc_boom)
    with pytest.raises(AuditStorageError):
        appt_service.update_unregistered_student_card(
            5, {"full_name": "Y"}, current_user={"id": 9},
            actor_role="supervisor",
        )
    db.commit.assert_not_called()


def test_card_archive_service_commit_not_reached(monkeypatch):
    db = _mock_session(monkeypatch, appt_service)
    card = SimpleNamespace(id=5)
    monkeypatch.setattr(appt_service.storage, "get_unregistered_student_card",
                        lambda *a, **kw: card)
    monkeypatch.setattr(appt_service.storage,
                        "archive_unregistered_student_card", _svc_boom)
    with pytest.raises(AuditStorageError):
        appt_service.archive_unregistered_student_card(
            5, current_user={"id": 9}, actor_role="supervisor",
        )
    db.commit.assert_not_called()


def test_link_service_flush_failure_no_record_event_no_commit(monkeypatch):
    """Linking: real service + real storage writer, mocked db. Business flush
    fails → record_event never called → service owner commit not reached."""
    db = _mock_session(monkeypatch, appt_service)
    monkeypatch.setattr(appt_storage, "normalize_email", lambda e: e)
    cards = [SimpleNamespace(id=11, linked_user_id=None, updated_at=None)]
    db.query.return_value.filter.return_value.all.return_value = cards
    db.flush.side_effect = _FlushSentinel("flush boom")
    calls = []
    monkeypatch.setattr(appt_storage, "record_event",
                        lambda **kw: calls.append(kw))
    with pytest.raises(_FlushSentinel):
        appt_service.link_unregistered_cards_to_user(
            50, "a@donnu.ru", actor_id=50, actor_role="student",
        )
    assert calls == []
    db.commit.assert_not_called()


def test_link_service_second_record_event_failure_no_commit(monkeypatch):
    """Linking: real service + real storage writer, mocked db. Second card's
    record_event fails → service owner commit not reached."""
    db = _mock_session(monkeypatch, appt_service)
    monkeypatch.setattr(appt_storage, "normalize_email", lambda e: e)
    cards = [SimpleNamespace(id=11, linked_user_id=None, updated_at=None),
             SimpleNamespace(id=22, linked_user_id=None, updated_at=None)]
    db.query.return_value.filter.return_value.all.return_value = cards
    seen = {"n": 0}

    def _rec(**kw):
        seen["n"] += 1
        if seen["n"] == 2:
            raise AuditStorageError("audit down on 2nd card")
    monkeypatch.setattr(appt_storage, "record_event", _rec)
    with pytest.raises(AuditStorageError):
        appt_service.link_unregistered_cards_to_user(
            50, "a@donnu.ru", actor_id=50, actor_role="student",
        )
    db.commit.assert_not_called()
