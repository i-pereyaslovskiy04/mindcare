"""
ADR-033 — задания психолога клиенту, unit-тесты БЕЗ БД.

  * AssignmentsRoute на мини-приложении: no-store на каждом ответе; 422 без
    значений и имён лишних полей; HTTPException зависимостей сохраняет статус;
    AuditError → строго 503 (не 500); прочее → 500 без деталей;
  * validators: текст, курсор keyset (битый курсор → invalid_cursor);
  * service: fail-closed чтение психологом (событие на каждое задание страницы
    ДО ответа, сбой → ничего не возвращается), пустая страница без событий,
    просроченность по московской дате;
  * storage: решения переходов (no-op / конфликт / завершённое сопровождение)
    и санитизация технических сбоев (SQL/параметры/шифртекст не утекают);
  * service не импортирует FastAPI / app.auth.deps.
"""
import ast
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.assignments.service as service
import app.assignments.storage as storage
from app.assignments import validators
from app.assignments.context import ClientContext, PsychologistContext
from app.assignments.errors import (
    ERROR_CODES, FIELD_NAMES, AssignmentEngagementInactive, AssignmentFinalized,
    AssignmentNotAvailable, AssignmentsStorageError, AssignmentValidationError,
)
from app.assignments.sanitized_route import NO_STORE, AssignmentsRoute
from app.assignments.schemas import AssignmentCreateIn
from app.audit.contracts import AuditStorageError
from app.core.encryption import ENCRYPTION_PREFIX, encrypt_text

SECRET = "Секретный текст задания про тревогу клиента"


# ── AssignmentsRoute ──────────────────────────────────────────────────────────

def _mini_app():
    router = APIRouter(route_class=AssignmentsRoute)

    def deny():
        raise HTTPException(status_code=403, detail="forbidden",
                            headers={"WWW-Authenticate": "Bearer"})

    @router.post("/create/{student_uuid}")
    def create(student_uuid: uuid.UUID, body: AssignmentCreateIn):
        return {"ok": True}

    @router.get("/denied", dependencies=[Depends(deny)])
    def denied():
        return {"ok": True}

    @router.get("/audit")
    def audit():
        raise AuditStorageError("audit down: " + SECRET)

    @router.get("/boom")
    def boom():
        raise RuntimeError(SECRET)

    @router.get("/ok")
    def ok():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_success_response_is_no_store():
    res = _mini_app().get("/ok")
    assert res.status_code == 200 and res.headers["cache-control"] == NO_STORE


def test_422_has_no_values_and_no_unknown_field_names(capsys):
    client = _mini_app()
    res = client.post(f"/create/{uuid.uuid4()}", json={
        "text": 123,                      # неверный тип: input не должен вернуться
        "due_date": SECRET,               # битая дата с «персональным» значением
        SECRET: SECRET,                   # лишнее поле: имя — чьё-то значение
    })
    assert res.status_code == 422 and res.headers["cache-control"] == NO_STORE
    body = res.json()
    assert body["code"] == "assignment_invalid"
    raw = res.text
    assert SECRET not in raw and "123" not in raw
    for err in body["errors"]:
        assert err["field"] is None or err["field"] in FIELD_NAMES
        assert err["code"] in ERROR_CODES
    fields = {(e["field"], e["code"]) for e in body["errors"]}
    assert ("text", "invalid_type") in fields
    assert ("due_date", "invalid_date") in fields
    assert (None, "unknown_field") in fields
    assert SECRET not in capsys.readouterr().err


def test_422_on_bad_path_uuid_and_bad_json():
    client = _mini_app()
    res = client.post("/create/not-a-uuid", json={"text": "x"})
    assert res.status_code == 422
    assert {"field": "student_uuid", "code": "invalid_uuid"} in res.json()["errors"]
    res = client.post(f"/create/{uuid.uuid4()}", content=b"{broken",
                      headers={"Content-Type": "application/json"})
    assert res.status_code == 422 and res.headers["cache-control"] == NO_STORE


