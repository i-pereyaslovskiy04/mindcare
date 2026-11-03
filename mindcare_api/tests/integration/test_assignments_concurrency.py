"""
ADR-033 — детерминированные concurrency-тесты заданий на реальном PostgreSQL
(lock_helpers: Gate + ожидание row-lock waiter'а).

  * закрытие сопровождения ДО мутации: FOR SHARE ждёт commit закрытия и
    видит свежую строку → выполнение отклонено (409), задание осталось active;
  * мутация ДО закрытия: UPDATE сопровождения ждёт commit выполнения → задание
    выполнено, связь закрыта после него; состояние согласовано;
  * выполнение vs отмена: ровно один переход побеждает, completed и cancelled
    не перезаписывают друг друга, success-событие ровно одно;
  * чтение психологом: передача/закрытие НЕ может зафиксироваться между
    проверкой доступа и выборкой страницы (FOR SHARE держит право на всём
    чтении); чтение, начавшееся раньше закрытия, заканчивается до него;
    закрытие, зафиксированное раньше, — тексты не отдаются;
  * то же для отключения/удаления клиента (строка users под FOR SHARE): оба
    порядка фиксации, единый 404 + assignment_read_failed, без content_read.
Потоки вызывают storage/service напрямую (TestClient не потокобезопасен).
"""
import uuid

import pytest
from sqlalchemy import text

from sqlalchemy.exc import OperationalError

import app.assignments.service as service
import app.users.storage as users_storage
import app.assignments.storage as storage
import app.supervisor.service as sup_service
from app.assignments.context import PsychologistContext
from app.assignments.errors import (
    AssignmentEngagementInactive, AssignmentFinalized, AssignmentNotAvailable,
)
from app.db.models import AuditLog, TherapyEngagement
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import (
    NO_STORE, SECRET, assert_failure_row, audit_since, auth, client_url, create_ok,
    engage, marks, row, user, uuid_of,
)
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, deadlock_count, run_in_thread, wait_for_lock_waiter,
)


@pytest.fixture
def setup(client):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    sup_id, _ = user(client, ["supervisor", "student"])
    eng = engage(pid, sid)
    a_uuid = create_ok(client, ptoken, sid)
    return {"sid": sid, "pid": pid, "ptoken": ptoken, "sup": sup_id, "eng": eng,
            "uuid": uuid.UUID(a_uuid)}


def _success_events(assignment_id):
    with SessionLocal() as db:
        return [r.event_type for r in db.query(AuditLog).filter(
            AuditLog.entity_type == "assignment", AuditLog.entity_id == assignment_id,
            AuditLog.event_type.in_(("assignment_completed", "assignment_cancelled")),
        ).order_by(AuditLog.id)]


def test_close_committed_first_rejects_completion(setup):
    s = setup
    deadlocks = deadlock_count()
    closer = SessionLocal()
    try:
        closer.execute(text(
            "UPDATE therapy_engagements SET status = 'completed', ended_at = now() "
            "WHERE id = :id"), {"id": s["eng"]})
        worker = run_in_thread(lambda: storage.complete_atomic(s["sid"], s["uuid"]))
        wait_for_lock_waiter()               # FOR SHARE ждёт незафиксированное закрытие
        closer.commit()
    finally:
        closer.close()
    kind, value = worker.join()
    assert kind == "error" and isinstance(value, AssignmentEngagementInactive), value
    stored = row(s["uuid"])
    assert stored.status == "active" and stored.completed_at is None
    assert _success_events(stored.id) == []
    assert deadlock_count() == deadlocks


def test_completion_holding_lock_makes_close_wait(setup, monkeypatch):
    s = setup
    gate = Gate()
    monkeypatch.setattr(storage, "_commit", gate.wrap(storage._commit))
    deadlocks = deadlock_count()
    worker = run_in_thread(lambda: storage.complete_atomic(s["sid"], s["uuid"]))
    gate.wait_reached()                      # FOR SHARE взят, UPDATE задания сделан
    closer = run_in_thread(lambda: sup_service.close_engagement(
        s["eng"], None, s["sup"], "supervisor"))
    wait_for_lock_waiter()                   # UPDATE сопровождения ждёт нашу блокировку
    gate.release.set()
    w, c = worker.join(), closer.join()
    assert_no_deadlock_error(w, c)
    assert w[0] == "ok" and w[1]["status"] == "completed", w
    assert c[0] == "ok" and c[1]["status"] == "completed", c
    stored = row(s["uuid"])
    assert stored.status == "completed"
    assert _success_events(stored.id) == ["assignment_completed"]
    assert deadlock_count() == deadlocks


