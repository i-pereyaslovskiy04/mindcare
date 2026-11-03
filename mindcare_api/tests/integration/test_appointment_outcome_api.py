"""
ADR-035 — итог индивидуальной встречи и встречи клиента в карточке психолога
(gated integration).

Итог (PATCH /api/psychologist/appointments/{uuid}/outcome):
  * confirmed → completed | no_show только психологом встречи и только после
    окончания (граница ends_at, ends_at NULL → starts_at + duration);
  * повтор того же итога — 200 changed=false без второго события; иной
    конечный статус / не confirmed / не закончилась — 409 без изменений и
    failure-событие; чужая встреча — 403 + failure; impersonation — 403;
  * смена статуса и success-событие — один commit: сбой аудита → 503, статус
    прежний;
  * decline после окончания confirmed-встречи — 409; поздние writer'ы не
    перезаписывают итог.
Встречи клиента (GET /api/psychologist/clients/{uuid}/appointments):
  * выборка ограничена психологом И клиентом; записи привязанной карточки
    видны; upcoming/history с keyset-пагинацией; строгое сопровождение.
"""
import uuid
from datetime import timedelta

import pytest

import app.appointments.storage as appt_storage
from app.audit import AuditStorageError
from tests.integration.appointment_outcome_helpers import (  # noqa: F401 (fixture)
    appt_row, cards, make_appt, now, set_appt,
)
from tests.integration.assignments_helpers import (
    NO_STORE, audit_since, auth, end_engagement, engage, marks, set_user, user, uuid_of,
)


def _outcome(client, token, appt_uuid, outcome="completed"):
    return client.patch(f"/api/psychologist/appointments/{appt_uuid}/outcome",
                        headers=auth(token), json={"outcome": outcome})


def _client_list(client, token, client_uid, view="upcoming", **params):
    return client.get(f"/api/psychologist/clients/{uuid_of(client_uid)}/appointments",
                      headers=auth(token), params={"view": view, **params})


def _events(m, name=None):
    rows = audit_since(m)
    return [r for r in rows if name is None or r.event_type == name]


def _assert_failure(m, actor_uid, code):
    (row,) = _events(m, "appointment_outcome_failed")
    assert (row.user_id, row.user_role) == (actor_uid, "psychologist")
    assert row.outcome == "failure" and row.failure_reason_code == code
    assert row.entity_type is None and row.log_metadata == {}


@pytest.fixture
def pair(client):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    eng = engage(pid, sid)
    return {"sid": sid, "stoken": stoken, "pid": pid, "ptoken": ptoken, "eng": eng}


# ── итог: успех, no-op, конфликт ─────────────────────────────────────────────

@pytest.mark.parametrize("outcome, event", [
    ("completed", "appointment_completed"), ("no_show", "appointment_no_show"),
])
def test_outcome_success_writes_one_atomic_event(client, pair, outcome, event):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    m = marks()
    r = _outcome(client, pair["ptoken"], a, outcome)
    assert r.status_code == 200, r.text
    assert r.json() == {"uuid": a, "status": outcome, "changed": True}
    assert appt_row(a).status == outcome
    (row,) = _events(m)
    assert row.event_type == event
    assert (row.user_id, row.user_role) == (pair["pid"], "psychologist")
    assert (row.entity_type, row.entity_id) == ("appointment", appt_row(a).id)
    assert row.outcome == "success" and row.log_metadata == {}


def test_repeat_same_outcome_is_noop_without_second_event(client, pair):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    assert _outcome(client, pair["ptoken"], a).status_code == 200
    updated = appt_row(a).updated_at
    m = marks()
    r = _outcome(client, pair["ptoken"], a)
    assert r.status_code == 200 and r.json()["changed"] is False
    assert _events(m) == []
    assert appt_row(a).updated_at == updated


@pytest.mark.parametrize("first, second", [("completed", "no_show"), ("no_show", "completed")])
def test_conflicting_final_status_is_409_without_change(client, pair, first, second):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    assert _outcome(client, pair["ptoken"], a, first).status_code == 200
    m = marks()
    r = _outcome(client, pair["ptoken"], a, second)
    assert r.status_code == 409, r.text
    assert appt_row(a).status == first
    _assert_failure(m, pair["pid"], "outcome_conflict")


@pytest.mark.parametrize("status", ["pending_confirmation", "cancelled", "declined"])
def test_not_confirmed_is_409_invalid_status(client, pair, status):
    a = make_appt(pair["pid"], client_id=pair["sid"], status=status)
    m = marks()
    r = _outcome(client, pair["ptoken"], a)
    assert r.status_code == 409 and appt_row(a).status == status
    _assert_failure(m, pair["pid"], "invalid_status")


# ── время: граница ends_at, ends_at NULL ─────────────────────────────────────

