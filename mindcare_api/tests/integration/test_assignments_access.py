"""
ADR-033 — gated integration: матрица доступа к заданиям.

Права — по membership roles[], не по выбранному кабинету:
  * психолог — только строгое активное сопровождение (status='active' AND
    ended_at IS NULL) с активным клиентом; клиент может иметь staff-роли;
  * клиент — только собственные задания; после завершения/передачи
    сопровождения история видна, изменение — 409 engagement_inactive;
  * прежний психолог теряет доступ, новый не получает старые задания;
    реактивация той же пары возвращает задания этой связи (решение ADR-033);
  * admin/supervisor сами по себе — 403; impersonation — 403 везде.
Отказы — точные *_failed-строки; значения не попадают в журналы и логи.
"""
import logging
import uuid

import pytest

import app.supervisor.service as sup_service
from app.db.models import TherapyEngagement
from app.db.session import SessionLocal
from tests.integration.assignments_helpers import (
    NO_STORE, SECRET, assert_failure_row, audit_since, auth, blob, cancel, client_url,
    complete, create, create_ok, end_engagement, engage, marks, my, row, rows_since,
    set_user, user, uuid_of,
)


def _psych_list(client, ptoken, client_uid):
    return client.get(client_url(client_uid), headers=auth(ptoken))


def _active_engagement_id(client_id):
    with SessionLocal() as db:
        return db.query(TherapyEngagement.id).filter(
            TherapyEngagement.client_id == client_id,
            TherapyEngagement.status == "active",
            TherapyEngagement.ended_at.is_(None),
        ).scalar()


def _assert_denied(r, m, event, actor_uid, role="psychologist", code="access_denied"):
    assert r.status_code == 404, r.text
    assert r.json() == {"detail": "Задание недоступно", "code": "assignment_not_available"}
    assert r.headers["cache-control"] == NO_STORE and SECRET not in r.text
    (fail,) = audit_since(m)
    assert_failure_row(fail, event, actor_uid, role, code)


# ── чужие uuid и посторонние ──────────────────────────────────────────────────

def test_foreign_client_and_foreign_assignment_are_denied(client):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    a_uuid = create_ok(client, ptoken, sid)

    other_pid, other_ptoken = user(client, ["psychologist", "student"])
    other_sid, other_stoken = user(client, ["student"])

    m = marks()
    _assert_denied(_psych_list(client, other_ptoken, sid), m, "assignment_read_failed", other_pid)
    m = marks()
    _assert_denied(create(client, other_ptoken, sid), m, "assignment_create_failed", other_pid)
    m = marks()
    _assert_denied(cancel(client, other_ptoken, a_uuid), m, "assignment_cancel_failed", other_pid)
    m = marks()
    _assert_denied(complete(client, other_stoken, a_uuid), m, "assignment_complete_failed",
                   other_sid, role="student")
    assert my(client, other_stoken).json()["items"] == []
    m = marks()
    _assert_denied(_psych_list(client, ptoken, other_sid), m, "assignment_read_failed", pid)
    m = marks()
    r = client.get(f"/api/psychologist/clients/{uuid.uuid4()}/assignments", headers=auth(ptoken))
    _assert_denied(r, m, "assignment_read_failed", pid)
    assert row(a_uuid).status == "active"


@pytest.mark.parametrize("roles", [["admin"], ["supervisor", "student"], ["admin", "supervisor"]])
def test_admin_and_supervisor_alone_have_no_access(client, roles):
    sid, _ = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    a_uuid = create_ok(client, ptoken, sid)
    _, token = user(client, roles)
    m = marks()
    for r in (_psych_list(client, token, sid), create(client, token, sid),
              cancel(client, token, a_uuid)):
        assert r.status_code == 403 and r.headers["cache-control"] == NO_STORE
        assert SECRET not in r.text
    assert audit_since(m) == []
    assert row(a_uuid).status == "active"


# ── multi-role ────────────────────────────────────────────────────────────────

