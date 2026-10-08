"""
ADR-029 — gated integration: санитизация SQLAlchemy-ошибок ЧТЕНИЯ модуля
student_verification (список, собственный статус, карточка, предварительные
чтения подачи и решения).

Сбой — настоящий OperationalError PostgreSQL: listener before_cursor_execute
(retval=True) переписывает целевой SELECT по student_verification_requests так,
что сервер отменяет его по statement_timeout (QueryCanceled). SQLAlchemy
оборачивает ошибку драйвера РЕАЛЬНЫМ SQL (с маркером-комментарием) и
РЕАЛЬНЫМИ параметрами — в т.ч. введённым supervisor'ом search-email. Проверка:
исключение без цепочки, traceback и запись uvicorn.error, stderr/caplog и тело
500 — без маркеров, SQL и параметров; *_failed и content_read SUCCESS не пишутся.
"""
import logging
import traceback
import uuid as _uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient

from app.db.models import AuditLog, StudentVerificationRequest as SVR
from app.db.session import SessionLocal, engine
from app.main import app
from app.student_verification.errors import VerificationStorageError
from tests.integration.conftest import create_multi_role_user, create_test_user

PASSWORD = "SecurePass42!"
ME_URL = "/api/student-verification/me"
LIST_URL = "/api/supervisor/student-verifications"
SQL_MARKER = "SQL-READ-MARKER-9d2b"
SEARCH_MARKER = f"integ_search_marker_{_uuid.uuid4().hex[:8]}@example.com"
LEAKS = (SQL_MARKER, SEARCH_MARKER, "student_verification_requests", "SELECT ",
         "statement_timeout", "ILIKE", "ticket_number_enc", "enc:v1:")


@contextmanager
def _fail_reads():
    """Каждый SELECT по заявкам отменяется сервером (OperationalError)."""
    def _rewrite(conn, cursor, statement, parameters, context, executemany):
        if (statement.lstrip().upper().startswith("SELECT")
                and "student_verification_requests" in statement):
            statement = (
                f"SET LOCAL statement_timeout = '1ms'; SELECT pg_sleep(0.2); "
                f"{statement} /* {SQL_MARKER} */"
            )
        return statement, parameters

    event.listen(engine, "before_cursor_execute", _rewrite, retval=True)
    try:
        yield
    finally:
        event.remove(engine, "before_cursor_execute", _rewrite)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _student(client):
    email = f"integ_svr_{_uuid.uuid4().hex[:10]}@example.com"
    uid = int(create_test_user(email, PASSWORD)["id"])
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return uid, r.json()["session_token"]


def _pending(client):
    uid, token = _student(client)
    r = client.post(ME_URL, headers=_auth(token),
                    json={"faculty_code": "law", "ticket_number": "000123"})
    assert r.status_code == 201, r.text
    return uid, token, r.json()["current"]["uuid"]


def _supervisor(client):
    token, uid, _ = create_multi_role_user(client, ["supervisor", "student"])
    return uid, token


def _audit_mark():
    with SessionLocal() as db:
        return db.query(AuditLog.id).order_by(AuditLog.id.desc()).limit(1).scalar() or 0


def _audit_since(mark):
    with SessionLocal() as db:
        return [(r.event_type, r.outcome) for r in
                db.query(AuditLog).filter(AuditLog.id > mark).order_by(AuditLog.id)]


def _assert_clean(exc, capsys, caplog, op):
    assert isinstance(exc, VerificationStorageError)
    assert exc.__cause__ is None and exc.__context__ is None
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 0,
                               "Exception in ASGI application", None,
                               (type(exc), exc, exc.__traceback__))
    logged = logging.Formatter().format(record)
    captured = capsys.readouterr()
    assert f"op={op} phase=read error=OperationalError" in captured.err
    for leak in LEAKS:
        assert leak not in rendered, leak
        assert leak not in logged, leak
        assert leak not in captured.err, leak
        assert leak not in captured.out, leak
        assert leak not in caplog.text, leak


