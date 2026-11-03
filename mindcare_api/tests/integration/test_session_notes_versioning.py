"""
ADR-035 — общий механизм правки заметок: generic PATCH /api/session-notes/{id}
и client-scoped PATCH пишут через один _apply_note_update.

  * старое → новое и новое → старое: любое реальное изменение (в т.ч. только
    note_type) повышает version, устаревшая версия в любом пути — 409 без
    изменений; generic без version — сохранённый last-write-wins;
  * настоящий no-op в обоих путях — без версии, updated_at и события;
  * explicit null у is_shared_with_client в generic — 422;
  * конкурентные правки обоих путей сериализуются блокировкой строки:
    проигравший с той же версией получает конфликт; без deadlock;
  * generic POST: чужие и несогласованные связи — 422 + failure.
"""
import pytest

import app.session_notes.storage as sn_storage
from app.db.session import SessionLocal
from app.db.models import SessionNote
from tests.integration.appointment_outcome_helpers import make_appt
from tests.integration.assignments_helpers import (
    audit_since, auth, engage, marks, user, uuid_of,
)
from tests.integration.lock_helpers import (
    Gate, assert_no_deadlock_error, deadlock_count, run_in_thread, wait_for_lock_waiter,
)
from tests.integration.notes_helpers import (
    create_note, generic_patch, note_row, patch_note,
)


@pytest.fixture
def note(client):
    sid, _ = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    eng = engage(pid, sid)
    body = create_note(client, ptoken, sid).json()
    return {"sid": sid, "pid": pid, "ptoken": ptoken, "eng": eng,
            "uuid": body["uuid"], "id": note_row(body["uuid"]).id}


def _events(m, name):
    return [r for r in audit_since(m) if r.event_type == name]


def test_old_then_new(client, note):
    m = marks()
    r = generic_patch(client, note["ptoken"], note["id"], note_type="diagnosis")
    assert r.status_code == 200 and r.json()["version"] == 2
    assert len(_events(m, "session_note_updated")) == 1
    m = marks()
    r = patch_note(client, note["ptoken"], note["sid"], note["uuid"], content="новое", version=1)
    assert r.status_code == 409
    assert note_row(note["uuid"]).note_type == "diagnosis" and note_row(note["uuid"]).version == 2
    (fail,) = _events(m, "session_note_update_failed")
    assert fail.failure_reason_code == "version_conflict"


def test_new_then_old(client, note):
    r = patch_note(client, note["ptoken"], note["sid"], note["uuid"], content="новое", version=1)
    assert r.json()["version"] == 2
    m = marks()
    r = generic_patch(client, note["ptoken"], note["id"], content="старое", version=1)
    assert r.status_code == 409
    (fail,) = _events(m, "session_note_update_failed")
    assert fail.failure_reason_code == "version_conflict"
    assert note_row(note["uuid"]).version == 2
    r = generic_patch(client, note["ptoken"], note["id"], note_type="plan")   # без version
    assert r.status_code == 200 and r.json()["version"] == 3


def test_noop_in_both_paths_and_null_shared(client, note):
    updated = note_row(note["uuid"]).updated_at
    m = marks()
    assert generic_patch(client, note["ptoken"], note["id"]).json()["version"] == 1
    assert generic_patch(client, note["ptoken"], note["id"], note_type="general",
                         is_shared_with_client=False).json()["version"] == 1
    r = patch_note(client, note["ptoken"], note["sid"], note["uuid"], note_type="general", version=1)
    assert r.json()["changed"] is False and r.json()["version"] == 1
    assert _events(m, "session_note_updated") == []
    assert note_row(note["uuid"]).updated_at == updated
    r = generic_patch(client, note["ptoken"], note["id"], is_shared_with_client=None)
    assert r.status_code == 422 and note_row(note["uuid"]).is_shared_with_client is False


def test_shared_flag_change_in_generic_bumps_version(client, note):
    r = generic_patch(client, note["ptoken"], note["id"], is_shared_with_client=True)
    assert r.status_code == 200 and r.json()["version"] == 2


@pytest.mark.parametrize("first", ["generic", "client"])
def test_concurrent_edits_are_serialized(note, monkeypatch, first):
    gate = Gate()
    monkeypatch.setattr(sn_storage, "_apply_note_update", gate.wrap(sn_storage._apply_note_update))
    deadlocks = deadlock_count()

    def generic():
        return sn_storage.update_note(
            note["id"], {"content": "из generic", "version": 1},
            author_id=note["pid"], actor_role="psychologist",
        )

    def scoped():
        return sn_storage.update_client_note(
            note["pid"], uuid_of_client(note), note_row(note["uuid"]).uuid, {"content": "из карточки"},
            expected_version=1, actor_role="psychologist",
        )

    a_fn, b_fn = (generic, scoped) if first == "generic" else (scoped, generic)
    a = run_in_thread(a_fn)
    gate.wait_reached()                  # первый держит строку заметки
    b = run_in_thread(b_fn)
    wait_for_lock_waiter()               # второй ждёт блокировку
    gate.release.set()
    ra, rb = a.join(), b.join()
    assert_no_deadlock_error(ra, rb)
    assert ra[0] == "ok"
    assert rb[0] == "error" and isinstance(rb[1], sn_storage.NoteVersionConflict)
    assert note_row(note["uuid"]).version == 2
    assert deadlock_count() == deadlocks


def uuid_of_client(note):
    import uuid as _uuid
    return _uuid.UUID(uuid_of(note["sid"]))


def test_generic_post_rejects_foreign_and_mismatched_links(client, note):
    other_pid, _ = user(client, ["psychologist", "student"])
    other_sid, _ = user(client, ["student"])
    other_eng = engage(other_pid, other_sid)
    with SessionLocal() as db:
        from app.db.models import Appointment
        import uuid as _uuid
        own_other_client = db.query(Appointment.id).filter(
            Appointment.uuid == _uuid.UUID(make_appt(note["pid"], client_id=other_sid))).scalar()
        foreign_appt = db.query(Appointment.id).filter(
            Appointment.uuid == _uuid.UUID(make_appt(other_pid, client_id=note["sid"]))).scalar()
    cases = [
        ({"engagement_id": other_eng}, "access_denied"),
        ({"appointment_id": foreign_appt}, "access_denied"),
        ({"engagement_id": 10 ** 9}, "access_denied"),
        ({"engagement_id": note["eng"], "appointment_id": own_other_client}, "link_mismatch"),
    ]
    for links, code in cases:
        m = marks()
        r = client.post("/api/session-notes", headers=auth(note["ptoken"]),
                        json={"content": "x", **links})
        assert r.status_code == 422, (links, r.text)
        (fail,) = _events(m, "session_note_create_failed")
        assert fail.failure_reason_code == code and fail.user_role == "psychologist"
    with SessionLocal() as db:
        assert db.query(SessionNote).filter(SessionNote.author_id == note["pid"]).count() == 1
    r = client.post("/api/session-notes", headers=auth(note["ptoken"]),
                    json={"content": "x", "engagement_id": note["eng"]})
    assert r.status_code == 201