def test_dependency_http_exception_keeps_status_and_headers():
    res = _mini_app().get("/denied")
    assert res.status_code == 403
    assert res.json() == {"detail": "forbidden"}
    assert res.headers["cache-control"] == NO_STORE
    assert res.headers["www-authenticate"] == "Bearer"


def test_audit_error_is_503_never_500(capsys):
    res = _mini_app().get("/audit")
    assert res.status_code == 503 and res.headers["cache-control"] == NO_STORE
    assert SECRET not in res.text and SECRET not in capsys.readouterr().err


def test_unexpected_error_is_500_without_details(capsys):
    res = _mini_app().get("/boom")
    assert res.status_code == 500 and res.headers["cache-control"] == NO_STORE
    assert res.json() == {"detail": "Внутренняя ошибка"}
    err = capsys.readouterr().err
    assert SECRET not in res.text and SECRET not in err
    assert "error=RuntimeError" in err


# ── validators ────────────────────────────────────────────────────────────────

def test_normalize_text():
    assert validators.normalize_text("  Прочитать главу\r\nи записать  ") == "Прочитать главу\nи записать"
    assert validators.normalize_text("a\tb") == "a\tb"
    for raw, code in (("   ", "required"), ("", "required"),
                      ("x" * (validators.TEXT_MAX + 1), "too_long"),
                      ("bad\x00char", "invalid_characters"),
                      ("bell\x07", "invalid_characters")):
        with pytest.raises(AssignmentValidationError) as info:
            validators.normalize_text(raw)
        assert [e.as_dict() for e in info.value.errors] == [{"field": "text", "code": code}]


def test_cursor_roundtrip_and_rejects_garbage():
    stamp = datetime(2026, 10, 26, 9, 30, 15, 123456, tzinfo=timezone.utc)
    value = uuid.uuid4()
    cursor = validators.encode_cursor(stamp, value)
    assert validators.decode_cursor(cursor) == (stamp, value)
    assert validators.decode_cursor(None) is None
    naive = validators.encode_cursor(stamp.replace(tzinfo=None), value)
    for bad in ("", "%%%", "bm90LWEtY3Vyc29y", naive):
        with pytest.raises(AssignmentValidationError) as info:
            validators.decode_cursor(bad)
        assert [e.as_dict() for e in info.value.errors] == [
            {"field": "before", "code": "invalid_cursor"}]


# ── service ───────────────────────────────────────────────────────────────────

def _row(n, **extra):
    base = {
        "id": n, "uuid": uuid.UUID(int=n), "text": f"{SECRET} {n}",
        "status": "active", "due_date": None,
        "created_at": datetime(2026, 10, 20, tzinfo=timezone.utc) - timedelta(minutes=n),
        "completed_at": None, "cancelled_at": None,
        "engagement_active": True, "psychologist_name": "Иванова И. И.",
        "material": None, "material_unavailable": False,
    }
    base.update(extra)
    return base


class _Spy:
    def __init__(self, fail_on=None):
        self.calls = []
        self.fail_on = fail_on

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_on is not None and len(self.calls) == self.fail_on:
            raise AuditStorageError("audit down")


def test_psychologist_read_records_event_per_page_item_before_returning(monkeypatch):
    page = {"rows": [_row(1), _row(2)], "has_more": True, "total": 5}
    monkeypatch.setattr(service.storage, "list_psychologist_page", lambda *a: page)
    spy = _Spy()
    monkeypatch.setattr(service, "record_event", spy)
    out = service.list_for_client(PsychologistContext(7), uuid.uuid4(), None, 2,
                                  ip="10.0.0.1", user_agent="UA")
    assert [c["target"].entity_id for c in spy.calls] == [1, 2]
    for call in spy.calls:
        assert call["event"] == "assignment_content_read"
        assert call["actor"].user_id == 7 and call["actor"].role == "psychologist"
        assert call["target"].entity_type == "assignment"
        assert call["metadata"] == {} and "db" not in call
    assert [i["uuid"] for i in out["items"]] == [uuid.UUID(int=1), uuid.UUID(int=2)]
    assert out["has_more"] is True and out["next_cursor"] is not None
    assert all(i["can_cancel"] for i in out["items"])