@pytest.fixture
def plain_client():
    return TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))


@pytest.fixture
def quiet(capsys, caplog):
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    return capsys, caplog


def test_injected_read_error_really_carries_sql_and_parameters(client):
    """Контроль инъекции: без санитизации SQL и параметры видны в str(exc)."""
    with _fail_reads(), SessionLocal() as db:
        with pytest.raises(OperationalError) as info:
            db.query(SVR.id).filter(SVR.faculty_code == SEARCH_MARKER).all()
    raw = str(info.value)
    assert SQL_MARKER in raw and SEARCH_MARKER in raw and "student_verification_requests" in raw


def test_list_read_error_with_search_email_is_sanitized(client, plain_client, quiet):
    capsys, caplog = quiet
    _, sup = _supervisor(client)
    mark = _audit_mark()
    params = {"status": "all", "search": SEARCH_MARKER}
    with _fail_reads():
        with pytest.raises(VerificationStorageError) as info:
            client.get(LIST_URL, headers=_auth(sup), params=params)
        _assert_clean(info.value, capsys, caplog, "list")
        r = plain_client.get(LIST_URL, headers=_auth(sup), params=params)
    assert r.status_code == 500
    assert all(leak not in r.text for leak in LEAKS)
    assert _audit_since(mark) == []
    # После сбоя модуль работает штатно (соединение/пул не испорчены).
    assert client.get(LIST_URL, headers=_auth(sup), params=params).status_code == 200


def test_card_read_error_writes_no_content_read(client, plain_client, quiet):
    capsys, caplog = quiet
    _, _, req_uuid = _pending(client)
    _, sup = _supervisor(client)
    mark = _audit_mark()
    with _fail_reads():
        with pytest.raises(VerificationStorageError) as info:
            client.get(f"{LIST_URL}/{req_uuid}", headers=_auth(sup))
        _assert_clean(info.value, capsys, caplog, "card")
        r = plain_client.get(f"{LIST_URL}/{req_uuid}", headers=_auth(sup))
    assert r.status_code == 500 and "000123" not in r.text
    assert _audit_since(mark) == []          # ни content_read SUCCESS, ни *_failed
    r = client.get(f"{LIST_URL}/{req_uuid}", headers=_auth(sup))
    assert r.status_code == 200 and r.json()["ticket_number"] == "000123"


def test_own_status_read_error_is_sanitized(client, quiet):
    capsys, caplog = quiet
    _, token, _ = _pending(client)
    mark = _audit_mark()
    with _fail_reads():
        with pytest.raises(VerificationStorageError) as info:
            client.get(ME_URL, headers=_auth(token))
        _assert_clean(info.value, capsys, caplog, "status")
    assert _audit_since(mark) == []


def test_submit_read_error_writes_no_failure_event(client, quiet):
    capsys, caplog = quiet
    uid, token = _student(client)
    mark = _audit_mark()
    with _fail_reads():
        with pytest.raises(VerificationStorageError) as info:
            client.post(ME_URL, headers=_auth(token),
                        json={"faculty_code": "law", "ticket_number": "000123"})
        _assert_clean(info.value, capsys, caplog, "submit")
    assert _audit_since(mark) == []
    with SessionLocal() as db:
        assert db.query(SVR).filter(SVR.user_id == uid).count() == 0


def test_decide_read_error_writes_no_failure_event(client, quiet):
    capsys, caplog = quiet
    _, _, req_uuid = _pending(client)
    _, sup = _supervisor(client)
    mark = _audit_mark()
    with _fail_reads():
        with pytest.raises(VerificationStorageError) as info:
            client.post(f"{LIST_URL}/{req_uuid}/approve", headers=_auth(sup))
        _assert_clean(info.value, capsys, caplog, "decide")
    assert _audit_since(mark) == []
    with SessionLocal() as db:
        assert db.query(SVR.status).filter(SVR.uuid == req_uuid).scalar() == "pending"
