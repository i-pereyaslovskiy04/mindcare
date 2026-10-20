"""
ADR-032 — контакты пользователя, unit-тесты БЕЗ БД.

  * ContactsRoute на мини-приложении: тело 422 строится из закрытых allowlist'ов,
    ни значения, ни имена лишних полей (в т.ч. синтетический email) не попадают
    ни в ответ, ни в логи; 403 guard'а побеждает ошибки полей;
  * service на фейковом storage: доменные ошибки, порядок «аудит → ответ»,
    fail-closed, отсутствие события при пустом результате;
  * service не импортирует FastAPI / app.auth.deps и не вызывает resolve_role_or_403;
  * storage: любая техническая ошибка санитизируется (SQL/параметры/шифртекст
    не попадают в traceback и stderr), шифртекст корректно кодирует/декодирует.
"""
import ast
import json
import logging
import traceback
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.user_contacts.service as service
import app.user_contacts.storage as storage
from app.audit.contracts import AuditStorageError
from app.core.encryption import ENCRYPTION_PREFIX, encrypt_text
from app.user_contacts import catalog
from app.user_contacts.context import OwnerContext, StaffContext
from app.user_contacts.errors import (
    ERROR_CODES, FIELD_NAMES, ContactsNotAvailable, ContactsStorageError,
    ContactsValidationError, ContactsVersionConflict,
)
from app.user_contacts.sanitized_route import ContactsRoute
from app.user_contacts.schemas import ContactsSaveIn

SECRET = "secret.person@private-mail.example"


# ── ContactsRoute на мини-приложении ──────────────────────────────────────────

def _guard(x_block: str = ""):
    if x_block:
        raise HTTPException(status_code=403, detail="guard")


def _make_client(raise_server_exceptions=True):
    router = APIRouter(route_class=ContactsRoute, dependencies=[Depends(_guard)])

    @router.put("/contacts")
    def put(body: ContactsSaveIn):
        return {"ok": True, "n": len(body.items)}

    @router.get("/bad-response", response_model=dict[str, int])
    def bad_response():
        return {"value": SECRET}      # str вместо int → ResponseValidationError

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _item(**o):
    base = {"id": str(uuid.uuid4()), "type": "phone", "value": "+79491234567"}
    base.update(o)
    return base


@pytest.fixture
def client():
    return _make_client()


def _assert_clean(response, capsys, caplog):
    assert SECRET not in response.text and "private-mail" not in response.text
    out = capsys.readouterr()
    assert SECRET not in out.out + out.err and SECRET not in caplog.text
    for err in response.json().get("errors", []):
        assert set(err) == {"index", "field", "code"}
        assert err["field"] is None or err["field"] in FIELD_NAMES
        assert err["code"] in ERROR_CODES


