"""
ADR-029 — ДЕТЕРМИНИРОВАННЫЕ concurrency-тесты подтверждения студента на
реальном PostgreSQL (lock_helpers: Gate + ожидание row-lock waiter'а).

Сериализация: подача — users заявителя FOR UPDATE; решение — users заявителя и
reviewer'а FOR UPDATE в порядке users.id, затем заявка FOR UPDATE с
перечитыванием. Проверяется:
  * две подачи одного пользователя → ровно одна pending (через блокировку);
  * подача ∥ одобрение существующей pending в обоих порядках → никогда
    approved и новая pending одновременно;
  * approve ∥ approve → второй после ожидания блокировок — no-op;
  * approve ∥ reject → второй verification_already_decided, итог — первый;
  * approve ∥ отключение заявителя администратором → account_inactive;
  * два пользователя подали заявки, стали supervisor'ами и одновременно
    проверяют заявки друг друга → обе операции успешны, без deadlock, решения
    и аудит согласованы.
"""
import uuid as _uuid

import app.student_verification.storage as sv_storage
import app.users.storage as users_storage
from app.db.models import AuditLog, StudentVerificationRequest as SVR, SystemMessageIntent
from app.db.session import SessionLocal
from app.student_verification import errors
from tests.integration.conftest import (
    add_user_role, create_multi_role_user, create_test_user,
)
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, deadlock_count, run_in_thread,
    wait_for_lock_waiter,
)

PASSWORD = "SecurePass42!"


def _student():
    email = f"integ_svc_{_uuid.uuid4().hex[:10]}@example.com"
    return int(create_test_user(email, PASSWORD)["id"])


def _supervisor(client):
    _, uid, _ = create_multi_role_user(client, ["supervisor", "student"])
    return uid


def _submit(user_id, ticket="000123"):
    return sv_storage.submit_atomic(user_id, faculty_code="law", ticket_number=ticket)


def _decide(req_uuid, decision, reviewer_id):
    return sv_storage.decide_atomic(
        _uuid.UUID(req_uuid), decision=decision, reviewer_id=reviewer_id,
        reason="Причина" if decision == "reject" else None,
    )


def _statuses(user_id):
    with SessionLocal() as db:
        return sorted(r.status for r in db.query(SVR).filter(SVR.user_id == user_id))


def _row(req_uuid):
    with SessionLocal() as db:
        row = db.query(SVR).filter(SVR.uuid == req_uuid).one()
        db.expunge(row)
        return row


def _events(event, entity_id=None):
    with SessionLocal() as db:
        q = db.query(AuditLog).filter(AuditLog.event_type == event)
        if entity_id is not None:
            q = q.filter(AuditLog.entity_id == entity_id)
        rows = q.all()
        for r in rows:
            db.expunge(r)
        return rows


def _result_intents(req_uuid):
    with SessionLocal() as db:
        return db.query(SystemMessageIntent).filter(
            SystemMessageIntent.event_key == f"student_verification_result:{req_uuid}",
        ).count()


def _error(result):
    kind, value = result
    assert kind == "error", result
    return value


def test_two_concurrent_submissions_create_one_pending(client, monkeypatch):
    uid = _student()
    deadlocks = deadlock_count()
    gate = Gate()
    # Первый поток берёт users FOR UPDATE и останавливается на проверке ролей.
    monkeypatch.setattr(sv_storage, "get_active_role_names",
                        gate.wrap(sv_storage.get_active_role_names))
    first = run_in_thread(lambda: _submit(uid, "111"))
    gate.wait_reached()
    second = run_in_thread(lambda: _submit(uid, "222"))
    wait_for_lock_waiter()
    gate.release.set()

    r1, r2 = first.join(), second.join()
    assert r1[0] == "ok"
    assert isinstance(_error(r2), errors.VerificationPendingExists)
    assert _statuses(uid) == ["pending"]
    assert len(_events("student_verification_submitted", r1[1]["id"])) == 1
    assert deadlock_count() == deadlocks


def test_approve_before_concurrent_submit_blocks_new_pending(client, monkeypatch):
    uid = _student()
    req = _submit(uid)
    sup = _supervisor(client)
    gate = Gate()
    monkeypatch.setattr(sv_storage, "lock_request", gate.wrap(sv_storage.lock_request))
    approve = run_in_thread(lambda: _decide(req["uuid"], "approve", sup))
    gate.wait_reached()          # approve держит users заявителя и reviewer'а
    submit = run_in_thread(lambda: _submit(uid, "999"))
    wait_for_lock_waiter()
    gate.release.set()

    assert approve.join()[0] == "ok"
    assert isinstance(_error(submit.join()), errors.AlreadyVerified)
    assert _statuses(uid) == ["approved"]


def test_submit_before_concurrent_approve_never_leaves_two_states(client, monkeypatch):
    uid = _student()
    req = _submit(uid)
    sup = _supervisor(client)
    gate = Gate()
    monkeypatch.setattr(sv_storage, "get_active_role_names",
                        gate.wrap(sv_storage.get_active_role_names))
    submit = run_in_thread(lambda: _submit(uid, "999"))
    gate.wait_reached()          # подача держит users заявителя
    approve = run_in_thread(lambda: _decide(req["uuid"], "approve", sup))
    wait_for_lock_waiter()
    gate.release.set()

    assert isinstance(_error(submit.join()), errors.VerificationPendingExists)
    assert approve.join()[0] == "ok"
    assert _statuses(uid) == ["approved"]


