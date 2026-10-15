"""
ADR-031 — gated integration: контакты владельца на реальном PostgreSQL
(isolated runner).

  * сохранение / повторное чтение / изменение / удаление / пустой список; GET
    пустого списка строки не создаёт; «пустое поверх пустого» — no-op;
  * шифрование в БД (`enc:v1:`, нет подстрок значений), нормализация;
  * контакты НЕ попадают в /me, login, /auth/profile, admin-DTO, списки
    супервизора и карточку психолога;
  * конфликт версий (тело без значений), повтор после потерянного ответа — no-op
    без новой версии и события, гонка двух потоков с одной версией;
  * точные строки аудита profile_updated(fields=["contacts"]) и failure-события;
    сбой аудита / commit откатывает запись; значения не попадают в журналы/логи;
  * санитизированный 422 (лишнее поле с синтетическим email — не эхом);
  * impersonation закрыт.
"""
import logging
import threading
import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

import app.user_contacts.storage as contacts_storage
from app.audit.contracts import AuditStorageError
from app.db.models import (
    AuditLog, AuthLog, DataChangeLog, TherapyEngagement, User, UserContacts,
)
from app.db.session import SessionLocal, engine
from app.user_contacts.errors import ContactsStorageError, ContactsVersionConflict
from tests.integration.conftest import create_multi_role_user

URL = "/api/auth/profile/contacts"
PHONE = "+79491234567"
EMAIL = "extra.person@contacts-test.example"
OTHER_VALUE = "ЛичныйКонтакт-7f31"
SITE = "https://site-7f31.example.org/page"
SECRETS = (PHONE, EMAIL, OTHER_VALUE, "site-7f31", "7949123")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _user(client, roles=("student",)):
    token, uid, _ = create_multi_role_user(client, list(roles))
    return uid, token


def _item(**o):
    base = {"id": str(uuid.uuid4()), "type": "phone", "service": None,
            "value": "8 (949) 123-45-67", "label": None}
    base.update(o)
    return base


def _full_set():
    return [
        _item(label="Личный"),
        _item(type="email", value=EMAIL.upper()),
        _item(type="other", value=OTHER_VALUE, label="Особый способ"),
        _item(type="website", value="site-7f31.example.org/page"),
    ]


def _put(client, token, version, items):
    return client.put(URL, headers=_auth(token), json={"version": version, "items": items})


def _row(uid):
    with SessionLocal() as db:
        row = db.query(UserContacts).filter(UserContacts.user_id == uid).first()
        if row is not None:
            db.expunge(row)
        return row


def _audit(event_name, **filters):
    with SessionLocal() as db:
        q = db.query(AuditLog).filter(AuditLog.event_type == event_name)
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


def _profile_updated(uid):
    return [r for r in _audit("profile_updated", user_id=uid)
            if r.log_metadata.get("fields") == ["contacts"]]


# ── чтение, сохранение, цикл ──────────────────────────────────────────────────

def test_get_of_an_empty_list_creates_nothing(client):
    uid, token = _user(client)
    marks = _marks()
    r = client.get(URL, headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["version"], body["items"], body["updated_at"]) == (0, [], None)
    assert body["limits"] == {"max_items": 10, "label_max": 80, "value_max": 500}
    assert {t["code"] for t in body["catalog"]["types"]} >= {"phone", "email", "website"}
    assert r.headers["cache-control"] == "no-store, private"
    assert _row(uid) is None
    assert all(rows == [] for rows in _rows_since(marks))


def test_unauthenticated_is_401(client):
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"version": 0, "items": []}).status_code == 401


def test_save_reload_update_delete_cycle(client):
    uid, token = _user(client)
    items = _full_set()
    r = _put(client, token, 0, items)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed"] is True and body["version"] == 1
    assert r.headers["cache-control"] == "no-store, private"
    assert [i["value"] for i in body["items"]] == [
        "+79491234567", EMAIL, OTHER_VALUE, "https://site-7f31.example.org/page"]
    assert [i["id"] for i in body["items"]] == [i["id"] for i in items]   # id не меняется

    again = client.get(URL, headers=_auth(token)).json()
    assert again["version"] == 1 and again["items"] == body["items"]

    # изменение и удаление элемента
    changed = [dict(body["items"][0], label="Рабочий")] + body["items"][2:]
    r = _put(client, token, 1, changed)
    assert r.json()["version"] == 2 and len(r.json()["items"]) == 3
    r = _put(client, token, 2, [])
    assert r.status_code == 200 and r.json()["version"] == 3 and r.json()["items"] == []
    # строка НЕ удаляется (версия не сбрасывается в 0), список пуст
    assert _row(uid).version == 3
    assert client.get(URL, headers=_auth(token)).json()["items"] == []
    assert len(_profile_updated(uid)) == 3


