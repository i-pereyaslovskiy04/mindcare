"""
ADR-031 — gated integration: чтение контактов сотрудниками (матрица доступа).

Права — только по membership roles[]:
  A) psychologist + строгое активное сопровождение (status='active' AND
     ended_at IS NULL) с целью — в т.ч. клиент со staff-ролью;
  B) supervisor + чистый студент из списка супервизора.
Нет доступа: admin сам по себе, посторонний/прежний психолог, другой пользователь,
impersonation. Отказ — один и тот же 404 + user_contacts_read_failed; сбой
обязательного аудита → 503 без значений; пустой результат события не пишет.
"""
import logging
import uuid
from datetime import datetime, timezone

import pytest

import app.supervisor.service as sup_service
import app.user_contacts.service as contacts_service
from app.audit.contracts import AuditStorageError
from app.db.models import (
    AuditLog, AuthLog, DataChangeLog, TherapyEngagement, User,
)
from app.db.session import SessionLocal
from tests.integration.conftest import create_multi_role_user

PHONE = "+79491234567"
PRIMARY = "+7 (949) 000-11-22"
EMAIL = "client.contact@access-test.example"
SECRETS = (PHONE, "79491234567", EMAIL, "000-11-22", "ЗаметныйКонтакт")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _user(client, roles):
    token, uid, _ = create_multi_role_user(client, list(roles))
    return uid, token


def _uuid_of(uid):
    with SessionLocal() as db:
        return str(db.get(User, uid).uuid)


def _contacts_url(uid):
    return f"/api/staff/users/{_uuid_of(uid)}/contacts"


def _seed_contacts(client, token, *, with_phone=True):
    """Владелец сохраняет контакты (и основной телефон) через настоящие endpoint'ы."""
    items = [
        {"id": str(uuid.uuid4()), "type": "phone", "service": None, "value": "8 949 123 45 67",
         "label": None},
        {"id": str(uuid.uuid4()), "type": "email", "service": None, "value": EMAIL, "label": None},
        {"id": str(uuid.uuid4()), "type": "other", "service": None, "value": "ЗаметныйКонтакт",
         "label": "Особый"},
    ]
    r = client.put("/api/auth/profile/contacts", headers=_auth(token),
                   json={"version": 0, "items": items})
    assert r.status_code == 200, r.text
    if with_phone:
        r = client.patch("/api/auth/profile", headers=_auth(token), json={"phone": PRIMARY})
        assert r.status_code == 200, r.text
    return r.json()


def _engage(psy_id, client_id, *, status="active", ended_at=None):
    with SessionLocal() as db:
        eng = TherapyEngagement(
            psychologist_id=psy_id, client_id=client_id, status=status, ended_at=ended_at,
        )
        db.add(eng)
        db.commit()
        return eng.id


def _audit(event, **filters):
    with SessionLocal() as db:
        q = db.query(AuditLog).filter(AuditLog.event_type == event)
        for key, value in filters.items():
            q = q.filter(getattr(AuditLog, key) == value)
        rows = q.order_by(AuditLog.id).all()
        for r in rows:
            db.expunge(r)
        return rows


def _marks():
    with SessionLocal() as db:
        return tuple(
            db.query(m.id).order_by(m.id.desc()).limit(1).scalar() or 0
            for m in (AuditLog, AuthLog, DataChangeLog)
        )


def _rows_since(marks):
    out = []
    with SessionLocal() as db:
        for model, mark in zip((AuditLog, AuthLog, DataChangeLog), marks):
            rows = db.query(model).filter(model.id > mark).order_by(model.id).all()
            for r in rows:
                db.expunge(r)
            out.append(rows)
    return out


def _blob(row):
    return " | ".join(str(getattr(row, c.name, "")) for c in row.__table__.columns)


def _assert_read(response, client_uid, actor_uid, role, marks_before):
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store, private"
    body = response.json()
    assert body["primary_phone"] == PRIMARY
    assert [i["value"] for i in body["items"]][:2] == [PHONE, EMAIL]
    assert "version" not in body                          # версия — деталь владельца
    reads = [r for r in _rows_since(marks_before)[0] if r.event_type == "user_contacts_content_read"]
    (row,) = reads
    assert (row.user_id, row.user_role) == (actor_uid, role)
    assert (row.entity_type, row.entity_id) == ("user", client_uid)
    assert row.outcome == "success" and row.log_metadata == {} and row.description is None
    assert row.failure_reason_code is None
    assert not any(s in _blob(row) for s in SECRETS)