def test_psychologist_read_fails_closed_on_any_audit_error(monkeypatch):
    page = {"rows": [_row(1), _row(2), _row(3)], "has_more": False, "total": 3}
    monkeypatch.setattr(service.storage, "list_psychologist_page", lambda *a: page)
    spy = _Spy(fail_on=2)
    monkeypatch.setattr(service, "record_event", spy)
    with pytest.raises(AuditStorageError):
        service.list_for_client(PsychologistContext(7), uuid.uuid4(), None, 20)
    assert len(spy.calls) == 2       # третье событие не пишется, ответа нет


def test_psychologist_read_empty_page_writes_no_events(monkeypatch):
    monkeypatch.setattr(service.storage, "list_psychologist_page",
                        lambda *a: {"rows": [], "has_more": False, "total": 0})
    spy = _Spy()
    monkeypatch.setattr(service, "record_event", spy)
    out = service.list_for_client(PsychologistContext(7), uuid.uuid4(), None, 20)
    assert out == {"items": [], "has_more": False, "next_cursor": None, "total": 0}
    assert spy.calls == []


def test_psychologist_read_without_grant_is_not_available(monkeypatch):
    monkeypatch.setattr(service.storage, "list_psychologist_page", lambda *a: None)
    spy = _Spy()
    monkeypatch.setattr(service, "record_event", spy)
    with pytest.raises(AssignmentNotAvailable):
        service.list_for_client(PsychologistContext(7), uuid.uuid4(), None, 20)
    assert spy.calls == []


def test_owner_list_flags_and_overdue_by_moscow_date(monkeypatch):
    today = date(2026, 10, 26)
    monkeypatch.setattr(service, "_today_moscow", lambda: today)
    rows = [
        _row(1, due_date=date(2026, 10, 25)),                          # просрочено
        _row(2, due_date=today),                                       # срок сегодня
        _row(3, due_date=date(2026, 10, 1), engagement_active=False),  # история
        _row(4, due_date=date(2026, 10, 1), status="completed",
             completed_at=datetime(2026, 10, 2, tzinfo=timezone.utc)),
        _row(5, psychologist_name=""),
    ]
    monkeypatch.setattr(service.storage, "list_client_page",
                        lambda *a: {"rows": rows, "has_more": False, "total": 5})
    out = service.list_my(ClientContext(3), "open", None, 20)
    items = out["items"]
    assert [i["is_overdue"] for i in items] == [True, False, False, False, False]
    assert [i["can_complete"] for i in items] == [True, True, False, False, True]
    assert items[4]["psychologist_name"] == service.PSYCHOLOGIST_FALLBACK_NAME
    assert out["next_cursor"] is None


def test_today_moscow_uses_utc_plus_3(monkeypatch):
    # 22:30 UTC 25 октября — в Москве уже 26 октября.
    class _Dt(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 25, 22, 30, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr(service, "datetime", _Dt)
    assert service._today_moscow() == date(2026, 10, 26)


def test_create_validates_text_before_storage(monkeypatch):
    called = []
    monkeypatch.setattr(service.storage, "create_atomic", lambda *a, **k: called.append(1))
    with pytest.raises(AssignmentValidationError):
        service.create_for_client(PsychologistContext(7), uuid.uuid4(),
                                  text="   ", due_date=None, article_uuid=None)
    assert called == []


def test_create_accepts_past_due_date(monkeypatch):
    seen = {}

    def fake(psych_id, client_uuid, text, due_date, article_uuid, **kw):
        seen.update(text=text, due_date=due_date)
        return {"changed": True}

    monkeypatch.setattr(service.storage, "create_atomic", fake)
    service.create_for_client(PsychologistContext(7), uuid.uuid4(), text=" Сделать ",
                              due_date=date(2020, 1, 1), article_uuid=None)
    assert seen == {"text": "Сделать", "due_date": date(2020, 1, 1)}


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


# ── storage: решения переходов на фейковой сессии ─────────────────────────────

class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row

    def scalar(self):
        return self._row


class _FakeDb:
    """execute() отдаёт результаты по очереди (или бросает исключение-элемент)."""

    def __init__(self, *results):
        self._queue = list(results)
        self.rolled_back = 0
        self.committed = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, *a, **k):
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return _Result(item)

    def rollback(self):
        self.rolled_back += 1

    def commit(self):
        self.committed += 1


