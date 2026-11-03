"""
ADR-035 — заметки психолога в карточке клиента (существующий session_notes).

  * строгое активное сопровождение с активным клиентом; impersonation, admin,
    supervisor — отказ; видны и правятся только свои заметки, у которых КАЖДАЯ
    заполненная связь принадлежит психологу и клиенту — противоречивая старая
    запись не выдаётся, не расшифровывается и не исправляется;
  * создание: engagement — текущее сопровождение, встреча — любая неудалённая
    встреча этого психолога с этим клиентом (в т.ч. за пределами первой
    страницы списка и по привязанной карточке); чужая — 422 + failure;
  * правка: CAS по version, note_type-only тоже повышает версию, no-op без
    события; аудит ATOMIC (сбой → 503 без изменений); no-store; текст заметки не
    попадает в журналы, логи и ответы об ошибках.
"""
import logging
import uuid
from datetime import timedelta

import pytest

import app.session_notes.storage as sn_storage
from app.audit import AuditStorageError
from app.db.models import Appointment, AuditLog, SessionNote
from app.db.session import SessionLocal
from tests.integration.appointment_outcome_helpers import (  # noqa: F401 (fixture)
    cards, make_appt, now,
)
from tests.integration.assignments_helpers import (
    NO_STORE, audit_since, auth, blob, end_engagement, engage, marks, set_user, user, uuid_of,
)
from tests.integration.notes_helpers import (
    NOTE_SECRET, create_note, insert_note, note_row, notes_url, patch_note,
)


@pytest.fixture
def pair(client):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    eng = engage(pid, sid)
    return {"sid": sid, "stoken": stoken, "pid": pid, "ptoken": ptoken, "eng": eng}


def _list(client, token, client_uid, **params):
    return client.get(notes_url(client_uid), headers=auth(token), params=params)


def _failure(m, event, actor, code):
    rows = [r for r in audit_since(m) if r.event_type == event]
    assert len(rows) == 1, [r.event_type for r in audit_since(m)]
    r = rows[0]
    assert (r.user_id, r.user_role) == (actor, "psychologist")
    assert r.outcome == "failure" and r.failure_reason_code == code
    assert r.log_metadata == {} and NOTE_SECRET not in blob(r)


def _appt_id(appt_uuid):
    with SessionLocal() as db:
        return db.query(Appointment.id).filter(Appointment.uuid == uuid.UUID(appt_uuid)).scalar()


# ── создание, список, правка ─────────────────────────────────────────────────

def test_create_list_and_edit_own_note(client, pair):
    m = marks()
    r = create_note(client, pair["ptoken"], pair["sid"], note_type="plan")
    assert r.status_code == 201, r.text
    assert r.headers["cache-control"] == NO_STORE
    body = r.json()
    assert body["content"] == NOTE_SECRET and body["note_type"] == "plan"
    assert body["version"] == 1 and body["appointment"] is None
    assert "is_shared_with_client" not in body and "id" not in body
    row = note_row(body["uuid"])
    assert row.content.startswith("enc:v1:") and NOTE_SECRET not in row.content
    assert row.engagement_id == pair["eng"] and row.is_shared_with_client is False
    (ev,) = audit_since(m)
    assert ev.event_type == "session_note_created" and ev.user_role == "psychologist"
    assert ev.log_metadata == {} and NOTE_SECRET not in blob(ev)

    r = _list(client, pair["ptoken"], pair["sid"])
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    assert [i["uuid"] for i in r.json()["items"]] == [body["uuid"]]

    m = marks()
    r = patch_note(client, pair["ptoken"], pair["sid"], body["uuid"], content="Новый текст", version=1)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2 and r.json()["changed"] is True
    (ev,) = audit_since(m)
    assert ev.event_type == "session_note_updated" and "Новый текст" not in blob(ev)


def test_note_type_only_bumps_version_and_noop_is_silent(client, pair):
    note = create_note(client, pair["ptoken"], pair["sid"]).json()
    r = patch_note(client, pair["ptoken"], pair["sid"], note["uuid"], note_type="followup", version=1)
    assert r.json()["version"] == 2 and r.json()["changed"] is True
    updated = note_row(note["uuid"]).updated_at
    m = marks()
    r = patch_note(client, pair["ptoken"], pair["sid"], note["uuid"],
                   note_type="followup", content=NOTE_SECRET, version=2)
    assert r.status_code == 200 and r.json()["changed"] is False and r.json()["version"] == 2
    assert audit_since(m) == [] and note_row(note["uuid"]).updated_at == updated