def test_repeated_approve_after_waiting_is_noop(client, monkeypatch):
    uid = _student()
    req = _submit(uid)
    sup1, sup2 = _supervisor(client), _supervisor(client)
    gate = Gate()
    monkeypatch.setattr(sv_storage, "lock_request", gate.wrap(sv_storage.lock_request))
    first = run_in_thread(lambda: _decide(req["uuid"], "approve", sup1))
    gate.wait_reached()
    second = run_in_thread(lambda: _decide(req["uuid"], "approve", sup2))
    wait_for_lock_waiter()
    gate.release.set()

    (kind1, (row1, changed1)), (kind2, (row2, changed2)) = first.join(), second.join()
    assert (kind1, changed1, kind2, changed2) == ("ok", True, "ok", False)
    assert _row(req["uuid"]).reviewed_by == sup1
    assert len(_events("student_verification_approved", req["id"])) == 1
    assert _result_intents(req["uuid"]) == 1


def test_opposite_decisions_after_waiting_keep_the_first(client, monkeypatch):
    uid = _student()
    req = _submit(uid)
    sup1, sup2 = _supervisor(client), _supervisor(client)
    gate = Gate()
    monkeypatch.setattr(sv_storage, "lock_request", gate.wrap(sv_storage.lock_request))
    approve = run_in_thread(lambda: _decide(req["uuid"], "approve", sup1))
    gate.wait_reached()
    reject = run_in_thread(lambda: _decide(req["uuid"], "reject", sup2))
    wait_for_lock_waiter()
    gate.release.set()

    assert approve.join()[0] == "ok"
    assert isinstance(_error(reject.join()), errors.VerificationAlreadyDecided)
    row = _row(req["uuid"])
    assert (row.status, row.reviewed_by, row.rejection_reason_enc) == ("approved", sup1, None)
    assert len(_events("student_verification_approved", req["id"])) == 1
    assert _events("student_verification_rejected", req["id"]) == []
    assert _result_intents(req["uuid"]) == 1


def test_approve_waiting_on_deactivation_sees_inactive_account(client, monkeypatch):
    uid = _student()
    req = _submit(uid)
    sup = _supervisor(client)
    _, admin_id, _ = create_multi_role_user(client, ["admin"])
    with SessionLocal() as db:
        from app.db.models import User
        target_uuid = str(db.get(User, uid).uuid)
    gate = Gate()
    monkeypatch.setattr(users_storage, "disable_user_in_tx",
                        gate.wrap(users_storage.disable_user_in_tx))
    deactivate = run_in_thread(lambda: users_storage.deactivate_user(
        target_uuid, "тест", actor_id=admin_id, actor_role="admin"))
    gate.wait_reached()          # отключение держит users заявителя
    approve = run_in_thread(lambda: _decide(req["uuid"], "approve", sup))
    wait_for_lock_waiter()
    gate.release.set()

    assert deactivate.join()[0] == "ok"
    assert isinstance(_error(approve.join()), errors.AccountInactive)
    assert _row(req["uuid"]).status == "pending"
    assert _result_intents(req["uuid"]) == 0


def test_two_supervisors_review_each_other_without_deadlock(client, monkeypatch):
    a, b = _student(), _student()
    req_a, req_b = _submit(a, "A-1"), _submit(b, "B-2")
    add_user_role(a, "supervisor")
    add_user_role(b, "supervisor")
    deadlocks = deadlock_count()

    gate = Gate()
    monkeypatch.setattr(sv_storage, "lock_request", gate.wrap(sv_storage.lock_request))
    # a проверяет заявку b; останавливается, удерживая users a И b.
    first = run_in_thread(lambda: _decide(req_b["uuid"], "approve", a))
    gate.wait_reached()
    # b проверяет заявку a — ждёт ту же пару строк в том же порядке.
    second = run_in_thread(lambda: _decide(req_a["uuid"], "approve", b))
    wait_for_lock_waiter()
    gate.release.set()

    r1, r2 = first.join(), second.join()
    assert_no_deadlock_error(r1, r2)
    assert r1[0] == "ok" and r1[1][1] is True
    assert r2[0] == "ok" and r2[1][1] is True
    assert deadlock_count() == deadlocks

    row_a, row_b = _row(req_a["uuid"]), _row(req_b["uuid"])
    assert (row_a.status, row_a.reviewed_by) == ("approved", b)
    assert (row_b.status, row_b.reviewed_by) == ("approved", a)
    (ev_b,) = _events("student_verification_approved", req_b["id"])
    (ev_a,) = _events("student_verification_approved", req_a["id"])
    assert (ev_b.user_id, ev_b.user_role) == (a, "supervisor")
    assert (ev_a.user_id, ev_a.user_role) == (b, "supervisor")
    assert _result_intents(req_a["uuid"]) == 1 and _result_intents(req_b["uuid"]) == 1
