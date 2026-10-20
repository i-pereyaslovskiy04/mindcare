"""
ADR-029 — gated integration: неожиданные SQLAlchemy-ошибки подачи и решения
не раскрывают SQL, параметры и ciphertext/plaintext ни в ASGI traceback, ни в
серверной диагностике, ни в ответе; не превращаются в ложный *_failed.

Реальные сбои БД: подменённый encrypt_text возвращает значение без префикса
`enc:v1:` с маркером → CHECK ck_svr_ticket_encrypted (flush подачи) или
ck_svr_reason_encrypted (UPDATE решения) отклоняет строку, и исходная
IntegrityError несёт маркер в параметрах. Синтетический сбой commit —
OperationalError с маркерами в SQL, параметрах и ошибке драйвера.
"""
import json
import logging
import traceback
import uuid as _uuid
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient

import app.student_verification.storage as sv_storage
from app.db.models import (
    AuditLog, AuthLog, DataChangeLog, StudentVerificationRequest as SVR,
    SystemMessageIntent,
)
from app.db.session import SessionLocal
from app.main import app
from app.student_verification.errors import VerificationStorageError
from tests.integration.conftest import create_multi_role_user, create_test_user

PASSWORD = "SecurePass42!"
ME_URL = "/api/student-verification/me"
LIST_URL = "/api/supervisor/student-verifications"
TICKET_MARKER = "PLAIN-TICKET-MARKER-5c1e"
REASON_MARKER = "PLAIN-REASON-MARKER-5c1e"
SQL_MARKER = "SQL-MARKER-5c1e"
CIPHER_MARKER = "enc:v1:CIPHER-MARKER-5c1e"
ALL_MARKERS = (TICKET_MARKER, REASON_MARKER, SQL_MARKER, CIPHER_MARKER,
               "INSERT INTO", "UPDATE student_verification_requests",
               "ck_svr_", "ticket_number_enc", "rejection_reason_enc")


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _student(client):
    email = f"integ_svs_{_uuid.uuid4().hex[:10]}@example.com"
    uid = int(create_test_user(email, PASSWORD)["id"])
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return uid, r.json()["session_token"]


def _pending(client):
    uid, token = _student(client)
    r = client.post(ME_URL, headers=_auth(token),
                    json={"faculty_code": "law", "ticket_number": "000123"})
    assert r.status_code == 201, r.text
    return uid, r.json()["current"]["uuid"]


def _supervisor(client):
    token, uid, _ = create_multi_role_user(client, ["supervisor", "student"])
    return uid, token


def _marks():
    with SessionLocal() as db:
        return tuple(
            db.query(m.id).order_by(m.id.desc()).limit(1).scalar() or 0
            for m in (AuditLog, AuthLog, DataChangeLog)
        )


def _new_audit_events(marks):
    with SessionLocal() as db:
        return [r.event_type for r in db.query(AuditLog).filter(AuditLog.id > marks[0])]


def _blob_since(marks):
    parts = []
    with SessionLocal() as db:
        for model, mark in zip((AuditLog, AuthLog, DataChangeLog), marks):
            for row in db.query(model).filter(model.id > mark):
                for col in row.__table__.columns:
                    val = getattr(row, col.name)
                    parts.append(json.dumps(val, ensure_ascii=False, default=str))
    return " ".join(parts)


def _status(req_uuid):
    with SessionLocal() as db:
        return db.query(SVR.status).filter(SVR.uuid == req_uuid).scalar()


def _result_intents(req_uuid):
    with SessionLocal() as db:
        return db.query(SystemMessageIntent).filter(
            SystemMessageIntent.event_key == f"student_verification_result:{req_uuid}",
        ).count()


def _assert_clean_exception(exc):
    assert isinstance(exc, VerificationStorageError)
    assert exc.__cause__ is None and exc.__context__ is None
    rendered = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    # Серверный лог необработанного исключения (как uvicorn "Exception in ASGI
    # application") — тот же traceback через logging.
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 0,
                               "Exception in ASGI application", None,
                               (type(exc), exc, exc.__traceback__))
    logged = logging.Formatter().format(record)
    for marker in ALL_MARKERS:
        assert marker not in rendered, marker
        assert marker not in logged, marker