def test_cancel_wins_before_complete_update(setup, monkeypatch):
    s = setup
    gate = Gate()
    monkeypatch.setattr(storage, "_transition", gate.wrap(storage._transition))
    worker = run_in_thread(lambda: storage.complete_atomic(s["sid"], s["uuid"]))
    gate.wait_reached()                      # complete прочитал active и ждёт у UPDATE
    cancelled = storage.cancel_atomic(s["pid"], s["uuid"])
    assert cancelled["status"] == "cancelled" and cancelled["changed"] is True
    gate.release.set()
    kind, value = worker.join()
    assert kind == "error" and isinstance(value, AssignmentFinalized), value
    assert value.current_status == "cancelled"
    stored = row(s["uuid"])
    assert stored.status == "cancelled" and stored.completed_at is None
    assert _success_events(stored.id) == ["assignment_cancelled"]


def test_cancel_waits_for_uncommitted_completion(setup, monkeypatch):
    s = setup
    gate = Gate()
    monkeypatch.setattr(storage, "_commit", gate.wrap(storage._commit))
    deadlocks = deadlock_count()
    worker = run_in_thread(lambda: storage.complete_atomic(s["sid"], s["uuid"]))
    gate.wait_reached()                      # строка задания уже обновлена, commit не сделан
    canceller = run_in_thread(lambda: storage.cancel_atomic(s["pid"], s["uuid"]))
    wait_for_lock_waiter()                   # условный UPDATE отмены ждёт строку задания
    gate.release.set()
    w, c = worker.join(), canceller.join()
    assert_no_deadlock_error(w, c)
    assert w[0] == "ok" and w[1]["status"] == "completed"
    assert c[0] == "error" and isinstance(c[1], AssignmentFinalized), c
    assert c[1].current_status == "completed"
    stored = row(s["uuid"])
    assert stored.status == "completed" and stored.cancelled_at is None
    assert _success_events(stored.id) == ["assignment_completed"]
    assert deadlock_count() == deadlocks


# ── чтение психологом против закрытия / передачи ─────────────────────────────

def _engagement_state(eng_id):
    with SessionLocal() as db:
        eng = db.get(TherapyEngagement, eng_id)
        return eng.status, eng.ended_at


def _read(s):
    return storage.list_psychologist_page(s["pid"], uuid.UUID(uuid_of(s["sid"])), None, 20)


def _content_reads(pid):
    with SessionLocal() as db:
        return db.query(AuditLog).filter(
            AuditLog.event_type == "assignment_content_read", AuditLog.user_id == pid,
        ).count()


def test_transfer_cannot_commit_between_access_check_and_page_read(setup, monkeypatch):
    """
    Второе соединение пытается зафиксировать передачу ровно в промежутке между
    проверкой права и выборкой страницы. Без блокировки передача прошла бы, и
    прежний психолог прочитал бы тексты по engagement_id. С FOR SHARE UPDATE
    сопровождения не может взять строку (lock_timeout) — право сохраняется до
    конца чтения, а после чтения передача проходит и доступ пропадает.
    """
    s = setup
    attempt = {}
    real_page = storage._page

    def page_after_racing_transfer(db, scope, cursor, size):
        other = SessionLocal()                      # второе соединение
        try:
            other.execute(text("SET LOCAL lock_timeout = '300ms'"))
            other.execute(text(
                "UPDATE therapy_engagements SET status = 'transferred', ended_at = now() "
                "WHERE id = :id"), {"id": s["eng"]})
            other.commit()
            attempt["committed"] = True
        except OperationalError as exc:
            other.rollback()
            attempt["committed"] = False
            attempt["pgcode"] = getattr(exc.orig, "pgcode", None)
        finally:
            other.close()
        return real_page(db, scope, cursor, size)

    monkeypatch.setattr(storage, "_page", page_after_racing_transfer)
    page = _read(s)
    monkeypatch.undo()

    assert attempt == {"committed": False, "pgcode": "55P03"}   # lock_not_available
    assert _engagement_state(s["eng"]) == ("active", None)
    # текст получен, пока право действительно было
    assert [r["text"] for r in page["rows"]] == [SECRET]

    # передача после чтения проходит — прежний психолог больше ничего не получает
    with SessionLocal() as db:
        db.execute(text(
            "UPDATE therapy_engagements SET status = 'transferred', ended_at = now() "
            "WHERE id = :id"), {"id": s["eng"]})
        db.commit()
    assert _read(s) is None