def test_client_with_staff_roles_receives_and_completes(client):
    sid, stoken = user(client, ["supervisor", "psychologist", "student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    a_uuid = create_ok(client, ptoken, sid)
    (item,) = my(client, stoken).json()["items"]
    assert item["uuid"] == a_uuid
    m = marks()
    assert complete(client, stoken, a_uuid).status_code == 200
    rows = audit_since(m)
    (done,) = [r for r in rows if r.event_type.startswith("assignment")]
    # кроме перехода — только создание system-беседы психолога для уведомления
    assert {r.event_type for r in rows if r is not done} <= {"system_conversation_created"}
    assert (done.user_id, done.user_role) == (sid, "student")
    # собственные задания клиента НЕ видны ему как психологу этого же клиента
    r = _psych_list(client, stoken, sid)
    assert r.status_code == 404


def test_psychologist_who_is_a_client_keeps_roles_separate(client):
    p1, t1 = user(client, ["psychologist", "student"])
    p2, t2 = user(client, ["psychologist", "student"])
    sid, stoken = user(client, ["student"])
    engage(p2, p1)            # p1 — клиент p2
    engage(p1, sid)           # p1 — психолог sid
    own = create_ok(client, t2, p1, text="для p1 как клиента")
    issued = create_ok(client, t1, sid, text="от p1 клиенту")
    assert [i["uuid"] for i in my(client, t1).json()["items"]] == [own]
    assert [i["uuid"] for i in _psych_list(client, t1, sid).json()["items"]] == [issued]
    assert _psych_list(client, t1, p1).status_code == 404


# ── impersonation ─────────────────────────────────────────────────────────────

def test_impersonation_is_forbidden_everywhere(client):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    a_uuid = create_ok(client, ptoken, sid)
    _, admin_token = user(client, ["admin"])

    def impersonate(uid):
        r = client.post(f"/api/admin/users/{uuid_of(uid)}/impersonate", headers=auth(admin_token))
        assert r.status_code == 200, r.text
        return r.json()["session_token"]

    as_psych, as_client = impersonate(pid), impersonate(sid)
    m = marks()
    responses = [
        _psych_list(client, as_psych, sid), create(client, as_psych, sid),
        cancel(client, as_psych, a_uuid),
        my(client, as_client), client.get("/api/assignments/my/summary", headers=auth(as_client)),
        complete(client, as_client, a_uuid),
    ]
    for r in responses:
        assert r.status_code == 403 and r.headers["cache-control"] == NO_STORE
        assert SECRET not in r.text
    assert [x for x in audit_since(m) if x.event_type.startswith("assignment")] == []
    assert row(a_uuid).status == "active"


# ── отключённые аккаунты ──────────────────────────────────────────────────────

@pytest.mark.parametrize("values", [{"is_active": False}, {"deleted_at": "now"}])
def test_disabled_or_deleted_client_is_not_available_to_psychologist(client, values):
    from datetime import datetime, timezone
    sid, _ = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    a_uuid = create_ok(client, ptoken, sid)
    if values.get("deleted_at") == "now":
        values = {"deleted_at": datetime.now(timezone.utc)}
    set_user(sid, **values)
    m = marks()
    _assert_denied(_psych_list(client, ptoken, sid), m, "assignment_read_failed", pid)
    m = marks()
    _assert_denied(create(client, ptoken, sid), m, "assignment_create_failed", pid)
    m = marks()
    _assert_denied(cancel(client, ptoken, a_uuid), m, "assignment_cancel_failed", pid)


def test_disabled_client_session_is_rejected(client):
    sid, stoken = user(client, ["student"])
    set_user(sid, is_active=False)
    r = my(client, stoken)
    assert r.status_code == 401 and r.headers["cache-control"] == NO_STORE


# ── завершение, передача, реактивация ─────────────────────────────────────────

@pytest.mark.parametrize("status", ["completed", "transferred"])
def test_ended_engagement_keeps_history_but_blocks_changes(client, status):
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    eng = engage(pid, sid)
    a_uuid = create_ok(client, ptoken, sid)
    end_engagement(eng, status=status)

    (item,) = my(client, stoken, view="history").json()["items"]
    assert item["uuid"] == a_uuid and item["can_complete"] is False
    assert client.get("/api/assignments/my/summary",
                      headers=auth(stoken)).json()["open_count"] == 0
    m = marks()
    r = complete(client, stoken, a_uuid)
    assert r.status_code == 409 and r.json()["code"] == "assignment_engagement_inactive"
    (fail,) = audit_since(m)
    assert_failure_row(fail, "assignment_complete_failed", sid, "student", "engagement_inactive")
    m = marks()
    _assert_denied(cancel(client, ptoken, a_uuid), m, "assignment_cancel_failed", pid)
    m = marks()
    _assert_denied(_psych_list(client, ptoken, sid), m, "assignment_read_failed", pid)
    assert row(a_uuid).status == "active"


def test_transfer_new_psychologist_does_not_get_old_assignments(client):
    sid, stoken = user(client, ["student"])
    sup_id, _ = user(client, ["supervisor", "student"])
    p1, t1 = user(client, ["psychologist", "student"])
    p2, t2 = user(client, ["psychologist", "student"])
    eng = sup_service.assign_psychologist(sid, p1, None, sup_id, "supervisor")
    old = create_ok(client, t1, sid, text="от первого")

    sup_service.transfer_psychologist(eng["id"], p2, None, sup_id, "supervisor")
    assert _psych_list(client, t1, sid).status_code == 404
    r = _psych_list(client, t2, sid)
    assert r.status_code == 200 and r.json()["items"] == []
    new = create_ok(client, t2, sid, text="от второго")
    assert [i["uuid"] for i in my(client, stoken).json()["items"]] == [new]
    assert [i["uuid"] for i in my(client, stoken, view="history").json()["items"]] == [old]
    m = marks()
    _assert_denied(cancel(client, t2, old), m, "assignment_cancel_failed", p2)


def test_reactivation_of_same_pair_restores_its_assignments(client):
    sid, stoken = user(client, ["student"])
    sup_id, _ = user(client, ["supervisor", "student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    sup_service.assign_psychologist(sid, pid, None, sup_id, "supervisor")
    first = create_ok(client, ptoken, sid, text="первое")
    second = create_ok(client, ptoken, sid, text="второе")

    sup_service.close_engagement(_active_engagement_id(sid), None, sup_id, "supervisor")
    assert complete(client, stoken, first).status_code == 409
    assert _psych_list(client, ptoken, sid).status_code == 404

    # та же пара назначена снова → прежняя связь реактивирована
    sup_service.assign_psychologist(sid, pid, None, sup_id, "supervisor")
    opened = my(client, stoken).json()["items"]
    assert {i["uuid"] for i in opened} == {first, second}
    assert all(i["can_complete"] for i in opened)
    assert complete(client, stoken, first).status_code == 200
    r = _psych_list(client, ptoken, sid)
    assert r.status_code == 200 and {i["uuid"] for i in r.json()["items"]} == {first, second}
    assert cancel(client, ptoken, second).status_code == 200


# ── утечки ────────────────────────────────────────────────────────────────────

def test_values_never_reach_journals_or_logs(client, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    sid, stoken = user(client, ["student"])
    pid, ptoken = user(client, ["psychologist", "student"])
    other_pid, other_ptoken = user(client, ["psychologist", "student"])
    engage(pid, sid)
    capsys.readouterr()
    m = marks()
    a_uuid = create_ok(client, ptoken, sid)
    assert _psych_list(client, ptoken, sid).status_code == 200
    assert _psych_list(client, other_ptoken, sid).status_code == 404
    assert create(client, ptoken, sid, text=" ").status_code == 422
    assert complete(client, stoken, a_uuid).status_code == 200
    assert cancel(client, ptoken, a_uuid).status_code == 409
    enc = row(a_uuid).text_enc
    for rows in rows_since(m):
        for r in rows:
            assert SECRET not in blob(r) and enc not in blob(r), r.__tablename__
            assert a_uuid not in blob(r)
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err + caplog.text