def _mut(status, n=1):
    return SimpleNamespace(
        id=n, uuid=uuid.UUID(int=n), status=status,
        created_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        completed_at=datetime(2026, 10, 21, tzinfo=timezone.utc) if status == "completed" else None,
        cancelled_at=datetime(2026, 10, 21, tzinfo=timezone.utc) if status == "cancelled" else None,
    )


REF = SimpleNamespace(id=1, engagement_id=10, psychologist_id=7, client_name="Иванова Анна")
ENG_ACTIVE = SimpleNamespace(status="active", ended_at=None)
ENG_ENDED = SimpleNamespace(status="completed", ended_at=datetime(2026, 10, 1, tzinfo=timezone.utc))


@pytest.fixture
def no_audit(monkeypatch):
    def fail(**kwargs):
        raise AssertionError("audit must not be written")
    monkeypatch.setattr(storage, "record_event", fail)


def _use(monkeypatch, db):
    monkeypatch.setattr(storage, "SessionLocal", lambda: db)
    return db


def test_complete_already_completed_is_noop(monkeypatch, no_audit):
    db = _use(monkeypatch, _FakeDb(REF, ENG_ENDED, _mut("completed")))
    out = storage.complete_atomic(3, uuid.UUID(int=1))
    assert out["changed"] is False and out["status"] == "completed"
    assert "notify" not in out                       # no-op не уведомляет
    assert db.committed == 0


def test_complete_cancelled_is_finalized(monkeypatch, no_audit):
    _use(monkeypatch, _FakeDb(REF, ENG_ACTIVE, _mut("cancelled")))
    with pytest.raises(AssignmentFinalized) as info:
        storage.complete_atomic(3, uuid.UUID(int=1))
    assert info.value.current_status == "cancelled"


def test_complete_in_ended_engagement_is_inactive(monkeypatch, no_audit):
    _use(monkeypatch, _FakeDb(REF, ENG_ENDED, _mut("active")))
    with pytest.raises(AssignmentEngagementInactive):
        storage.complete_atomic(3, uuid.UUID(int=1))


def test_complete_foreign_is_not_available(monkeypatch, no_audit):
    _use(monkeypatch, _FakeDb(None))
    with pytest.raises(AssignmentNotAvailable):
        storage.complete_atomic(3, uuid.UUID(int=1))


def test_complete_lost_race_to_cancel_is_finalized(monkeypatch, no_audit):
    # Условный UPDATE не нашёл active-строку: параллельная отмена победила.
    _use(monkeypatch, _FakeDb(REF, ENG_ACTIVE, _mut("active"), None, _mut("cancelled")))
    with pytest.raises(AssignmentFinalized) as info:
        storage.complete_atomic(3, uuid.UUID(int=1))
    assert info.value.current_status == "cancelled"


def test_complete_lost_race_to_own_retry_is_noop(monkeypatch, no_audit):
    _use(monkeypatch, _FakeDb(REF, ENG_ACTIVE, _mut("active"), None, _mut("completed")))
    out = storage.complete_atomic(3, uuid.UUID(int=1))
    assert out["changed"] is False and out["status"] == "completed"