def _assert_clean_server_output(capsys, caplog, phase_line):
    captured = capsys.readouterr()
    assert phase_line in captured.err
    for marker in ALL_MARKERS:
        assert marker not in captured.err, marker
        assert marker not in captured.out, marker
        assert marker not in caplog.text, marker


@pytest.fixture
def plain_client():
    """500 как его видит клиент (без проброса исключения в тест)."""
    return TestClient(app, raise_server_exceptions=False, client=("127.0.0.1", 50000))


def test_unknown_flush_error_on_submit_is_sanitized(client, plain_client, monkeypatch,
                                                    capsys, caplog):
    uid, token = _student(client)
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    marks = _marks()
    monkeypatch.setattr(sv_storage, "encrypt_text", lambda value: f"{value}")

    body = {"faculty_code": "law", "ticket_number": TICKET_MARKER}
    with pytest.raises(VerificationStorageError) as info:
        client.post(ME_URL, headers=_auth(token), json=body)
    _assert_clean_exception(info.value)
    _assert_clean_server_output(capsys, caplog,
                                "op=submit phase=flush error=IntegrityError")

    r = plain_client.post(ME_URL, headers=_auth(token), json=body)
    assert r.status_code == 500
    assert all(marker not in r.text for marker in ALL_MARKERS)

    with SessionLocal() as db:
        assert db.query(SVR).filter(SVR.user_id == uid).count() == 0
    events = _new_audit_events(marks)
    assert "student_verification_submitted" not in events
    assert "student_verification_submit_failed" not in events
    assert TICKET_MARKER not in _blob_since(marks)


def test_unknown_update_error_on_reject_is_sanitized(client, monkeypatch, capsys, caplog):
    applicant, req_uuid = _pending(client)
    _, sup = _supervisor(client)
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    marks = _marks()
    monkeypatch.setattr(sv_storage, "encrypt_text", lambda value: f"{value}")

    with pytest.raises(VerificationStorageError) as info:
        client.post(f"{LIST_URL}/{req_uuid}/reject", headers=_auth(sup),
                    json={"reason": REASON_MARKER})
    _assert_clean_exception(info.value)
    _assert_clean_server_output(capsys, caplog,
                                "op=decide phase=update error=IntegrityError")

    assert _status(req_uuid) == "pending"
    assert _result_intents(req_uuid) == 0
    events = _new_audit_events(marks)
    assert "student_verification_rejected" not in events
    assert "student_verification_review_failed" not in events
    assert REASON_MARKER not in _blob_since(marks)


def test_unknown_commit_error_on_approve_is_sanitized(client, monkeypatch, capsys, caplog):
    _, req_uuid = _pending(client)
    _, sup = _supervisor(client)
    caplog.set_level(logging.DEBUG)
    capsys.readouterr()
    marks = _marks()
    real_factory = sv_storage.SessionLocal

    def _failing_commit():
        raise OperationalError(
            f"COMMIT /* {SQL_MARKER} */",
            {"rejection_reason_enc": CIPHER_MARKER, "plain": REASON_MARKER},
            SimpleNamespace(diag=SimpleNamespace(constraint_name=None)),
        )

    def _factory():
        session = real_factory()
        session.commit = _failing_commit
        return session

    monkeypatch.setattr(sv_storage, "SessionLocal", _factory)
    with pytest.raises(VerificationStorageError) as info:
        client.post(f"{LIST_URL}/{req_uuid}/approve", headers=_auth(sup))
    _assert_clean_exception(info.value)
    _assert_clean_server_output(capsys, caplog,
                                "op=decide phase=commit error=OperationalError")

    monkeypatch.undo()
    assert _status(req_uuid) == "pending"
    assert _result_intents(req_uuid) == 0
    events = _new_audit_events(marks)
    assert "student_verification_approved" not in events
    assert "student_verification_review_failed" not in events