def test_read_started_before_close_finishes_before_close_commits(setup, monkeypatch):
    """Чтение взяло право первым: закрытие ждёт конца чтения, затем доступ пропадает."""
    s = setup
    gate = Gate()
    monkeypatch.setattr(storage, "_page", gate.wrap(storage._page))
    deadlocks = deadlock_count()
    reads_before = _content_reads(s["pid"])

    reader = run_in_thread(lambda: service.list_for_client(
        PsychologistContext(s["pid"]), uuid.UUID(uuid_of(s["sid"])), None, 20))
    gate.wait_reached()                     # право проверено (FOR SHARE), выборки ещё нет
    closer = run_in_thread(lambda: sup_service.close_engagement(
        s["eng"], None, s["sup"], "supervisor"))
    wait_for_lock_waiter()                  # UPDATE сопровождения ждёт конца чтения
    assert _engagement_state(s["eng"])[0] == "active"
    gate.release.set()

    r, c = reader.join(), closer.join()
    assert_no_deadlock_error(r, c)
    assert r[0] == "ok", r
    assert [i["text"] for i in r[1]["items"]] == [SECRET]
    assert _content_reads(s["pid"]) == reads_before + 1      # fail-closed аудит сохранён
    assert c[0] == "ok" and c[1]["status"] == "completed", c
    assert deadlock_count() == deadlocks

    # после закрытия: тексты не отдаются, событие чтения не пишется
    with pytest.raises(AssignmentNotAvailable):
        service.list_for_client(PsychologistContext(s["pid"]), uuid.UUID(uuid_of(s["sid"])), None, 20)
    assert _content_reads(s["pid"]) == reads_before + 1


@pytest.mark.parametrize("new_status", ["completed", "transferred"])
def test_close_committed_before_read_returns_nothing(setup, new_status):
    """Закрытие/передача взяли строку первыми: чтение ждёт и видит потерю права."""
    s = setup
    reads_before = _content_reads(s["pid"])
    closer = SessionLocal()
    try:
        closer.execute(text(
            "UPDATE therapy_engagements SET status = :st, ended_at = now() WHERE id = :id"),
            {"st": new_status, "id": s["eng"]})
        reader = run_in_thread(lambda: service.list_for_client(
            PsychologistContext(s["pid"]), uuid.UUID(uuid_of(s["sid"])), None, 20))
        wait_for_lock_waiter()              # FOR SHARE ждёт незафиксированное закрытие
        closer.commit()
    finally:
        closer.close()
    kind, value = reader.join()
    assert kind == "error" and isinstance(value, AssignmentNotAvailable), value
    assert SECRET not in repr(value)
    assert _content_reads(s["pid"]) == reads_before


# ── чтение психологом против отключения / удаления клиента ────────────────────

_CLIENT_CHANGES = {
    "deactivated": "UPDATE users SET is_active = false WHERE id = :id",
    "deleted": "UPDATE users SET deleted_at = now() WHERE id = :id",
}


def _client_state(uid):
    with SessionLocal() as db:
        return db.execute(text(
            "SELECT is_active, deleted_at FROM users WHERE id = :id"), {"id": uid}).one()


def _assert_api_denied(client, s):
    """После потери права: единый 404 + assignment_read_failed, без content_read."""
    m = marks()
    r = client.get(client_url_by_uuid(s), headers=auth(s["ptoken"]))
    assert r.status_code == 404 and r.headers["cache-control"] == NO_STORE
    assert r.json() == {"detail": "Задание недоступно", "code": "assignment_not_available"}
    assert SECRET not in r.text
    (fail,) = audit_since(m)
    assert_failure_row(fail, "assignment_read_failed", s["pid"], "psychologist", "access_denied")


def client_url_by_uuid(s):
    return f"/api/psychologist/clients/{s['client_uuid']}/assignments"