def test_complete_success_stages_audit_in_same_session(monkeypatch):
    db = _use(monkeypatch, _FakeDb(REF, ENG_ACTIVE, _mut("active"), _mut("completed")))
    calls = []
    monkeypatch.setattr(storage, "record_event", lambda **k: calls.append(k))
    out = storage.complete_atomic(3, uuid.UUID(int=1), ip="10.0.0.1", user_agent="UA")
    assert out["changed"] is True and out["status"] == "completed"
    assert out["notify"] == {"psychologist_id": 7, "client_name": "Иванова Анна"}
    assert len(calls) == 1 and calls[0]["db"] is db
    assert calls[0]["event"] == "assignment_completed"
    assert calls[0]["actor"].role == "student" and calls[0]["target"].entity_id == 1
    assert calls[0]["metadata"] == {}
    assert db.committed == 1


def test_complete_audit_failure_propagates_without_commit(monkeypatch):
    db = _use(monkeypatch, _FakeDb(REF, ENG_ACTIVE, _mut("active"), _mut("completed")))

    def boom(**k):
        raise AuditStorageError("down")

    monkeypatch.setattr(storage, "record_event", boom)
    with pytest.raises(AuditStorageError):
        storage.complete_atomic(3, uuid.UUID(int=1))
    assert db.committed == 0


def test_cancel_without_grant_is_not_available(monkeypatch, no_audit):
    # Своё задание, но сопровождение больше не строго активно → нет права.
    _use(monkeypatch, _FakeDb(REF, None))
    with pytest.raises(AssignmentNotAvailable):
        storage.cancel_atomic(7, uuid.UUID(int=1))


def test_cancel_completed_is_finalized_and_cancelled_is_noop(monkeypatch, no_audit):
    _use(monkeypatch, _FakeDb(REF, 10, _mut("completed")))
    with pytest.raises(AssignmentFinalized) as info:
        storage.cancel_atomic(7, uuid.UUID(int=1))
    assert info.value.current_status == "completed"
    _use(monkeypatch, _FakeDb(REF, 10, _mut("cancelled")))
    assert storage.cancel_atomic(7, uuid.UUID(int=1))["changed"] is False


def test_cancel_lost_race_to_complete_is_finalized(monkeypatch, no_audit):
    _use(monkeypatch, _FakeDb(REF, 10, _mut("active"), None, _mut("completed")))
    with pytest.raises(AssignmentFinalized):
        storage.cancel_atomic(7, uuid.UUID(int=1))


# ── storage: санитизация ──────────────────────────────────────────────────────

SQL_MARKER = "SQL-MARKER-9a7e"
CIPHER_MARKER = "enc:v1:CIPHER-MARKER-9a7e"


def _synthetic():
    return OperationalError(
        f"INSERT INTO assignments (text_enc) VALUES (%(t)s) /* {SQL_MARKER} */",
        {"t": CIPHER_MARKER}, SimpleNamespace(),
    )


def _assert_sanitized(exc, err):
    assert isinstance(exc, AssignmentsStorageError)
    assert exc.__cause__ is None and exc.__context__ is None
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    for marker in (SQL_MARKER, CIPHER_MARKER, "INSERT INTO assignments", SECRET):
        assert marker not in rendered and marker not in err


@pytest.mark.parametrize("call, op", [
    (lambda: storage.list_client_page(3, "open", None, 20), "list_my"),
    (lambda: storage.client_summary(3), "summary"),
    (lambda: storage.list_psychologist_page(7, uuid.uuid4(), None, 20), "list_client"),
    (lambda: storage.create_atomic(7, uuid.uuid4(), SECRET, None, None), "create"),
    (lambda: storage.complete_atomic(3, uuid.uuid4()), "complete"),
    (lambda: storage.cancel_atomic(7, uuid.uuid4()), "cancel"),
])
def test_read_errors_are_sanitized(monkeypatch, capsys, call, op):
    db = _use(monkeypatch, _FakeDb(_synthetic()))
    with pytest.raises(AssignmentsStorageError) as info:
        call()
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert f"op={op} phase=read error=OperationalError" in err
    assert db.rolled_back == 1


def test_create_write_error_is_sanitized(monkeypatch, capsys, no_audit):
    _use(monkeypatch, _FakeDb(10, _synthetic()))
    with pytest.raises(AssignmentsStorageError) as info:
        storage.create_atomic(7, uuid.uuid4(), SECRET, None, None)
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert "op=create phase=write error=OperationalError" in err


