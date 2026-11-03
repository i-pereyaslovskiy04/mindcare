"""
ADR-035 — детерминированные concurrency-тесты итога встречи на реальном
PostgreSQL (lock_helpers). Все writer'ы статуса берут строку встречи FOR NO
KEY UPDATE, поэтому:

  * итог/итог: второй ждёт первого и видит свежий статус — тот же итог даёт
    no-op, другой — конфликт; success-событие ровно одно;
  * итог/отмена и итог/отклонение: незафиксированная отмена/отклонение держит
    строку, итог ждёт и получает 409 без перезаписи; итог, взявший строку
    первым, заставляет decline ждать, и тот видит completed;
  * без deadlock.
Потоки вызывают service напрямую (TestClient не потокобезопасен).
"""
import pytest
from sqlalchemy import text

import app.appointments.service as service
import app.appointments.storage as storage
from app.db.models import AuditLog
from app.db.session import SessionLocal
from tests.integration.appointment_outcome_helpers import appt_row, make_appt
from tests.integration.assignments_helpers import engage, user
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, deadlock_count, run_in_thread, wait_for_lock_waiter,
)


@pytest.fixture
def setup(client):
    sid, _ = user(client, ["student"])
    pid, _ = user(client, ["psychologist", "student"])
    engage(pid, sid)
    return {"sid": sid, "pid": pid, "appt": make_appt(pid, client_id=sid)}


def _mark(s, outcome):
    return service.psychologist_mark_outcome(
        s["appt"], {"id": str(s["pid"])}, outcome, actor_role="psychologist",
    )


def _success_events(appt_uuid):
    appt_id = appt_row(appt_uuid).id
    with SessionLocal() as db:
        return [r.event_type for r in db.query(AuditLog).filter(
            AuditLog.entity_type == "appointment", AuditLog.entity_id == appt_id,
            AuditLog.event_type.in_(("appointment_completed", "appointment_no_show")),
        ).order_by(AuditLog.id)]


@pytest.mark.parametrize("second, expected", [
    ("completed", "noop"), ("no_show", "conflict"),
])
def test_outcome_vs_outcome_serialized(setup, monkeypatch, second, expected):
    s = setup
    gate = Gate()
    monkeypatch.setattr(storage, "mark_outcome", gate.wrap(storage.mark_outcome))
    deadlocks = deadlock_count()

    first = run_in_thread(lambda: _mark(s, "completed"))
    gate.wait_reached()                         # строка взята, переход ещё не записан
    other = run_in_thread(lambda: _mark(s, second))
    wait_for_lock_waiter()                      # второй ждёт строку встречи
    gate.release.set()

    a, b = first.join(), other.join()
    assert_no_deadlock_error(a, b)
    assert a == ("ok", {"uuid": s["appt"], "status": "completed", "changed": True}), a
    if expected == "noop":
        assert b == ("ok", {"uuid": s["appt"], "status": "completed", "changed": False}), b
    else:
        assert b[0] == "error" and isinstance(b[1], service.AuditableAppointmentError)
        assert b[1].status_code == 409 and b[1].audit_code == "outcome_conflict"
    assert appt_row(s["appt"]).status == "completed"
    assert _success_events(s["appt"]) == ["appointment_completed"]
    assert deadlock_count() == deadlocks


@pytest.mark.parametrize("status", ["cancelled", "declined"])
def test_uncommitted_cancel_or_decline_makes_outcome_wait_and_fail(setup, status):
    s = setup
    holder = SessionLocal()
    try:
        holder.execute(text("UPDATE appointments SET status = :st WHERE uuid = :u"),
                       {"st": status, "u": s["appt"]})
        worker = run_in_thread(lambda: _mark(s, "completed"))
        wait_for_lock_waiter()                  # итог ждёт незафиксированную отмену
        holder.commit()
    finally:
        holder.close()
    kind, value = worker.join()
    assert kind == "error" and isinstance(value, service.AuditableAppointmentError)
    assert value.status_code == 409 and value.audit_code == "invalid_status"
    assert appt_row(s["appt"]).status == status
    assert _success_events(s["appt"]) == []


def test_outcome_holding_row_makes_decline_wait_and_see_completed(setup, monkeypatch):
    s = setup
    gate = Gate()
    monkeypatch.setattr(storage, "mark_outcome", gate.wrap(storage.mark_outcome))
    deadlocks = deadlock_count()

    marker = run_in_thread(lambda: _mark(s, "completed"))
    gate.wait_reached()
    decliner = run_in_thread(lambda: service.psychologist_decline(
        s["appt"], {"id": str(s["pid"])}, None, actor_role="psychologist"))
    wait_for_lock_waiter()                      # decline ждёт строку
    gate.release.set()

    a, b = marker.join(), decliner.join()
    assert_no_deadlock_error(a, b)
    assert a[0] == "ok" and a[1]["status"] == "completed"
    assert b[0] == "error" and isinstance(b[1], service.AppointmentError)
    assert b[1].status_code == 422                # «Нельзя отклонить статус completed»
    assert appt_row(s["appt"]).status == "completed"
    assert deadlock_count() == deadlocks