def _assert_denied(response, actor_uid, role, marks_before):
    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Контакты недоступны", "code": "contacts_not_available"}
    assert response.headers["cache-control"] == "no-store, private"
    assert not any(s in response.text for s in SECRETS)
    rows = _rows_since(marks_before)[0]
    assert [r.event_type for r in rows] == ["user_contacts_read_failed"]
    (row,) = rows
    assert (row.user_id, row.user_role) == (actor_uid, role)
    assert row.outcome == "failure" and row.failure_reason_code == "access_denied"
    assert row.entity_type is None and row.log_metadata == {}


@pytest.fixture
def student(client):
    uid, token = _user(client, ["student"])
    _seed_contacts(client, token)
    return uid, token


# ── назначенный психолог ──────────────────────────────────────────────────────

def test_assigned_psychologist_reads_with_exact_audit(client, student):
    sid, _ = student
    pid, ptoken = _user(client, ["psychologist", "student"])
    _engage(pid, sid)
    marks = _marks()
    r = client.get(_contacts_url(sid), headers=_auth(ptoken))
    _assert_read(r, sid, pid, "psychologist", marks)
    assert {"types", "services"} <= set(r.json()["catalog"])


@pytest.mark.parametrize("status,ended", [
    ("completed", None),                                   # статус закрыт, ended_at пуст
    ("active", datetime(2026, 1, 1, tzinfo=timezone.utc)),  # статус active, но завершено
    ("transferred", datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ("cancelled", None),
])
def test_ended_engagement_gives_no_access(client, student, status, ended):
    sid, _ = student
    pid, ptoken = _user(client, ["psychologist", "student"])
    _engage(pid, sid, status=status, ended_at=ended)
    marks = _marks()
    _assert_denied(client.get(_contacts_url(sid), headers=_auth(ptoken)), pid, "psychologist", marks)


def test_real_lifecycle_close_transfer_and_reassign(client, student):
    sid, _ = student
    sup_id, _ = _user(client, ["supervisor", "student"])
    p1, t1 = _user(client, ["psychologist", "student"])
    p2, t2 = _user(client, ["psychologist", "student"])

    eng = sup_service.assign_psychologist(sid, p1, None, sup_id, "supervisor")
    marks = _marks()
    _assert_read(client.get(_contacts_url(sid), headers=_auth(t1)), sid, p1, "psychologist", marks)

    # передача: прежний психолог теряет доступ, новый получает
    sup_service.transfer_psychologist(eng["id"], p2, None, sup_id, "supervisor")
    marks = _marks()
    _assert_denied(client.get(_contacts_url(sid), headers=_auth(t1)), p1, "psychologist", marks)
    marks = _marks()
    _assert_read(client.get(_contacts_url(sid), headers=_auth(t2)), sid, p2, "psychologist", marks)

    # закрытие: доступа нет и у нового
    current = sup_service.close_engagement(
        # актуальная связь клиента — у p2
        _active_engagement_id(sid), None, sup_id, "supervisor")
    assert current["status"] == "completed"
    marks = _marks()
    _assert_denied(client.get(_contacts_url(sid), headers=_auth(t2)), p2, "psychologist", marks)

    # повторное назначение реактивирует строку — доступ возвращается
    sup_service.assign_psychologist(sid, p2, None, sup_id, "supervisor")
    marks = _marks()
    _assert_read(client.get(_contacts_url(sid), headers=_auth(t2)), sid, p2, "psychologist", marks)


def _active_engagement_id(client_id):
    with SessionLocal() as db:
        return db.query(TherapyEngagement.id).filter(
            TherapyEngagement.client_id == client_id,
            TherapyEngagement.status == "active",
            TherapyEngagement.ended_at.is_(None),
        ).scalar()


def test_other_psychologist_is_denied(client, student):
    sid, _ = student
    owner_psy, _ = _user(client, ["psychologist", "student"])
    _engage(owner_psy, sid)
    other_id, other_token = _user(client, ["psychologist", "student"])
    marks = _marks()
    _assert_denied(client.get(_contacts_url(sid), headers=_auth(other_token)),
                   other_id, "psychologist", marks)


# ── супервизор ────────────────────────────────────────────────────────────────

def test_supervisor_reads_a_pure_student_without_engagement(client, student):
    sid, _ = student
    supid, stoken = _user(client, ["supervisor", "student"])
    marks = _marks()
    _assert_read(client.get(_contacts_url(sid), headers=_auth(stoken)), sid, supid, "supervisor", marks)


@pytest.mark.parametrize("mutation", ["disabled", "deleted"])
def test_inactive_or_deleted_student_is_not_available(client, student, mutation):
    sid, _ = student
    supid, stoken = _user(client, ["supervisor", "student"])
    with SessionLocal() as db:
        u = db.get(User, sid)
        if mutation == "disabled":
            u.is_active = False
        else:
            u.deleted_at = datetime.now(timezone.utc)
        db.commit()
    marks = _marks()
    _assert_denied(client.get(_contacts_url(sid), headers=_auth(stoken)), supid, "supervisor", marks)


def test_supervisor_has_no_access_to_a_staff_account_without_engagement(client):
    colleague_id, ctoken = _user(client, ["psychologist", "student"])
    _seed_contacts(client, ctoken)
    supid, stoken = _user(client, ["supervisor", "student"])
    marks = _marks()
    _assert_denied(client.get(_contacts_url(colleague_id), headers=_auth(stoken)),
                   supid, "supervisor", marks)


# ── клиент со staff-ролью (ветка A без требования «чистый студент») ───────────

def test_staff_client_with_active_engagement_psychologist_reads_supervisor_is_denied(client):
    client_id, client_token = _user(client, ["psychologist", "student"])    # клиент со staff-ролью
    _seed_contacts(client, client_token)
    psy_id, psy_token = _user(client, ["psychologist", "student"])
    _engage(psy_id, client_id)
    sup_id, sup_token = _user(client, ["supervisor", "student"])             # без сопровождения
    both_id, both_token = _user(client, ["supervisor", "psychologist", "student"])  # тоже без

    marks = _marks()
    _assert_read(client.get(_contacts_url(client_id), headers=_auth(psy_token)),
                 client_id, psy_id, "psychologist", marks)
    marks = _marks()
    _assert_denied(client.get(_contacts_url(client_id), headers=_auth(sup_token)),
                   sup_id, "supervisor", marks)
    marks = _marks()
    _assert_denied(client.get(_contacts_url(client_id), headers=_auth(both_token)),
                   both_id, "supervisor", marks)      # роль отказа — самая широкая из допустимых


def test_staff_client_access_ends_with_the_engagement(client):
    client_id, client_token = _user(client, ["psychologist", "student"])
    _seed_contacts(client, client_token)
    psy_id, psy_token = _user(client, ["psychologist", "student"])
    eng_id = _engage(psy_id, client_id)
    with SessionLocal() as db:
        eng = db.get(TherapyEngagement, eng_id)
        eng.status, eng.ended_at = "completed", datetime.now(timezone.utc)
        db.commit()
    marks = _marks()
    _assert_denied(client.get(_contacts_url(client_id), headers=_auth(psy_token)),
                   psy_id, "psychologist", marks)


def test_supervisor_who_is_the_assigned_psychologist_reads_via_that_grant(client):
    client_id, client_token = _user(client, ["psychologist", "student"])
    _seed_contacts(client, client_token)
    both_id, both_token = _user(client, ["supervisor", "psychologist", "student"])
    _engage(both_id, client_id)
    marks = _marks()
    _assert_read(client.get(_contacts_url(client_id), headers=_auth(both_token)),
                 client_id, both_id, "psychologist", marks)


def test_multi_role_uses_the_narrowest_grant(client, student):
    sid, _ = student
    both_id, both_token = _user(client, ["supervisor", "psychologist", "student"])
    marks = _marks()
    _assert_read(client.get(_contacts_url(sid), headers=_auth(both_token)),
                 sid, both_id, "supervisor", marks)          # сопровождения нет → грант B
    _engage(both_id, sid)
    marks = _marks()
    _assert_read(client.get(_contacts_url(sid), headers=_auth(both_token)),
                 sid, both_id, "psychologist", marks)        # есть сопровождение → грант A


# ── кому доступа нет вообще ───────────────────────────────────────────────────

def test_admin_alone_other_students_and_anonymous_have_no_access(client, student):
    sid, _ = student
    admin_id, admin_token = _user(client, ["admin"])
    other_id, other_token = _user(client, ["student"])
    marks = _marks()
    for token in (admin_token, other_token):
        r = client.get(_contacts_url(sid), headers=_auth(token))
        assert r.status_code == 403 and not any(s in r.text for s in SECRETS)
    assert client.get(_contacts_url(sid)).status_code == 401
    assert all(rows == [] for rows in _rows_since(marks))      # router-level 403 без аудита


def test_admin_with_psychologist_role_but_no_engagement_is_denied(client, student):
    sid, _ = student
    aid, atoken = _user(client, ["admin", "psychologist"])
    marks = _marks()
    _assert_denied(client.get(_contacts_url(sid), headers=_auth(atoken)), aid, "psychologist", marks)


def test_admin_plus_supervisor_reads_via_supervisor_membership(client, student):
    sid, _ = student
    aid, atoken = _user(client, ["admin", "supervisor"])
    marks = _marks()
    _assert_read(client.get(_contacts_url(sid), headers=_auth(atoken)), sid, aid, "supervisor", marks)


def test_unknown_and_malformed_targets(client):
    supid, stoken = _user(client, ["supervisor", "student"])
    marks = _marks()
    r = client.get(f"/api/staff/users/{uuid.uuid4()}/contacts", headers=_auth(stoken))
    assert r.status_code == 404 and r.json()["code"] == "contacts_not_available"
    assert [x.failure_reason_code for x in _rows_since(marks)[0]] == ["access_denied"]
    bad = client.get("/api/staff/users/not-a-uuid/contacts", headers=_auth(stoken))
    assert bad.status_code == 422 and "not-a-uuid" not in bad.text


# ── impersonation ─────────────────────────────────────────────────────────────

def test_impersonated_psychologist_cannot_read(client, student):
    sid, _ = student
    pid, _ptoken = _user(client, ["psychologist", "student"])
    _engage(pid, sid)
    admin_token = _user(client, ["admin"])[1]
    imp = client.post(f"/api/admin/users/{_uuid_of(pid)}/impersonate",
                      headers=_auth(admin_token)).json()["session_token"]
    marks = _marks()
    r = client.get(_contacts_url(sid), headers=_auth(imp))
    assert r.status_code == 403 and not any(s in r.text for s in SECRETS)
    assert [x.event_type for x in _rows_since(marks)[0] if x.event_type.startswith("user_contacts")] == []


# ── аудит ─────────────────────────────────────────────────────────────────────

def test_audit_failure_returns_no_values(client, student, monkeypatch):
    sid, _ = student
    supid, stoken = _user(client, ["supervisor", "student"])

    def boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(contacts_service, "record_event", boom)
    r = client.get(_contacts_url(sid), headers=_auth(stoken))
    assert r.status_code == 503
    assert r.headers.get("cache-control") != "public"
    assert not any(s in r.text for s in SECRETS)
    assert "items" not in r.text and "primary_phone" not in r.text
    assert _audit("user_contacts_content_read", user_id=supid) == []


def test_nothing_to_disclose_writes_no_event(client):
    sid, _ = _user(client, ["student"])                       # ни контактов, ни телефона
    supid, stoken = _user(client, ["supervisor", "student"])
    marks = _marks()
    r = client.get(_contacts_url(sid), headers=_auth(stoken))
    assert r.status_code == 200
    assert r.json()["items"] == [] and r.json()["primary_phone"] is None
    assert all(rows == [] for rows in _rows_since(marks))


def test_phone_only_is_still_disclosed_under_audit(client):
    sid, stoken_owner = _user(client, ["student"])
    assert client.patch("/api/auth/profile", headers=_auth(stoken_owner),
                        json={"phone": PRIMARY}).status_code == 200
    supid, stoken = _user(client, ["supervisor", "student"])
    marks = _marks()
    r = client.get(_contacts_url(sid), headers=_auth(stoken))
    assert r.json()["primary_phone"] == PRIMARY and r.json()["items"] == []
    assert [x.event_type for x in _rows_since(marks)[0]] == ["user_contacts_content_read"]


def test_owner_reading_own_contacts_writes_no_content_read(client, student):
    sid, stoken = student
    marks = _marks()
    assert client.get("/api/auth/profile/contacts", headers=_auth(stoken)).status_code == 200
    assert all(rows == [] for rows in _rows_since(marks))


def test_values_never_reach_journals_or_logs_on_staff_reads(client, student, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    sid, _ = student
    supid, stoken = _user(client, ["supervisor", "student"])
    other_id, other_token = _user(client, ["psychologist", "student"])
    capsys.readouterr()
    marks = _marks()
    assert client.get(_contacts_url(sid), headers=_auth(stoken)).status_code == 200
    assert client.get(_contacts_url(sid), headers=_auth(other_token)).status_code == 404
    for rows in _rows_since(marks):
        for row in rows:
            assert not any(s in _blob(row) for s in SECRETS), row.__tablename__
    out = capsys.readouterr()
    for secret in SECRETS:
        assert secret not in out.out + out.err + caplog.text