def test_before_end_is_409_not_ended_and_after_end_ok(client, pair):
    start = now() - timedelta(minutes=30)
    not_yet = make_appt(pair["pid"], client_id=pair["sid"], starts_at=start,
                        ends_at=now() + timedelta(minutes=2))
    m = marks()
    r = _outcome(client, pair["ptoken"], not_yet)
    assert r.status_code == 409 and appt_row(not_yet).status == "confirmed"
    _assert_failure(m, pair["pid"], "not_ended")

    just_ended = make_appt(pair["pid"], client_id=pair["sid"], starts_at=start,
                           ends_at=now() - timedelta(seconds=1))
    assert _outcome(client, pair["ptoken"], just_ended).status_code == 200


def test_null_ends_at_uses_starts_at_plus_duration(client, pair):
    running = make_appt(pair["pid"], client_id=pair["sid"],
                        starts_at=now() - timedelta(minutes=10), duration=50, ends_at=None)
    assert _outcome(client, pair["ptoken"], running).status_code == 409
    finished = make_appt(pair["pid"], client_id=pair["sid"],
                         starts_at=now() - timedelta(minutes=60), duration=50, ends_at=None)
    assert _outcome(client, pair["ptoken"], finished).status_code == 200


# ── доступ ───────────────────────────────────────────────────────────────────

def test_foreign_psychologist_and_unknown_uuid(client, pair):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    other_pid, other_token = user(client, ["psychologist", "student"])
    m = marks()
    r = _outcome(client, other_token, a)
    assert r.status_code == 403 and appt_row(a).status == "confirmed"
    _assert_failure(m, other_pid, "access_denied")
    m = marks()
    assert _outcome(client, pair["ptoken"], uuid.uuid4()).status_code == 404
    assert _events(m) == []


def test_outcome_does_not_require_active_engagement(client, pair):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    end_engagement(pair["eng"])
    assert _outcome(client, pair["ptoken"], a).status_code == 200


def test_impersonation_and_non_psychologist_are_forbidden(client, pair):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    _, admin_token = user(client, ["admin"])
    r = client.post(f"/api/admin/users/{uuid_of(pair['pid'])}/impersonate",
                    headers=auth(admin_token))
    as_psych = r.json()["session_token"]
    m = marks()
    assert _outcome(client, as_psych, a).status_code == 403
    assert _outcome(client, admin_token, a).status_code == 403
    assert _outcome(client, pair["stoken"], a).status_code == 403
    assert [x for x in _events(m) if x.event_type.startswith("appointment_")] == []
    assert appt_row(a).status == "confirmed"


def test_invalid_outcome_value_is_422(client, pair):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    r = client.patch(f"/api/psychologist/appointments/{a}/outcome",
                     headers=auth(pair["ptoken"]), json={"outcome": "cancelled"})
    assert r.status_code == 422 and appt_row(a).status == "confirmed"


# ── транзакция: сбой аудита откатывает переход ───────────────────────────────

def test_audit_failure_rolls_back_status(client, pair, monkeypatch):
    a = make_appt(pair["pid"], client_id=pair["sid"])

    def _boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(appt_storage, "record_event", _boom)
    r = _outcome(client, pair["ptoken"], a)
    monkeypatch.undo()
    assert r.status_code == 503, r.text
    assert appt_row(a).status == "confirmed"


# ── другие writer'ы не перезаписывают итог ───────────────────────────────────

def test_decline_after_end_is_409_and_decline_of_outcome_is_rejected(client, pair):
    ended = make_appt(pair["pid"], client_id=pair["sid"])
    r = client.patch(f"/api/psychologist/appointments/{ended}/decline",
                     headers=auth(pair["ptoken"]), json={"reason": None})
    assert r.status_code == 409 and appt_row(ended).status == "confirmed"

    assert _outcome(client, pair["ptoken"], ended).status_code == 200
    r = client.patch(f"/api/psychologist/appointments/{ended}/decline",
                     headers=auth(pair["ptoken"]), json={"reason": None})
    assert r.status_code == 422 and appt_row(ended).status == "completed"

    future = make_appt(pair["pid"], client_id=pair["sid"],
                       starts_at=now() + timedelta(days=3))
    r = client.patch(f"/api/psychologist/appointments/{future}/decline",
                     headers=auth(pair["ptoken"]), json={"reason": None})
    assert r.status_code == 200 and appt_row(future).status == "declined"


def test_student_cannot_cancel_completed(client, pair):
    a = make_appt(pair["pid"], client_id=pair["sid"])
    assert _outcome(client, pair["ptoken"], a).status_code == 200
    r = client.patch(f"/api/appointments/{a}/cancel", headers=auth(pair["stoken"]),
                     json={"reason": None})
    assert r.status_code == 422 and appt_row(a).status == "completed"


def test_general_list_exposes_can_mark_outcome(client, pair):
    ended = make_appt(pair["pid"], client_id=pair["sid"])
    future = make_appt(pair["pid"], client_id=pair["sid"], starts_at=now() + timedelta(days=1))
    items = client.get("/api/psychologist/appointments", headers=auth(pair["ptoken"]),
                       params={"size": 100}).json()["items"]
    flags = {i["uuid"]: i["can_mark_outcome"] for i in items}
    assert flags[ended] is True and flags[future] is False