def test_ciphertext_at_rest_has_no_plaintext(client):
    uid, token = _user(client)
    assert _put(client, token, 0, _full_set()).status_code == 200
    with engine.connect() as conn:
        enc = conn.execute(
            text("SELECT contacts_enc FROM user_contacts WHERE user_id = :u"), {"u": uid}
        ).scalar()
    assert enc.startswith("enc:v1:")
    for secret in SECRETS + ("Особый способ", "Личный"):
        assert secret not in enc


def test_empty_over_empty_is_a_noop_without_a_row(client):
    uid, token = _user(client)
    marks = _marks()
    r = _put(client, token, 0, [])
    assert r.status_code == 200 and r.json()["changed"] is False and r.json()["version"] == 0
    assert _row(uid) is None
    assert all(rows == [] for rows in _rows_since(marks))


def test_staff_owner_can_manage_own_contacts_with_membership_role(client):
    uid, token = _user(client, ("psychologist", "student"))
    assert _put(client, token, 0, [_item()]).status_code == 200
    (row,) = _profile_updated(uid)
    assert row.user_role == "psychologist"          # роль определена по membership


# ── аудит ─────────────────────────────────────────────────────────────────────

def test_success_audit_row_is_exact_and_has_no_values(client):
    uid, token = _user(client)
    marks = _marks()
    assert _put(client, token, 0, _full_set()).status_code == 200
    audit, auth, dcl = _rows_since(marks)
    assert [a.event_type for a in audit] == ["profile_updated"] and auth == [] and dcl == []
    row = audit[0]
    assert (row.user_id, row.user_role) == (uid, "student")
    assert (row.entity_type, row.entity_id) == ("user", uid)
    assert row.log_metadata == {"fields": ["contacts"]}
    assert row.outcome == "success" and row.failure_reason_code is None
    assert row.description is None
    assert not any(s in _blob(row) for s in SECRETS)


def test_lost_response_retry_is_a_noop_without_new_version_or_event(client):
    uid, token = _user(client)
    items = _full_set()
    first = _put(client, token, 0, items)
    assert first.status_code == 200 and first.json()["version"] == 1
    stored = _row(uid)
    events_before = len(_profile_updated(uid))
    marks = _marks()

    retry = _put(client, token, 0, items)           # тот же payload и та же (устаревшая) версия
    assert retry.status_code == 200, retry.text
    assert retry.json()["changed"] is False and retry.json()["version"] == 1
    assert retry.json()["items"] == first.json()["items"]
    after = _row(uid)
    assert (after.version, after.updated_at, after.contacts_enc) == (
        stored.version, stored.updated_at, stored.contacts_enc)
    assert len(_profile_updated(uid)) == events_before == 1
    assert all(rows == [] for rows in _rows_since(marks))


def test_stale_version_with_different_content_is_a_clean_409(client):
    uid, token = _user(client)
    assert _put(client, token, 0, _full_set()).status_code == 200
    stored = _row(uid)
    marks = _marks()
    r = _put(client, token, 0, [_item(value="+7 949 000 00 00")])
    assert r.status_code == 409
    assert r.json() == {
        "detail": "Контакты были изменены в другом окне или на другом устройстве. "
                  "Ваши правки не потеряны.",
        "code": "contacts_version_conflict",
        "current_version": 1,
    }
    assert r.headers["cache-control"] == "no-store, private"
    assert not any(s in r.text for s in SECRETS)
    assert _row(uid).contacts_enc == stored.contacts_enc            # ничего не перезаписано
    (failure,) = [a for a in _rows_since(marks)[0]]
    assert failure.event_type == "profile_update_failed"
    assert failure.outcome == "failure" and failure.failure_reason_code == "contacts_version_conflict"
    assert (failure.user_id, failure.user_role) == (uid, "student")
    assert failure.entity_type is None and failure.log_metadata == {}


def test_future_version_is_also_a_conflict(client):
    _, token = _user(client)
    assert _put(client, token, 5, [_item()]).status_code == 409


# ── валидация ─────────────────────────────────────────────────────────────────

def test_validation_errors_are_structured_audited_and_value_free(client):
    uid, token = _user(client)
    marks = _marks()
    bad = [_item(type="website", value="javascript:" + EMAIL), _item(value="12"),
           _item(type="other", value=OTHER_VALUE)]
    r = _put(client, token, 0, bad)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "contacts_invalid" and body["detail"] == "Проверьте поля контактов"
    assert body["errors"] == [
        {"index": 0, "field": "value", "code": "unsafe_url"},
        {"index": 1, "field": "value", "code": "invalid_phone"},
        {"index": 2, "field": "label", "code": "label_required"},
    ]
    assert not any(s in r.text for s in SECRETS)
    assert _row(uid) is None
    (failure,) = _rows_since(marks)[0]
    assert (failure.event_type, failure.failure_reason_code) == ("profile_update_failed", "invalid_request")