class _ListDb(_FakeDb):
    """Сессия для _page: первая выборка — строки (.all()), вторая — total."""

    def __init__(self, rows, total):
        super().__init__()
        self._rows, self._total = rows, total

    def execute(self, *a, **k):
        rows, self._rows = self._rows, None
        if rows is not None:
            return SimpleNamespace(all=lambda: rows)
        return _Result(self._total)


def test_corrupted_ciphertext_is_reported_without_values(monkeypatch, capsys):
    row = SimpleNamespace(
        id=1, uuid=uuid.uuid4(), text_enc=ENCRYPTION_PREFIX + "garbage", status="active",
        due_date=None, created_at=None, completed_at=None, cancelled_at=None,
        article_id=None, article_uuid=None, article_title=None, article_published=None,
        article_deleted_at=None, eng_status="active", eng_ended_at=None,
        psychologist_name=None,
    )
    db = _use(monkeypatch, _ListDb([row], 1))
    with pytest.raises(AssignmentsStorageError) as info:
        storage.list_client_page(3, "open", None, 20)
    err = capsys.readouterr().err
    _assert_sanitized(info.value, err)
    assert "op=list_my phase=read error=Undecryptable" in err and "garbage" not in err
    assert db.rolled_back == 1


def test_hidden_material_is_not_disclosed():
    base = dict(
        id=1, uuid=uuid.uuid4(), status="active", due_date=None, created_at=None,
        completed_at=None, cancelled_at=None, eng_status="active", eng_ended_at=None,
        psychologist_name="X", article_id=5, article_uuid=uuid.uuid4(),
        article_title="Скрытый черновик",
    )
    enc = encrypt_text("t")
    for published, deleted in ((False, None), (True, datetime.now(timezone.utc)), (None, None)):
        row = SimpleNamespace(**base, text_enc=enc, article_published=published,
                              article_deleted_at=deleted)
        out = storage._row_dict(row)
        assert out["material"] is None and out["material_unavailable"] is True
    row = SimpleNamespace(**base, text_enc=enc, article_published=True, article_deleted_at=None)
    out = storage._row_dict(row)
    assert out["material"] == {"uuid": base["article_uuid"], "title": "Скрытый черновик"}
    assert out["material_unavailable"] is False


def test_create_schema_is_strict():
    assert AssignmentCreateIn.model_config.get("extra") == "forbid"


# ── уведомление психолога о выполнении ───────────────────────────────────────

def test_complete_notifies_psychologist_after_commit_without_task_text(monkeypatch):
    sent = []
    result = {"uuid": uuid.UUID(int=5), "status": "completed", "changed": True,
              "notify": {"psychologist_id": 7, "client_name": "Иванова Анна"}}
    monkeypatch.setattr(service.storage, "complete_atomic", lambda *a, **k: dict(result))
    monkeypatch.setattr(service, "publish_system_message", lambda **k: sent.append(k))
    out = service.complete_my(ClientContext(3), uuid.UUID(int=5))
    assert "notify" not in out and out["changed"] is True
    assert sent == [{
        "recipient_id": 7,
        "event_key": f"assignment_completed:assignment:{uuid.UUID(int=5)}",
        "text": "Задание выполнено. Клиент: Иванова Анна. Статус виден в карточке клиента.",
    }]
    assert SECRET not in sent[0]["text"]


def test_noop_complete_does_not_notify(monkeypatch):
    sent = []
    monkeypatch.setattr(service.storage, "complete_atomic",
                        lambda *a, **k: {"uuid": uuid.UUID(int=5), "status": "completed", "changed": False})
    monkeypatch.setattr(service, "publish_system_message", lambda **k: sent.append(k))
    assert service.complete_my(ClientContext(3), uuid.UUID(int=5))["changed"] is False
    assert sent == []


def test_notification_text_falls_back_without_name():
    assert service.completed_message_text("  ") == (
        "Задание выполнено. Клиент: клиент. Статус виден в карточке клиента.")