def test_version_conflict_is_409_without_change(client, pair):
    note = create_note(client, pair["ptoken"], pair["sid"]).json()
    patch_note(client, pair["ptoken"], pair["sid"], note["uuid"], content="v2", version=1)
    m = marks()
    r = patch_note(client, pair["ptoken"], pair["sid"], note["uuid"], content="устаревшее", version=1)
    assert r.status_code == 409 and r.json()["code"] == "note_version_conflict"
    assert r.headers["cache-control"] == NO_STORE and "устаревшее" not in r.text
    assert note_row(note["uuid"]).version == 2
    _failure(m, "session_note_update_failed", pair["pid"], "version_conflict")


def test_keyset_pagination(client, pair):
    created = [create_note(client, pair["ptoken"], pair["sid"], content=f"Заметка {i}").json()["uuid"]
               for i in range(23)]
    first = _list(client, pair["ptoken"], pair["sid"], size=20).json()
    assert len(first["items"]) == 20 and first["has_more"] and first["next_cursor"]
    second = _list(client, pair["ptoken"], pair["sid"], size=20, before=first["next_cursor"]).json()
    uuids = [i["uuid"] for i in first["items"] + second["items"]]
    assert sorted(uuids) == sorted(created) and second["has_more"] is False
    bad = _list(client, pair["ptoken"], pair["sid"], before="%%%")
    assert bad.status_code == 422 and bad.headers["cache-control"] == NO_STORE


# ── привязка к встрече ───────────────────────────────────────────────────────

def test_note_to_meeting_beyond_first_page(client, pair):
    appts = [make_appt(pair["pid"], client_id=pair["sid"],
                       starts_at=now() - timedelta(days=3, hours=i)) for i in range(25)]
    oldest = appts[-1]
    first_page = client.get(
        f"/api/psychologist/clients/{uuid_of(pair['sid'])}/appointments",
        headers=auth(pair["ptoken"]), params={"view": "history", "size": 20},
    ).json()["items"]
    assert oldest not in {i["uuid"] for i in first_page}
    r = create_note(client, pair["ptoken"], pair["sid"], appointment_uuid=oldest)
    assert r.status_code == 201, r.text
    assert r.json()["appointment"]["uuid"] == oldest
    row = note_row(r.json()["uuid"])
    assert row.appointment_id == _appt_id(oldest) and row.engagement_id == pair["eng"]
    (item,) = [i for i in _list(client, pair["ptoken"], pair["sid"]).json()["items"]
               if i["uuid"] == r.json()["uuid"]]
    assert item["appointment"]["uuid"] == oldest


def test_note_to_linked_card_meeting(client, pair, cards):
    appt = make_appt(pair["pid"], card_id=cards(linked_user_id=pair["sid"]))
    r = create_note(client, pair["ptoken"], pair["sid"], appointment_uuid=appt)
    assert r.status_code == 201, r.text


def test_foreign_or_mismatched_meeting_is_rejected(client, pair, cards):
    other_pid, _ = user(client, ["psychologist", "student"])
    other_sid, _ = user(client, ["student"])
    foreign = [
        make_appt(other_pid, client_id=pair["sid"]),            # чужой психолог
        make_appt(pair["pid"], client_id=other_sid),            # другой клиент
        make_appt(pair["pid"], card_id=cards()),                # неприв. карточка
        make_appt(pair["pid"], client_id=pair["sid"], deleted=True),
        str(uuid.uuid4()),
    ]
    for appt in foreign:
        m = marks()
        r = create_note(client, pair["ptoken"], pair["sid"], appointment_uuid=appt)
        assert r.status_code == 422 and NOTE_SECRET not in r.text
        _failure(m, "session_note_create_failed", pair["pid"], "access_denied")
    with SessionLocal() as db:
        assert db.query(SessionNote).filter(SessionNote.author_id == pair["pid"]).count() == 0


# ── противоречивые старые записи ─────────────────────────────────────────────

