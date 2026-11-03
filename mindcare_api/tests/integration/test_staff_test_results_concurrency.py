"""
ADR-016 (дополнение 2026-10-29) — детерминированные concurrency-тесты чтения
результатов психологом на реальном PostgreSQL (lock_helpers).

  * закрытие/передача сопровождения и отключение клиента НЕ могут
    зафиксироваться между проверкой области и чтением ответов: FOR SHARE строк
    сопровождения и клиента держит право на всём чтении;
  * чтение, начавшееся раньше закрытия, заканчивается до него (закрытие ждёт);
  * закрытие/отключение, зафиксированное раньше, — содержимое не читается и
    не расшифровывается, content_read не пишется.
Потоки вызывают storage/service напрямую (TestClient не потокобезопасен).
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

import app.supervisor.service as sup_service
import app.tests.service as service
import app.tests.storage as storage
from app.db.models import TherapyEngagement
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import engage, user
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, deadlock_count, run_in_thread, wait_for_lock_waiter,
)
from tests.integration.staff_results_helpers import (  # noqa: F401 (fixture)
    SECRET_TEXT, content_reads, full_test, submit,
)


@pytest.fixture
def setup(client, full_test):
    admin_id, _ = user(client, ["admin"])
    sid, stoken = user(client, ["student"])
    pid, _ = user(client, ["psychologist", "student"])
    sup_id, _ = user(client, ["supervisor", "student"])
    eng = engage(pid, sid)
    r_uuid = submit(client, stoken, full_test(admin_id))
    return {"sid": sid, "pid": pid, "sup": sup_id, "eng": eng, "r": uuid.UUID(r_uuid)}


def _read_answers(s):
    return storage.read_result_for_staff(
        role="psychologist", actor_id=s["pid"], result_uuid=s["r"], with_answers=True,
    )


def _service_answers(s):
    return service.get_staff_result_answers(
        current_user={"id": str(s["pid"]), "roles": ["psychologist", "student"]},
        requested_role=None, result_uuid=s["r"],
    )


def _free_text(data):
    return [i["free_text"] for i in data["items"] if i["free_text"]]


def _engagement_status(eng_id):
    with SessionLocal() as db:
        return db.get(TherapyEngagement, eng_id).status


_RACES = {
    "transfer": "UPDATE therapy_engagements SET status = 'transferred', ended_at = now() "
                "WHERE id = :eng",
    "deactivate": "UPDATE users SET is_active = false WHERE id = :sid",
    "delete": "UPDATE users SET deleted_at = now() WHERE id = :sid",
}


@pytest.mark.parametrize("race", sorted(_RACES))
def test_change_cannot_commit_between_scope_check_and_read(setup, monkeypatch, race):
    """
    Второе соединение пытается зафиксировать передачу/отключение ровно между
    проверкой области и чтением ответов. Строки под FOR SHARE: UPDATE не берёт
    их (lock_timeout) — право сохраняется до конца чтения; после чтения
    изменение проходит, и ответы больше не читаются.
    """
    s = setup
    attempt = {}
    real = storage._answers_to_dict

    def answers_after_race(result, db):
        other = SessionLocal()
        try:
            other.execute(text("SET LOCAL lock_timeout = '300ms'"))
            other.execute(text(_RACES[race]), {"eng": s["eng"], "sid": s["sid"]})
            other.commit()
            attempt["committed"] = True
        except OperationalError as exc:
            other.rollback()
            attempt["committed"] = False
            attempt["pgcode"] = getattr(exc.orig, "pgcode", None)
        finally:
            other.close()
        return real(result, db)

    monkeypatch.setattr(storage, "_answers_to_dict", answers_after_race)
    found = _read_answers(s)
    monkeypatch.undo()

    assert attempt == {"committed": False, "pgcode": "55P03"}   # lock_not_available
    assert _free_text(found["data"]) == [SECRET_TEXT]
    with SessionLocal() as db:
        db.execute(text(_RACES[race]), {"eng": s["eng"], "sid": s["sid"]})
        db.commit()
    assert _read_answers(s) is None


def test_read_started_before_close_finishes_before_close_commits(setup, monkeypatch):
    s = setup
    gate = Gate()
    monkeypatch.setattr(storage, "_answers_to_dict", gate.wrap(storage._answers_to_dict))
    deadlocks = deadlock_count()
    reads_before = len(content_reads(s["r"]))

    reader = run_in_thread(lambda: _service_answers(s))
    gate.wait_reached()                       # область проверена (FOR SHARE), чтения ещё нет
    closer = run_in_thread(lambda: sup_service.close_engagement(
        s["eng"], None, s["sup"], "supervisor"))
    wait_for_lock_waiter()                    # UPDATE сопровождения ждёт конца чтения
    assert _engagement_status(s["eng"]) == "active"
    gate.release.set()

    r, c = reader.join(), closer.join()
    assert_no_deadlock_error(r, c)
    assert r[0] == "ok", r
    assert _free_text(r[1]) == [SECRET_TEXT]
    assert len(content_reads(s["r"])) == reads_before + 1
    assert c[0] == "ok" and c[1]["status"] == "completed", c
    assert deadlock_count() == deadlocks

    with pytest.raises(service.ResultNotAvailable):
        _service_answers(s)
    assert len(content_reads(s["r"])) == reads_before + 1


@pytest.mark.parametrize("race", sorted(_RACES))
def test_change_committed_before_read_returns_nothing(setup, monkeypatch, race):
    s = setup
    decrypted = []
    real_decrypt = storage.decrypt_text
    monkeypatch.setattr(storage, "decrypt_text",
                        lambda v: decrypted.append(v) or real_decrypt(v))
    reads_before = len(content_reads(s["r"]))
    changer = SessionLocal()
    try:
        changer.execute(text(_RACES[race]), {"eng": s["eng"], "sid": s["sid"]})
        reader = run_in_thread(lambda: _service_answers(s))
        wait_for_lock_waiter()                # FOR SHARE ждёт незафиксированное изменение
        changer.commit()
    finally:
        changer.close()
    kind, value = reader.join()
    assert kind == "error" and isinstance(value, service.ResultNotAvailable), value
    assert SECRET_TEXT not in repr(value)
    assert decrypted == []
    assert len(content_reads(s["r"])) == reads_before