def test_missing_or_duplicate_ids_are_rejected_not_generated(client):
    uid, token = _user(client)
    no_id = {"type": "phone", "value": PHONE}
    r = _put(client, token, 0, [no_id])
    assert r.status_code == 422 and r.json()["errors"] == [
        {"index": 0, "field": "id", "code": "required"}]
    same = str(uuid.uuid4())
    r = _put(client, token, 0, [_item(id=same), _item(id=same, value="+7 949 000 00 01")])
    assert r.json()["errors"] == [{"index": 1, "field": "id", "code": "duplicate_id"}]
    assert _row(uid) is None


def test_more_than_ten_items_is_rejected(client):
    _, token = _user(client)
    items = [_item(value=f"+7949000{i:04d}") for i in range(11)]
    r = _put(client, token, 0, items)
    assert r.status_code == 422 and r.json()["errors"] == [
        {"index": None, "field": "items", "code": "too_many"}]


@pytest.mark.parametrize("body", [
    {"version": 0, "items": [], "junk.person@leak.example": 1},
    {"version": 0, "items": [{"id": str(uuid.uuid4()), "type": "phone", "value": PHONE,
                              "junk.person@leak.example": 1}]},
    {"version": "x", "items": []},
    {"version": -1, "items": []},
    {"version": 0, "items": [{"id": str(uuid.uuid4()), "type": "phone", "value": [PHONE]}]},
])
def test_shape_errors_do_not_echo_input_or_field_names(client, body, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    _, token = _user(client)
    capsys.readouterr()
    r = client.put(URL, headers=_auth(token), json=body)
    assert r.status_code == 422
    for needle in ("junk.person", "leak.example", PHONE, "input"):
        assert needle not in r.text
    assert all(set(e) == {"index", "field", "code"} for e in r.json()["errors"])
    out = capsys.readouterr()
    for needle in ("junk.person", "leak.example", PHONE):
        assert needle not in out.out + out.err + caplog.text


def test_malformed_json_is_sanitized(client):
    _, token = _user(client)
    r = client.put(URL, headers={**_auth(token), "content-type": "application/json"},
                   content=('{"version": 0, "items": [' + EMAIL).encode())
    assert r.status_code == 422 and EMAIL not in r.text
    assert r.json()["errors"][0]["code"] == "invalid_json"


# ── impersonation ─────────────────────────────────────────────────────────────

def test_owner_endpoints_are_closed_in_impersonation(client):
    uid, token = _user(client)
    assert _put(client, token, 0, [_item()]).status_code == 200
    admin_token, _, _ = create_multi_role_user(client, ["admin"])
    with SessionLocal() as db:
        target_uuid = str(db.get(User, uid).uuid)
    imp = client.post(f"/api/admin/users/{target_uuid}/impersonate",
                      headers=_auth(admin_token)).json()["session_token"]
    marks = _marks()
    for r in (client.get(URL, headers=_auth(imp)), _put(client, imp, 1, [])):
        assert r.status_code == 403 and PHONE not in r.text and "items" not in r.json()
    # битое тело от impersonation-сессии: 403 побеждает ошибки полей
    r = client.put(URL, headers=_auth(imp), json={"version": "x", "junk": 1})
    assert r.status_code == 403
    assert _row(uid).version == 1
    assert all(rows == [] for rows in _rows_since(marks))


# ── отсутствие утечек в других DTO ────────────────────────────────────────────

def test_contacts_are_absent_from_unrelated_responses(client):
    suid, stoken = _user(client)
    with SessionLocal() as db:
        student = db.get(User, suid)
        student.phone = "+7 (949) 000-11-22"
        email, student_uuid = student.email, str(student.uuid)
        db.commit()
    assert _put(client, stoken, 0, _full_set()).status_code == 200

    admin_token, _, _ = create_multi_role_user(client, ["admin"])
    sup_token, _, _ = create_multi_role_user(client, ["supervisor", "student"])
    psy_token, psy_id, _ = create_multi_role_user(client, ["psychologist", "student"])
    with SessionLocal() as db:
        db.add(TherapyEngagement(psychologist_id=psy_id, client_id=suid, status="active"))
        db.commit()

    responses = {
        "me": client.get("/api/auth/me", headers=_auth(stoken)),
        "profile": client.get("/api/auth/profile", headers=_auth(stoken)),
        "login": client.post("/api/auth/login",
                             json={"email": email, "password": "SecurePass42!"}),
        "admin_list": client.get("/api/admin/users/", headers=_auth(admin_token),
                                 params={"search": email, "include_deleted": "true"}),
        "admin_detail": client.get(f"/api/admin/users/{student_uuid}", headers=_auth(admin_token)),
        "supervisor_students": client.get("/api/supervisor/students", headers=_auth(sup_token),
                                          params={"search": email}),
        "psychologist_card": client.get(f"/api/psychologist/students/{suid}",
                                        headers=_auth(psy_token)),
    }
    for name, r in responses.items():
        assert r.status_code == 200, (name, r.status_code, r.text[:200])
        assert not any(s in r.text for s in SECRETS), name
        assert "contacts" not in r.text.lower(), name


# ── failure-injection ─────────────────────────────────────────────────────────

def test_audit_failure_rolls_back_the_write(client, monkeypatch):
    uid, token = _user(client)

    def boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(contacts_storage, "record_event", boom)
    marks = _marks()
    r = _put(client, token, 0, _full_set())
    assert r.status_code == 503 and not any(s in r.text for s in SECRETS)
    assert _row(uid) is None
    assert _rows_since(marks)[0] == []             # ни profile_updated, ни ложного failure


def test_audit_failure_keeps_previous_version(client, monkeypatch):
    uid, token = _user(client)
    assert _put(client, token, 0, [_item()]).status_code == 200
    before = _row(uid)

    def boom(**kwargs):
        raise AuditStorageError("audit storage failure")

    monkeypatch.setattr(contacts_storage, "record_event", boom)
    assert _put(client, token, 1, []).status_code == 503
    after = _row(uid)
    assert (after.version, after.contacts_enc) == (before.version, before.contacts_enc)


def test_commit_failure_rolls_back_and_is_not_audited_as_business_failure(client, capsys):
    uid, token = _user(client)
    state = {"wrote": False}

    def _mark(conn, cursor, statement, parameters, context, executemany):
        if "user_contacts" in statement and statement.lstrip().upper().startswith(("INSERT", "UPDATE")):
            state["wrote"] = True

    def _fail_commit(session):
        if state["wrote"]:
            state["wrote"] = False
            raise OperationalError("COMMIT /* SQL-MARKER */", {"c": EMAIL}, Exception("driver"))

    event.listen(engine, "before_cursor_execute", _mark)
    event.listen(SessionLocal.class_, "before_commit", _fail_commit)
    marks = _marks()
    try:
        with pytest.raises(ContactsStorageError):
            _put(client, token, 0, _full_set())
    finally:
        event.remove(engine, "before_cursor_execute", _mark)
        event.remove(SessionLocal.class_, "before_commit", _fail_commit)
    err = capsys.readouterr().err
    assert "phase=commit error=OperationalError" in err
    assert "SQL-MARKER" not in err and EMAIL not in err
    assert _row(uid) is None
    assert _rows_since(marks)[0] == []             # неоднозначный commit — без *_failed


# ── гонка ─────────────────────────────────────────────────────────────────────

def test_two_concurrent_saves_with_the_same_version_one_wins(client):
    uid, _ = _user(client)
    barrier = threading.Barrier(2)
    results = []

    def worker(value):
        items = [{"id": str(uuid.uuid4()), "type": "phone", "service": None,
                  "value": value, "label": None}]
        barrier.wait()
        try:
            results.append(("ok", contacts_storage.save_atomic(
                uid, 0, items, actor_role="student")))
        except ContactsVersionConflict as exc:
            results.append(("conflict", exc.current_version))

    threads = [threading.Thread(target=worker, args=(v,)) for v in ("+79490000001", "+79490000002")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    kinds = sorted(kind for kind, _ in results)
    assert kinds == ["conflict", "ok"], results
    assert [v for kind, v in results if kind == "conflict"] == [1]
    assert _row(uid).version == 1
    assert len(_profile_updated(uid)) == 1


# ── журналы и логи ────────────────────────────────────────────────────────────

def test_values_never_reach_journals_or_logs(client, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    uid, token = _user(client)
    capsys.readouterr()
    marks = _marks()
    _put(client, token, 0, _full_set())
    _put(client, token, 0, [_item(value="+7 949 555 55 55")])           # конфликт
    _put(client, token, 1, [_item(type="website", value="javascript:x")])  # валидация
    client.get(URL, headers=_auth(token))
    for rows in _rows_since(marks):
        for row in rows:
            assert not any(s in _blob(row) for s in SECRETS + ("555 55 55", "javascript")), row.__tablename__
    out = capsys.readouterr()
    for secret in SECRETS:
        assert secret not in out.out + out.err + caplog.text