def test_inconsistent_old_notes_are_hidden_and_not_decrypted(client, pair, monkeypatch):
    other_sid, _ = user(client, ["student"])
    other_eng = engage(pair["pid"], other_sid)
    other_pid, _ = user(client, ["psychologist", "student"])
    appt_b = make_appt(pair["pid"], client_id=other_sid)
    foreign_appt = make_appt(other_pid, client_id=pair["sid"])
    # сопровождение → клиент A, встреча → клиент B
    _, mixed_uuid, mixed_ct = insert_note(pair["pid"], engagement_id=pair["eng"],
                                          appointment_id=_appt_id(appt_b))
    # своё сопровождение A + встреча чужого психолога
    _, foreign_uuid, foreign_ct = insert_note(pair["pid"], engagement_id=pair["eng"],
                                              appointment_id=_appt_id(foreign_appt))
    # заметка другого автора на том же клиенте
    insert_note(other_pid, appointment_id=_appt_id(foreign_appt))
    _, ok_uuid, _ = insert_note(pair["pid"], engagement_id=pair["eng"], content="Корректная")

    decrypted = []
    real = sn_storage.decrypt_text
    monkeypatch.setattr(sn_storage, "decrypt_text", lambda v: decrypted.append(v) or real(v))

    items_a = _list(client, pair["ptoken"], pair["sid"]).json()["items"]
    items_b = _list(client, pair["ptoken"], other_sid).json()["items"]
    assert [i["uuid"] for i in items_a] == [ok_uuid]
    assert items_b == []
    assert mixed_ct not in decrypted and foreign_ct not in decrypted
    assert other_eng

    before = note_row(mixed_uuid)
    for client_uid in (pair["sid"], other_sid):
        m = marks()
        r = patch_note(client, pair["ptoken"], client_uid, mixed_uuid, content="подмена", version=1)
        assert r.status_code == 404 and NOTE_SECRET not in r.text
        _failure(m, "session_note_update_failed", pair["pid"], "access_denied")
    after = note_row(mixed_uuid)
    assert (after.content, after.version, after.engagement_id, after.appointment_id) == \
        (before.content, before.version, before.engagement_id, before.appointment_id)


# ── доступ ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("change", ["ended", "inactive", "foreign"])
def test_scope_is_required(client, pair, change):
    note = create_note(client, pair["ptoken"], pair["sid"]).json()
    token, actor = pair["ptoken"], pair["pid"]
    if change == "ended":
        end_engagement(pair["eng"])
    elif change == "inactive":
        set_user(pair["sid"], is_active=False)
    else:
        actor, token = user(client, ["psychologist", "student"])
    r = _list(client, token, pair["sid"])
    assert r.status_code == 404 and NOTE_SECRET not in r.text
    m = marks()
    assert create_note(client, token, pair["sid"]).status_code == 404
    _failure(m, "session_note_create_failed", actor, "access_denied")
    m = marks()
    r = patch_note(client, token, pair["sid"], note["uuid"], content="x", version=1)
    assert r.status_code == 404
    _failure(m, "session_note_update_failed", actor, "access_denied")
    assert note_row(note["uuid"]).version == 1


def test_other_roles_and_impersonation_are_forbidden(client, pair):
    _, admin_token = user(client, ["admin"])
    _, sup_token = user(client, ["supervisor"])
    as_psych = client.post(f"/api/admin/users/{uuid_of(pair['pid'])}/impersonate",
                           headers=auth(admin_token)).json()["session_token"]
    for token in (admin_token, sup_token, as_psych, pair["stoken"]):
        r = _list(client, token, pair["sid"])
        assert r.status_code == 403 and r.headers["cache-control"] == NO_STORE
        assert create_note(client, token, pair["sid"]).status_code == 403


# ── аудит и утечки ───────────────────────────────────────────────────────────

def test_audit_failure_rolls_back_create_and_update(client, pair, monkeypatch):
    note = create_note(client, pair["ptoken"], pair["sid"]).json()

    def _boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(sn_storage, "record_event", _boom)
    r = create_note(client, pair["ptoken"], pair["sid"], content="Не сохранится")
    assert r.status_code == 503 and "Не сохранится" not in r.text
    r = patch_note(client, pair["ptoken"], pair["sid"], note["uuid"], content="Тоже нет", version=1)
    assert r.status_code == 503
    monkeypatch.undo()
    with SessionLocal() as db:
        assert db.query(SessionNote).filter(SessionNote.author_id == pair["pid"]).count() == 1
    assert note_row(note["uuid"]).version == 1


def test_invalid_body_is_422_without_echo(client, pair, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    r = client.post(notes_url(pair["sid"]), headers=auth(pair["ptoken"]),
                    json={"content": NOTE_SECRET, "is_shared_with_client": True})
    assert r.status_code == 422 and r.headers["cache-control"] == NO_STORE
    assert NOTE_SECRET not in r.text
    r = client.post(notes_url(pair["sid"]), headers=auth(pair["ptoken"]),
                    json={"content": "", "note_type": NOTE_SECRET})
    assert r.status_code == 422 and NOTE_SECRET not in r.text
    out = capsys.readouterr()
    assert NOTE_SECRET not in caplog.text and NOTE_SECRET not in out.out + out.err
    with SessionLocal() as db:
        for row in db.query(AuditLog).order_by(AuditLog.id.desc()).limit(50):
            assert NOTE_SECRET not in blob(row)