# ── встречи клиента в карточке ───────────────────────────────────────────────

def test_client_list_is_scoped_to_psychologist_and_client(client, pair, cards):
    other_pid, _ = user(client, ["psychologist", "student"])
    other_sid, _ = user(client, ["student"])
    mine = make_appt(pair["pid"], client_id=pair["sid"], starts_at=now() + timedelta(days=1))
    make_appt(other_pid, client_id=pair["sid"], starts_at=now() + timedelta(days=2))
    make_appt(pair["pid"], client_id=other_sid, starts_at=now() + timedelta(days=3))
    linked = make_appt(pair["pid"], card_id=cards(linked_user_id=pair["sid"]),
                       starts_at=now() - timedelta(days=30))
    make_appt(pair["pid"], card_id=cards(), starts_at=now() - timedelta(days=31))
    make_appt(pair["pid"], card_id=cards(linked_user_id=other_sid),
              starts_at=now() - timedelta(days=32))
    deleted = make_appt(pair["pid"], client_id=pair["sid"], status="cancelled",
                        starts_at=now() + timedelta(days=4), deleted=True)

    r = _client_list(client, pair["ptoken"], pair["sid"], "upcoming")
    assert r.status_code == 200 and r.headers["cache-control"] == NO_STORE
    assert [i["uuid"] for i in r.json()["items"]] == [mine]
    hist = _client_list(client, pair["ptoken"], pair["sid"], "history").json()["items"]
    assert [i["uuid"] for i in hist] == [linked]
    assert hist[0]["via_card"] is True and deleted not in str(hist)
    assert set(hist[0]) == {"uuid", "starts_at", "ends_at", "status", "meeting_type_name",
                            "modality", "via_card", "can_mark_outcome"}


def test_upcoming_and_history_split(client, pair):
    running = make_appt(pair["pid"], client_id=pair["sid"],
                        starts_at=now() - timedelta(minutes=10), ends_at=now() + timedelta(minutes=40))
    ended = make_appt(pair["pid"], client_id=pair["sid"])
    past_pending = make_appt(pair["pid"], client_id=pair["sid"], status="pending_confirmation",
                             starts_at=now() - timedelta(days=1))
    future_declined = make_appt(pair["pid"], client_id=pair["sid"], status="declined",
                                starts_at=now() + timedelta(days=1))
    up = _client_list(client, pair["ptoken"], pair["sid"], "upcoming").json()["items"]
    assert [i["uuid"] for i in up] == [running]
    assert up[0]["can_mark_outcome"] is False
    hist = {i["uuid"]: i for i in
            _client_list(client, pair["ptoken"], pair["sid"], "history").json()["items"]}
    assert set(hist) == {ended, past_pending, future_declined}
    assert hist[ended]["can_mark_outcome"] is True
    assert hist[past_pending]["can_mark_outcome"] is False


def test_client_list_keyset_pagination(client, pair):
    created = [make_appt(pair["pid"], client_id=pair["sid"],
                         starts_at=now() - timedelta(days=2, hours=i)) for i in range(25)]
    first = _client_list(client, pair["ptoken"], pair["sid"], "history", size=20).json()
    assert len(first["items"]) == 20 and first["has_more"] is True and first["next_cursor"]
    second = _client_list(client, pair["ptoken"], pair["sid"], "history", size=20,
                          before=first["next_cursor"]).json()
    assert len(second["items"]) == 5 and second["has_more"] is False
    uuids = [i["uuid"] for i in first["items"] + second["items"]]
    assert sorted(uuids) == sorted(created) and len(set(uuids)) == 25
    stamps = [i["starts_at"] for i in first["items"] + second["items"]]
    assert stamps == sorted(stamps, reverse=True)

    bad = _client_list(client, pair["ptoken"], pair["sid"], "history", before="%%%")
    assert bad.status_code == 422 and bad.headers["cache-control"] == NO_STORE


@pytest.mark.parametrize("change", ["ended", "inactive", "foreign"])
def test_client_list_requires_strict_scope(client, pair, change):
    token = pair["ptoken"]
    if change == "ended":
        end_engagement(pair["eng"])
    elif change == "inactive":
        set_user(pair["sid"], is_active=False)
    else:
        _, token = user(client, ["psychologist", "student"])
    r = _client_list(client, token, pair["sid"])
    assert r.status_code == 404 and r.headers["cache-control"] == NO_STORE


def test_client_list_forbidden_under_impersonation(client, pair):
    _, admin_token = user(client, ["admin"])
    as_psych = client.post(f"/api/admin/users/{uuid_of(pair['pid'])}/impersonate",
                           headers=auth(admin_token)).json()["session_token"]
    r = _client_list(client, as_psych, pair["sid"])
    assert r.status_code == 403 and r.headers["cache-control"] == NO_STORE