@pytest.mark.parametrize("change", sorted(_CLIENT_CHANGES))
def test_client_disable_cannot_commit_between_access_check_and_page_read(
    setup, monkeypatch, change,
):
    """
    Второе соединение пытается отключить/удалить клиента ровно между проверкой
    права и выборкой страницы. Строка users под FOR SHARE: UPDATE не берёт её
    (lock_timeout) — право сохраняется до конца чтения; после чтения изменение
    проходит, и тексты больше не отдаются.
    """
    s = setup
    attempt = {}
    real_page = storage._page
    deadlocks = deadlock_count()

    def page_after_racing_disable(db, scope, cursor, size):
        other = SessionLocal()                      # второе соединение
        try:
            other.execute(text("SET LOCAL lock_timeout = '300ms'"))
            other.execute(text(_CLIENT_CHANGES[change]), {"id": s["sid"]})
            other.commit()
            attempt["committed"] = True
        except OperationalError as exc:
            other.rollback()
            attempt["committed"] = False
            attempt["pgcode"] = getattr(exc.orig, "pgcode", None)
        finally:
            other.close()
        return real_page(db, scope, cursor, size)

    monkeypatch.setattr(storage, "_page", page_after_racing_disable)
    page = _read(s)
    monkeypatch.undo()

    assert attempt == {"committed": False, "pgcode": "55P03"}   # lock_not_available
    state = _client_state(s["sid"])
    assert state.is_active is not False and state.deleted_at is None
    assert [r["text"] for r in page["rows"]] == [SECRET]

    with SessionLocal() as db:
        db.execute(text(_CLIENT_CHANGES[change]), {"id": s["sid"]})
        db.commit()
    assert _read(s) is None
    assert deadlock_count() == deadlocks


def test_read_started_before_client_deactivation(client, setup, monkeypatch):
    """Чтение взяло право первым: настоящее отключение (ADR-028) ждёт конца чтения."""
    s = setup
    s["client_uuid"] = uuid_of(s["sid"])
    admin_id, _ = user(client, ["admin"])
    gate = Gate()
    monkeypatch.setattr(storage, "_page", gate.wrap(storage._page))
    deadlocks = deadlock_count()
    reads_before = _content_reads(s["pid"])

    reader = run_in_thread(lambda: service.list_for_client(
        PsychologistContext(s["pid"]), uuid.UUID(s["client_uuid"]), None, 20))
    gate.wait_reached()                     # право проверено под FOR SHARE, выборки ещё нет
    disabler = run_in_thread(lambda: users_storage.deactivate_user(
        s["client_uuid"], "Причина отключения", actor_id=admin_id, actor_role="admin"))
    wait_for_lock_waiter()                  # users FOR UPDATE ждёт конца чтения
    assert _client_state(s["sid"]).is_active is not False
    gate.release.set()

    r, d = reader.join(), disabler.join()
    assert_no_deadlock_error(r, d)
    assert r[0] == "ok", r
    assert [i["text"] for i in r[1]["items"]] == [SECRET]
    assert _content_reads(s["pid"]) == reads_before + 1      # fail-closed аудит сохранён
    assert d[0] == "ok", d
    assert _client_state(s["sid"]).is_active is False
    assert deadlock_count() == deadlocks

    monkeypatch.undo()
    _assert_api_denied(client, s)
    assert _content_reads(s["pid"]) == reads_before + 1


@pytest.mark.parametrize("change", sorted(_CLIENT_CHANGES))
def test_client_disable_committed_before_read_returns_nothing(client, setup, change):
    """Отключение/удаление взяло строку users первым: чтение ждёт и видит потерю права."""
    s = setup
    s["client_uuid"] = uuid_of(s["sid"])
    deadlocks = deadlock_count()
    reads_before = _content_reads(s["pid"])
    disabler = SessionLocal()
    try:
        disabler.execute(text(_CLIENT_CHANGES[change]), {"id": s["sid"]})
        reader = run_in_thread(lambda: service.list_for_client(
            PsychologistContext(s["pid"]), uuid.UUID(s["client_uuid"]), None, 20))
        wait_for_lock_waiter()              # FOR SHARE ждёт незафиксированное изменение
        disabler.commit()
    finally:
        disabler.close()
    kind, value = reader.join()
    assert kind == "error" and isinstance(value, AssignmentNotAvailable), value
    assert SECRET not in repr(value)
    assert _content_reads(s["pid"]) == reads_before
    assert deadlock_count() == deadlocks

    _assert_api_denied(client, s)
    assert _content_reads(s["pid"]) == reads_before