def test_top_level_extra_field_named_like_an_email_is_not_echoed(client, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    r = client.put("/contacts", json={"version": 0, "items": [], SECRET: "x"})
    assert r.status_code == 422
    assert r.json()["errors"] == [{"index": None, "field": None, "code": "unknown_field"}]
    assert r.headers["cache-control"] == "no-store, private"
    _assert_clean(r, capsys, caplog)


def test_nested_extra_field_named_like_an_email_is_not_echoed(client, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    r = client.put("/contacts", json={"version": 0, "items": [
        _item(), _item(type="email", value="a@b.ru", **{SECRET: 1})]})
    assert r.status_code == 422
    assert r.json()["errors"] == [{"index": 1, "field": None, "code": "unknown_field"}]
    _assert_clean(r, capsys, caplog)


def test_value_of_the_wrong_type_is_not_echoed(client, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    r = client.put("/contacts", json={"version": 0, "items": [_item(value=[SECRET])]})
    assert r.status_code == 422
    assert r.json()["errors"] == [{"index": 0, "field": "value", "code": "invalid_type"}]
    _assert_clean(r, capsys, caplog)


def test_malformed_json_with_a_value_inside_is_not_echoed(client, capsys, caplog):
    caplog.set_level(logging.DEBUG)
    r = client.put("/contacts", content=('{"version": 0, "items": [' + SECRET).encode(),
                   headers={"content-type": "application/json"})
    assert r.status_code == 422
    assert r.json()["errors"][0]["code"] == "invalid_json"
    _assert_clean(r, capsys, caplog)


@pytest.mark.parametrize("body,expected", [
    ({"version": 0, "items": [{"type": "phone", "value": "+79491234567"}]},
     {"index": 0, "field": "id", "code": "required"}),
    ({"version": 0, "items": [_item(value="x" * 2001)]},
     {"index": 0, "field": "value", "code": "too_long"}),
    ({"version": 0, "items": [_item() for _ in range(51)]},
     {"index": None, "field": "items", "code": "too_many"}),
    ({"version": -1, "items": []}, {"index": None, "field": "version", "code": "out_of_range"}),
    ({"version": "abc", "items": []}, {"index": None, "field": "version", "code": "invalid_type"}),
    ({"items": []}, {"index": None, "field": "version", "code": "required"}),
    ({"version": 0, "items": "x"}, {"index": None, "field": "items", "code": "invalid_type"}),
])
def test_shape_errors_use_closed_vocabulary(client, body, expected):
    r = client.put("/contacts", json=body)
    assert r.status_code == 422
    assert r.json()["detail"] == "Проверьте поля контактов"
    assert r.json()["code"] == "contacts_invalid"
    assert expected in r.json()["errors"]
    assert "input" not in r.text and "ctx" not in r.text


def test_guard_forbidden_wins_over_body_errors(client):
    r = client.put("/contacts?x_block=1", json={"version": "abc", SECRET: 1})
    assert r.status_code == 403
    assert SECRET not in r.text


def test_valid_body_passes(client):
    assert client.put("/contacts", json={"version": 0, "items": [_item()]}).json() == {"ok": True, "n": 1}


def test_response_validation_error_is_sanitized(capsys):
    client = _make_client(raise_server_exceptions=False)
    r = client.get("/bad-response")
    assert r.status_code == 500 and SECRET not in r.text
    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err
    assert "ResponseValidationError" in captured.err


# ── service ───────────────────────────────────────────────────────────────────

class _Spy:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise self.fail


def _grant(role="psychologist", phone=None):
    return {"target_id": 77, "acting_role": role, "primary_phone": phone}


def _snap(items):
    return {"version": 3, "updated_at": None, "items": items}


STAFF = StaffContext(user_id=5, roles=frozenset({"psychologist", "supervisor"}))


def test_staff_without_grant_gets_not_available_and_no_audit(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(service, "record_event", spy)
    monkeypatch.setattr(service.storage, "resolve_staff_grant", lambda *a, **k: None)
    with pytest.raises(ContactsNotAvailable):
        service.read_for_staff(STAFF, uuid.uuid4())
    assert spy.calls == []


def test_staff_read_audits_before_returning_with_the_granting_role(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(service, "record_event", spy)
    monkeypatch.setattr(service.storage, "resolve_staff_grant",
                        lambda *a, **k: _grant("supervisor", "+79490000000"))
    item = {"id": str(uuid.uuid4()), "type": "phone", "service": None,
            "value": "+79491234567", "label": None}
    monkeypatch.setattr(service.storage, "read_snapshot", lambda *a, **k: _snap([item]))
    out = service.read_for_staff(STAFF, uuid.uuid4(), ip="127.0.0.1", user_agent="ua")
    (call,) = spy.calls
    assert call["event"] == "user_contacts_content_read"
    assert call["actor"].user_id == 5 and call["actor"].role == "supervisor"
    assert call["target"].entity_type == "user" and call["target"].entity_id == 77
    assert call["metadata"] == {} and "db" not in call
    assert out["primary_phone"] == "+79490000000" and out["items"] == [item]


def test_audit_failure_returns_no_values(monkeypatch):
    monkeypatch.setattr(service, "record_event", _Spy(fail=AuditStorageError("x")))
    monkeypatch.setattr(service.storage, "resolve_staff_grant", lambda *a, **k: _grant(phone="+7949"))
    monkeypatch.setattr(service.storage, "read_snapshot", lambda *a, **k: _snap([]))
    with pytest.raises(AuditStorageError):
        service.read_for_staff(STAFF, uuid.uuid4())


def test_nothing_to_disclose_writes_no_event(monkeypatch):
    spy = _Spy()
    monkeypatch.setattr(service, "record_event", spy)
    monkeypatch.setattr(service.storage, "resolve_staff_grant", lambda *a, **k: _grant(phone=None))
    monkeypatch.setattr(service.storage, "read_snapshot", lambda *a, **k: None)
    out = service.read_for_staff(STAFF, uuid.uuid4())
    assert spy.calls == [] and out["items"] == [] and out["primary_phone"] is None


def test_owner_empty_read_and_save_validation(monkeypatch):
    monkeypatch.setattr(service.storage, "read_snapshot", lambda *a, **k: None)
    out = service.get_my_contacts(1)
    assert (out["version"], out["items"], out["updated_at"]) == (0, [], None)
    assert out["limits"] == {"max_items": 10, "label_max": 80, "value_max": 500}
    assert {c["code"] for c in out["catalog"]["types"]} == catalog.TYPE_CODES

    saved = []
    monkeypatch.setattr(service.storage, "save_atomic", lambda *a, **k: saved.append((a, k)))
    with pytest.raises(ContactsValidationError):
        service.save_my_contacts(OwnerContext(1, "student"), 0, [{"type": "phone"}])
    assert saved == []                     # невалидное не доходит до storage


def test_owner_save_passes_normalized_items_and_role(monkeypatch):
    captured = {}

    def fake_save(user_id, version, items, **kwargs):
        captured.update(user_id=user_id, version=version, items=items, **kwargs)
        return {"version": 1, "updated_at": None, "items": items, "changed": True}

    monkeypatch.setattr(service.storage, "save_atomic", fake_save)
    raw = [{"id": str(uuid.uuid4()), "type": "phone", "value": "8 949 123 45 67"}]
    out = service.save_my_contacts(OwnerContext(9, "psychologist"), 0, raw, ip="1.1.1.1")
    assert captured["items"][0]["value"] == "+79491234567"
    assert captured["actor_role"] == "psychologist" and captured["user_id"] == 9
    assert out["changed"] is True and out["version"] == 1


def test_version_conflict_propagates(monkeypatch):
    def boom(*a, **k):
        raise ContactsVersionConflict(4)

    monkeypatch.setattr(service.storage, "save_atomic", boom)
    raw = [{"id": str(uuid.uuid4()), "type": "phone", "value": "+79491234567"}]
    with pytest.raises(ContactsVersionConflict) as info:
        service.save_my_contacts(OwnerContext(1, "student"), 0, raw)
    assert info.value.current_version == 4


def test_service_has_no_http_dependencies():
    source = Path(service.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert not any(m == "fastapi" or m.startswith("fastapi.") for m in imported)
    assert "app.auth.deps" not in imported
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not {"resolve_role_or_403", "HTTPException", "Depends"} & used


# ── storage: санитизация и шифрование ─────────────────────────────────────────

SQL_MARKER = "SQL-MARKER-4c1d"
CIPHER_MARKER = "enc:v1:CIPHER-MARKER-4c1d"


def _synthetic():
    return OperationalError(
        f"UPDATE user_contacts SET contacts_enc=%(c)s /* {SQL_MARKER} */",
        {"c": CIPHER_MARKER}, SimpleNamespace(),
    )


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row

    def scalar(self):
        return self._row


class _FakeDb:
    def __init__(self, execute=None):
        self._execute = execute
        self.rolled_back = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        return self._execute()

    def rollback(self):
        self.rolled_back += 1


def _assert_sanitized(exc, err):
    assert isinstance(exc, ContactsStorageError)
    assert exc.__cause__ is None and exc.__context__ is None
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    for marker in (SQL_MARKER, CIPHER_MARKER, "UPDATE user_contacts"):
        assert marker not in rendered and marker not in err


def test_read_error_is_sanitized(monkeypatch, capsys):
    def boom():
        raise _synthetic()

    db = _FakeDb(boom)
    monkeypatch.setattr(storage, "SessionLocal", lambda: db)
    with pytest.raises(ContactsStorageError) as info:
        storage.read_snapshot(1)
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert "op=read phase=read error=OperationalError" in err and db.rolled_back == 1


def test_grant_and_save_read_errors_are_sanitized(monkeypatch, capsys):
    def boom():
        raise _synthetic()

    monkeypatch.setattr(storage, "SessionLocal", lambda: _FakeDb(boom))
    with pytest.raises(ContactsStorageError) as info:
        storage.resolve_staff_grant(1, {"psychologist"}, uuid.uuid4())
    _assert_sanitized(info.value, capsys.readouterr().err)
    with pytest.raises(ContactsStorageError) as info:
        storage.save_atomic(1, 0, [], actor_role="student")
    _assert_sanitized(info.value, capsys.readouterr().err)


def test_corrupted_ciphertext_is_reported_without_values(monkeypatch, capsys):
    row = SimpleNamespace(version=1, updated_at=None, contacts_enc=ENCRYPTION_PREFIX + "garbage")
    monkeypatch.setattr(storage, "SessionLocal", lambda: _FakeDb(lambda: _Result(row)))
    with pytest.raises(ContactsStorageError) as info:
        storage.read_snapshot(1)
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert "Undecodable" in err and "garbage" not in err


def test_envelope_roundtrip_and_format():
    item = {"id": str(uuid.uuid4()), "type": "other", "service": None,
            "value": "Кириллица ✓", "label": "Название"}
    enc = storage._encode([item])
    assert enc.startswith(ENCRYPTION_PREFIX) and "Кириллица" not in enc
    assert storage._decode(enc) == [item]
    # неверная версия конверта / не список → не расшифровывается
    for payload in ({"v": 2, "items": []}, {"v": 1, "items": "x"}, [1, 2]):
        with pytest.raises(storage._Undecodable):
            storage._decode(encrypt_text(json.dumps(payload)))


def test_equal_content_is_a_noop_even_with_a_stale_version(monkeypatch):
    item = {"id": str(uuid.uuid4()), "type": "phone", "service": None,
            "value": "+79491234567", "label": None}
    row = SimpleNamespace(version=5, updated_at="T", contacts_enc=storage._encode([item]))
    db = _FakeDb(lambda: _Result(row))
    monkeypatch.setattr(storage, "SessionLocal", lambda: db)
    monkeypatch.setattr(storage, "record_event", _Spy(fail=AssertionError("audit on no-op")))
    out = storage.save_atomic(1, 2, [item], actor_role="student")      # версия устарела
    assert out == {"version": 5, "updated_at": "T", "items": [item], "changed": False}


def test_empty_over_empty_is_a_noop_without_a_row(monkeypatch):
    db = _FakeDb(lambda: _Result(None))
    monkeypatch.setattr(storage, "SessionLocal", lambda: db)
    out = storage.save_atomic(1, 0, [], actor_role="student")
    assert out["changed"] is False and out["version"] == 0 and out["items"] == []


def test_stale_version_with_different_content_conflicts(monkeypatch):
    item = {"id": str(uuid.uuid4()), "type": "phone", "service": None,
            "value": "+79491234567", "label": None}
    row = SimpleNamespace(version=5, updated_at=None, contacts_enc=storage._encode([item]))
    monkeypatch.setattr(storage, "SessionLocal", lambda: _FakeDb(lambda: _Result(row)))
    with pytest.raises(ContactsVersionConflict) as info:
        storage.save_atomic(1, 2, [], actor_role="student")
    assert info.value.current_version == 5


def test_error_objects_carry_no_values():
    err = ContactsVersionConflict(3)
    assert "3" not in err.message and err.code == "contacts_version_conflict"
    assert ContactsNotAvailable().status_code == 404
